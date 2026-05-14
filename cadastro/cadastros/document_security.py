"""
Validação de segurança para uploads de documentos (dados sensíveis).

- Extensões permitidas: .jpg, .jpeg, .jfif, .jpe, .png, .webp, .pdf
- Checagem do Content-Type declarado (lista branca + octet-stream quando a assinatura bate).
- Assinatura binária (magic bytes) para confirmar JPEG, PNG, WebP ou PDF.
- Imagens: Pillow ``verify()`` após ``load()`` para descartar polyglot / lixo.
"""
from io import BytesIO
from typing import Optional, Tuple

from django.core.exceptions import ValidationError
from PIL import Image

# Limite por arquivo (evita ZIP bomb / memória)
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024  # 20 MiB

ALLOWED_EXTENSIONS = frozenset({'jpg', 'jpeg', 'jfif', 'jpe', 'png', 'webp', 'pdf'})

ALLOWED_IMAGE_MIMES = frozenset({
    'image/jpeg',
    'image/pjpeg',
    'image/png',
    'image/webp',
    'image/x-png',
})

ALLOWED_PDF_MIMES = frozenset({
    'application/pdf',
    'application/x-pdf',
})

# Quando o navegador manda genérico mas os magic bytes batem, aceitamos.
GENERIC_MIMES = frozenset({
    '',
    'application/octet-stream',
    'binary/octet-stream',
})


def normalize_extension(filename: str) -> str:
    if not filename or '.' not in filename:
        return ''
    ext = filename.rsplit('.', 1)[-1].lower()
    if ext in ('jfif', 'jpe', 'jpeg'):
        return 'jpg'
    return ext


def detect_binary_kind(header: bytes) -> Optional[str]:
    """Identifica o formato real pelos primeiros bytes. Retorna jpeg | png | webp | pdf."""
    if not header:
        return None
    if header.startswith(b'\xff\xd8\xff'):
        return 'jpeg'
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return 'webp'
    if header.startswith(b'%PDF'):
        return 'pdf'
    return None


def _mime_allows_image(declared: str) -> bool:
    d = (declared or '').split(';')[0].strip().lower()
    if d in GENERIC_MIMES:
        return True
    return d in ALLOWED_IMAGE_MIMES


def _mime_allows_pdf(declared: str) -> bool:
    d = (declared or '').split(';')[0].strip().lower()
    if d in GENERIC_MIMES:
        return True
    return d in ALLOWED_PDF_MIMES


def validate_cliente_document_upload(uploaded_file, field_name: str) -> None:
    """
    Valida extensão, tamanho, MIME declarado, assinatura binária e (para imagem) integridade Pillow.

    `selfie_documento` não aceita PDF.
    Levanta ``django.core.exceptions.ValidationError`` com dict ``{field_name: msg}``.
    """
    if not uploaded_file:
        return

    name = getattr(uploaded_file, 'name', '') or ''
    ext = normalize_extension(name)
    if not ext or ext not in ALLOWED_EXTENSIONS:
        raise ValidationError({
            field_name: 'Envie apenas arquivo .jpg, .jpeg, .png, .webp ou .pdf (formatos permitidos).',
        })

    if field_name == 'selfie_documento' and ext == 'pdf':
        raise ValidationError({
            field_name: 'SELFIE aceita apenas imagem (JPG, PNG ou WebP). PDF não é permitido.',
        })

    size = getattr(uploaded_file, 'size', None)
    if size is not None and size > MAX_DOCUMENT_BYTES:
        raise ValidationError({
            field_name: f'O arquivo excede o tamanho máximo permitido ({MAX_DOCUMENT_BYTES // (1024 * 1024)} MB).',
        })

    declared = (getattr(uploaded_file, 'content_type', '') or '').strip()

    try:
        uploaded_file.seek(0)
        sample = uploaded_file.read(65536)
        uploaded_file.seek(0)
    except Exception as exc:
        raise ValidationError({
            field_name: 'Não foi possível ler o arquivo enviado. Tente novamente.',
        }) from exc

    if not sample:
        raise ValidationError({field_name: 'O arquivo enviado está vazio.'})

    kind = detect_binary_kind(sample[:32])

    if ext == 'pdf':
        if not _mime_allows_pdf(declared):
            raise ValidationError({
                field_name: 'Tipo MIME do PDF não reconhecido. Envie um PDF válido.',
            })
        if kind != 'pdf':
            raise ValidationError({
                field_name: 'O arquivo indicado como PDF não passou na verificação de segurança (assinatura inválida).',
            })
        return

    # Imagem (.jpg / .png / .webp …)
    if not _mime_allows_image(declared):
        raise ValidationError({
            field_name: 'Tipo MIME da imagem não permitido. Use JPG, PNG ou WebP.',
        })

    if kind not in ('jpeg', 'png', 'webp'):
        raise ValidationError({
            field_name: 'O arquivo não é uma imagem válida (JPG, PNG ou WebP) ou foi alterado (assinatura inválida).',
        })

    # Coerência extensão × conteúdo (evita .jpg com PNG dentro para confundir scanners simples)
    if ext == 'jpg' and kind not in ('jpeg',):
        raise ValidationError({
            field_name: 'A extensão .jpg não corresponde ao conteúdo real do arquivo. Renomeie ou reexporte a imagem.',
        })
    if ext == 'png' and kind != 'png':
        raise ValidationError({
            field_name: 'A extensão .png não corresponde ao conteúdo real do arquivo.',
        })
    if ext == 'webp' and kind != 'webp':
        raise ValidationError({
            field_name: 'A extensão .webp não corresponde ao conteúdo real do arquivo.',
        })

    try:
        uploaded_file.seek(0)
        raw = uploaded_file.read()
        uploaded_file.seek(0)
    except Exception as exc:
        raise ValidationError({
            field_name: 'Falha ao ler o arquivo para validação.',
        }) from exc

    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValidationError({
            field_name: f'O arquivo excede o tamanho máximo permitido ({MAX_DOCUMENT_BYTES // (1024 * 1024)} MB).',
        })

    try:
        bio = BytesIO(raw)
        im = Image.open(bio)
        im.load()
        im.verify()
    except Exception:
        raise ValidationError({
            field_name: 'A imagem não pôde ser validada (arquivo corrompido ou não é imagem real).',
        })


