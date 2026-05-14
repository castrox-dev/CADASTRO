"""Storages do Cloudinary com `resource_type='auto'`.

O `MediaCloudinaryStorage` padrão do `django-cloudinary-storage` faz upload com
``resource_type='image'``, o que faz o Cloudinary devolver «Invalid image file»
para PDF e outros formatos que não são tratados como imagem pelo endpoint de imagem.

Aqui:
    - Upload com ``resource_type='auto'`` (Cloudinary classifica imagem vs raw).
    - URL de entrega: ``/image/upload/`` ou ``/raw/upload/`` conforme extensão;
      **sem extensão no nome** (ex.: public_id só com sufixo aleatório) usamos
      **image**, porque nesse app o comum é foto; **.pdf** continua **raw**.
    - ``unique_filename=False``: o path já leva CPF/campo/extensão — evita perder
      a extensão no public_id e evita 404 ao abrir o link.
"""
from __future__ import annotations

import os
import re

import cloudinary
import cloudinary.api
import cloudinary.uploader
import requests
from cloudinary.utils import cloudinary_url
from django.core.files.base import ContentFile
from cloudinary_storage.storage import (
    MediaCloudinaryStorage,
    RESOURCE_TYPES,
)


# Extensões tratadas como «imagem» na URL do Cloudinary. Inclui formatos legados
# já armazenados antes da política restrita de upload (novos envios: só JPG/PNG/WebP/PDF).
IMAGE_EXTS = frozenset({
    '.jpg', '.jpeg', '.png', '.webp',
    '.gif', '.bmp', '.tif', '.tiff', '.svg', '.heic', '.heif', '.avif',
})

# Extensões entregues como «raw» na URL (PDF e binários). O restante usa «image».
RAW_DELIVERY_EXTS = frozenset({
    '.pdf',
})