# --- Nome de arquivo + MIME (download HTTP e upload IXC) --------------------

# Mesmos sufixos usados em ``get_file_path`` / ``upload_to`` no modelo Cadastro.
DOCUMENTO_CAMPO_TO_STEM = {
    'contrato_social': 'contrato_social',
    'comprovante_residencia': 'comprovante_residencia',
    'foto_documento_frente': 'doc_frente',
    'foto_documento_verso': 'doc_verso',
    'selfie_documento': 'selfie',
}

_EXT_TO_MIME = {
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'webp': 'image/webp',
    'pdf': 'application/pdf',
}


def guess_doc_extension_from_bytes(data: bytes, campo: str) -> str:
    """Extensão real (sem ponto): jpg | png | webp | pdf, a partir dos magic bytes.

    Fallback conservador se o buffer for curto demais: contrato social → pdf;
    demais campos → jpg (pós-pipeline de compressão no app).
    """
    kind = detect_binary_kind((data or b'')[:32])
    if kind == 'jpeg':
        return 'jpg'
    if kind == 'png':
        return 'png'
    if kind == 'webp':
        return 'webp'
    if kind == 'pdf':
        return 'pdf'
    if campo == 'contrato_social':
        return 'pdf'
    return 'jpg'


def build_cliente_document_filename(documento_digits: str, campo: str, ext: str) -> str:
    """Nome estável: ``{CPF/CNPJ só dígitos}_{stem}.{ext}`` (IXC e download)."""
    stem = DOCUMENTO_CAMPO_TO_STEM.get(campo, campo)
    e = (ext or 'jpg').lstrip('.').lower()
    if e in ('jfif', 'jpe', 'jpeg'):
        e = 'jpg'
    if e not in ALLOWED_EXTENSIONS:
        e = 'jpg'
    digits = ''.join(c for c in (documento_digits or '') if c.isdigit())
    if not digits:
        digits = 'sem_documento'
    return f'{digits}_{stem}.{e}'


def mimetype_for_doc_extension(ext: str) -> str:
    e = (ext or '').lstrip('.').lower()
    if e in ('jfif', 'jpe', 'jpeg'):
        e = 'jpg'
    return _EXT_TO_MIME.get(e, 'application/octet-stream')


def prepare_bytes_for_ixc_upload(file_bytes: bytes, field_name: str) -> Tuple[bytes, str, bool]:
    """IXC não aceita WebP: converte raster WebP para JPEG; PDF e demais imagens mantêm.

    Retorna ``(bytes, extensão_sem_ponto, converteu_webp)`` para nome e MIME no multipart.
    """
    data = file_bytes or b''
    if not data:
        return b'', 'jpg', False
    ext = guess_doc_extension_from_bytes(data[:64], field_name)
    if ext != 'webp':
        return data, ext, False
    try:
        bio = BytesIO(data)
        im = Image.open(bio)
        im.load()
        if im.mode in ('RGBA', 'LA', 'P'):
            im = im.convert('RGB')
        elif im.mode != 'RGB':
            im = im.convert('RGB')
        out = BytesIO()
        im.save(out, format='JPEG', quality=90, optimize=True)
        return out.getvalue(), 'jpg', True
    except Exception:
        return data, ext, False