class AutoMediaCloudinaryStorage(MediaCloudinaryStorage):
    """Sobe qualquer arquivo (imagem ou PDF) usando `resource_type='auto'`."""

    RESOURCE_TYPE = RESOURCE_TYPES['IMAGE']  # default; sobrescrito por arquivo

    _HTTP_HEADERS = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        ),
        'Accept': '*/*',
    }

    def _slug_tail(self, name):
        return str(name or '').replace('\\', '/').rsplit('/', 1)[-1].lower()

    def _is_documentos_cliente_path(self, p):
        return 'documentos_clientes' in str(p or '').replace('\\', '/').lower()

    def _is_pdfish_slug(self, name):
        """Comprovante / contrato social: PDF no Cloudinary muitas vezes sem extensão no public_id."""
        slug = self._slug_tail(name)
        return any(
            k in slug
            for k in ('comprovante', 'contrato', 'residencia', 'social')
        )

    def _ext(self, name):
        return os.path.splitext(name or '')[1].lower()

    def _is_image(self, name):
        return self._ext(name) in IMAGE_EXTS

    def _get_resource_type(self, name):
        """Tipo na URL de entrega deve bater com o tipo real no Cloudinary.

        Upload com ``resource_type='auto'`` grava fotos como *image*. Se o nome no
        banco perdeu a extensão (ex.: sufixo aleatório do Cloudinary), cair em
        ``raw`` na URL gera 404. PDF continua ``raw``.
        """
        ext = self._ext(name)
        if ext in RAW_DELIVERY_EXTS:
            return 'raw'
        if self._is_image(name):
            return 'image'
        # Sem extensão no public_id: PDFs de contrato/comprovante costumam ir como *raw*
        # no Cloudinary (upload `auto`); assumir *image* quebra o download (URL 404).
        if not ext:
            slug = self._slug_tail(name)
            if any(
                k in slug
                for k in ('contrato', 'comprovante', 'residencia', 'social')
            ):
                return 'raw'
            return 'image'
        return 'raw'

    def _resource_types_for_open(self, name):
        """Ordem ao ler bytes: sem extensão em documentos do cliente → image depois raw (JPEG ou PDF)."""
        ext = self._ext(name)
        path = str(name or '').replace('\\', '/')
        if not ext and (self._is_documentos_cliente_path(path) or self._is_pdfish_slug(path)):
            return ['image', 'raw']
        primary = self._get_resource_type(name)
        alt = 'raw' if primary == 'image' else 'image'
        return [primary, alt]

    def _strip_cloudinary_random_suffix(self, public_id):
        """Remove sufixo tipo ``_en5o0b`` (4–12 chars) do final do public_id."""
        p = str(public_id or '').strip().replace('\\', '/')
        return re.sub(r'_[a-z0-9]{4,12}$', '', p, flags=re.IGNORECASE)

    def _norm_public_id_compare(self, s):
        p = str(s or '').strip().replace('\\', '/')
        if p.startswith('media/'):
            p = p[len('media/') :]
        return self._strip_cloudinary_random_suffix(p)

    def _cloudinary_public_ids_match(self, requested, found):
        """True se o asset listado for o mesmo ficheiro lógico (media/, sufixo Cloudinary)."""
        r = self._norm_public_id_compare(requested)
        f = self._norm_public_id_compare(found)
        if r == f:
            return True
        r_full = str(requested or '').replace('\\', '/')
        f_full = str(found or '').replace('\\', '/')
        if r_full == f_full:
            return True
        return f_full.startswith(r + '_') or r_full.startswith(f + '_')

    def _admin_prefix_candidates(self, pub_id):
        p = str(pub_id or '').strip().replace('\\', '/')
        if not p:
            return []
        out = []
        for x in (p, self._strip_cloudinary_random_suffix(p)):
            if x and x not in out:
                out.append(x)
            if x.startswith('media/'):
                no_media = x[len('media/') :]
                if no_media and no_media not in out:
                    out.append(no_media)
        return list(dict.fromkeys(out))

    def _open_via_admin_list_prefix(self, pub_id, original_name, mode):
        """Lista recursos por prefixo (public_id no Django ≠ asset real no Cloudinary)."""
        if not self._is_documentos_cliente_path(pub_id):
            return None
        for prefix in self._admin_prefix_candidates(pub_id):
            for rtype in ('image', 'raw'):
                try:
                    resp = cloudinary.api.resources(
                        type='upload',
                        resource_type=rtype,
                        prefix=prefix,
                        max_results=50,
                    )
                except Exception:
                    continue
                for item in (resp or {}).get('resources', []) or []:
                    ipid = (item.get('public_id') or '').replace('\\', '/')
                    if not self._cloudinary_public_ids_match(pub_id, ipid):
                        continue
                    url = item.get('secure_url') or item.get('url')
                    data = self._http_get_binary(url)
                    if data:
                        fileobj = ContentFile(data)
                        fileobj.name = original_name
                        fileobj.mode = mode
                        return fileobj
        return None

    def _public_id_fetch_variants(self, pub_id, original_name):
        """Variantes de public_id: extensões comuns + base sem sufixo aleatório Cloudinary."""
        p = str(pub_id or '').strip().replace('\\', '/')
        if not p:
            return []
        out = [p]
        ext = self._ext(original_name or p)

        def push(q):
            if q and q not in out:
                out.append(q)

        def add_exts(path):
            if not path:
                return
            low = path.lower()
            for tail in ('.jpg', '.jpeg', '.pdf', '.png', '.webp'):
                if not low.endswith(tail):
                    push(path + tail)

        if not ext and self._is_documentos_cliente_path(p):
            add_exts(p)
            stripped = self._strip_cloudinary_random_suffix(p)
            if stripped != p:
                push(stripped)
                add_exts(stripped)
        elif not ext and self._is_pdfish_slug(p):
            if not p.lower().endswith('.pdf'):
                push(p + '.pdf')
            stripped = self._strip_cloudinary_random_suffix(p)
            if stripped != p:
                push(stripped)
                if not stripped.lower().endswith('.pdf'):
                    push(stripped + '.pdf')
        return list(dict.fromkeys(out))

    def _delivery_resource_type_chain(self, name):
        """Compat: delega para ``_resource_types_for_open``."""
        return self._resource_types_for_open(name)

    def _public_id_candidates(self, name):
        """Public IDs a testar (prefixo Cloudinary / path relativo / variações comuns)."""
        raw = str(name or '').strip().replace('\\', '/')
        if not raw or raw.startswith(('http://', 'https://')):
            return []
        out = []
        prefixed = self._prepend_prefix(raw)
        if prefixed:
            out.append(prefixed)
        if raw not in out:
            out.append(raw)
        # Alguns registros guardam só a pasta+arquivo sem o prefixo de MEDIA do pacote.
        if '/' in raw:
            tail = raw.split('/', 1)[1]
            if tail and tail not in out:
                out.append(tail)
        return list(dict.fromkeys(out))

    def _http_get_binary(self, url):
        if not url:
            return None
        try:
            response = requests.get(
                url, timeout=120, headers=self._HTTP_HEADERS, allow_redirects=True
            )
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        data = response.content or b''
        return data if data else None

    def _open_from_signed_delivery(self, public_id, resource_type, fmt=None):
        opts = {
            'resource_type': resource_type,
            'secure': True,
            'sign_url': True,
        }
        if fmt:
            opts['format'] = fmt
        try:
            url, _ = cloudinary_url(public_id, **opts)
        except Exception:
            return None
        return self._http_get_binary(url)

    def _open_from_admin_api(self, public_id, original_name, mode):
        """Usa a Admin API para obter a URL canónica (útil quando a URL pública construída falha)."""
        for rtype in ('image', 'raw'):
            try:
                meta = cloudinary.api.resource(public_id, resource_type=rtype)
            except Exception:
                continue
            for key in ('secure_url', 'url'):
                u = meta.get(key)
                data = self._http_get_binary(u)
                if data:
                    fileobj = ContentFile(data)
                    fileobj.name = original_name
                    fileobj.mode = mode
                    return fileobj
        return None

    def _collect_delivery_urls(self, pid, rtype, original_name):
        """URLs a testar (Resource + raw com ``format=pdf`` para comprovante/contrato sem extensão)."""
        urls = []
        try:
            urls.append(
                cloudinary.CloudinaryResource(
                    pid,
                    default_resource_type=rtype,
                ).url
            )
        except Exception:
            pass
        if (
            rtype == 'raw'
            and self._is_pdfish_slug(pid)
            and not str(pid).lower().endswith('.pdf')
        ):
            try:
                u_fmt, _ = cloudinary_url(
                    pid,
                    resource_type='raw',
                    format='pdf',
                    secure=True,
                )
                urls.append(u_fmt)
            except Exception:
                pass
        return list(dict.fromkeys(urls))

    def url(self, name):
        """Entrega com ``format=pdf`` em raw quando o public_id não tem extensão (evita 404 no browser)."""
        raw = str(name or '').strip().replace('\\', '/')
        if raw.startswith(('http://', 'https://')):
            return raw
        norm_fn = getattr(self, '_normalise_name', None)
        if callable(norm_fn):
            n = norm_fn(raw)
        else:
            n = raw.replace('\\', '/')
        prefixed = self._prepend_prefix(n)
        if not self._ext(prefixed) and self._is_pdfish_slug(prefixed):
            try:
                u, _ = cloudinary_url(
                    prefixed,
                    resource_type='raw',
                    format='pdf',
                    secure=True,
                )
                return u
            except Exception:
                pass
        return super().url(name)

    def _open(self, name, mode='rb'):
        """Lê bytes do Cloudinary: variantes de public_id, image/raw, ``.pdf``, assinatura e Admin API."""
        raw_name = str(name or '').strip().replace('\\', '/')
        if raw_name.startswith(('http://', 'https://')):
            data = self._http_get_binary(raw_name)
            if data:
                fileobj = ContentFile(data)
                fileobj.name = name
                fileobj.mode = mode
                return fileobj
            raise OSError(f'URL direta não retornou dados: {raw_name!r}')

        rtypes = self._resource_types_for_open(name)
        for pub_id in self._public_id_candidates(name):
            pid_variants = self._public_id_fetch_variants(pub_id, name)
            for pid in pid_variants:
                for rtype in rtypes:
                    for url in self._collect_delivery_urls(pid, rtype, name):
                        data = self._http_get_binary(url)
                        if data:
                            fileobj = ContentFile(data)
                            fileobj.name = name
                            fileobj.mode = mode
                            return fileobj
                for rtype in ('image', 'raw'):
                    data = self._open_from_signed_delivery(pid, rtype)
                    if data:
                        fileobj = ContentFile(data)
                        fileobj.name = name
                        fileobj.mode = mode
                        return fileobj
                    if rtype == 'raw' and self._is_pdfish_slug(pid) and not str(pid).lower().endswith('.pdf'):
                        data = self._open_from_signed_delivery(pid, rtype, fmt='pdf')
                        if data:
                            fileobj = ContentFile(data)
                            fileobj.name = name
                            fileobj.mode = mode
                            return fileobj
                api_file = self._open_from_admin_api(pid, name, mode)
                if api_file is not None:
                    return api_file

            listed = self._open_via_admin_list_prefix(pub_id, name, mode)
            if listed is not None:
                return listed

        raise OSError(
            f'Não foi possível abrir {name!r} no Cloudinary '
            f'(extensões, image/raw, API resource e listagem por prefixo)'
        )

    def _upload(self, name, content):
        """No upload usa sempre 'auto' — Cloudinary detecta o melhor tipo."""
        options = {
            'use_filename': True,
            'unique_filename': False,
            'resource_type': 'auto',
            'tags': self.TAG,
        }
        folder = os.path.dirname(name)
        if folder:
            options['folder'] = folder
        return cloudinary.uploader.upload(content, **options)
