import requests
import base64
import json
import mimetypes
import os
import re
import unicodedata
from io import BytesIO
from django.conf import settings
from django.utils import timezone

from . import ixc_ids
from .document_security import (
    build_cliente_document_filename,
    mimetype_for_doc_extension,
    prepare_bytes_for_ixc_upload,
)
from .models import only_digits_br


class IXCIntegration:
    """
    Integração outbound com o webservice IXCSoft (IXC Provedor).

    **IDs IXC:** o sistema usa o hub central ``cadastros/ixc_ids.py``, que
    consulta primeiro o painel ``/admin-dash/operacao/`` (banco) e depois cai
    nos DEFAULTS documentados nesse mesmo arquivo (IDs reais de produção
    fornecidos pela operação Fibramar). Nada de IDs hardcoded aqui.
    """

    # Fallback do mapeamento de Canais de Venda (Origens). Use OrigemCanalVenda
    # no painel /admin-dash/ para gerenciar — este dict só roda se o cadastro
    # vier com uma origem que ainda não foi cadastrada lá.
    # Fallback legado — os IDs variam por provedor IXC. Prefira OrigemCanalVenda (Operação) com ixc_id correto.
    ORIGENS_MAP = {
        'Instagram': '6',
        'Facebook': '9',
        'Google': '7',
        'Google Ads': '12',
        'Indicação': '4',
        'Indicação de outros clientes': '4',
        'Indicação de cliente': '9',
        'Amigo': '9',
        'AMIGO': '9',
        'Amigos': '9',
        'Site': '10',
        'WhatsApp': '1',
        'TikTok': '13',
    }
    # Recursos CRM usados só se ``contato`` falhar e IXC_LEAD_AFTER_CONTATO_TRY_CRM=True.
    CRM_LEAD_ORDER_CRM = ['crm_leads', 'crm_sp_leads', 'crm_lead']

    def _crm_lead_resources_to_try(self):
        """Etapa 1 (WS) antes da prospecção em ``crm_canditados``:

        Fluxo por etapas (padrão): **1º** ``contato`` → grava ``ixc_lead_id`` + recurso
        ``contato`` nos logs → **2º** ``crm_canditados`` com ``id_contato_principal`` /
        ``id_contato`` (ver ``create_crm_prospect`` / ``build_crm_prospect_payload``).

        ``IXC_LEAD_RESOURCE``: força um único recurso na etapa 1.

        ``IXC_LEAD_CONTATO_ONLY`` (padrão True): ignora o fallback para ``crm_leads`` — só ``contato``,
        para o IXC não alternar entre ficha simples e pipeline comercial.

        ``IXC_LEAD_AFTER_CONTATO_TRY_CRM``: só é aplicado se ``IXC_LEAD_CONTATO_ONLY=False``; aí, se
        ``contato`` não existir ou falhar no WS, tenta ``crm_leads`` / ``crm_sp_leads`` / ``crm_lead``.
        """
        if self.lead_resource_override:
            return [self.lead_resource_override]
        if self._is_demo_ixc_host():
            return ['contato']
        # Só ``contato``: o fallback para ``crm_leads`` / ``crm_sp_leads`` costuma abrir o fluxo comercial
        # no IXC (venda, contrato) de forma inconsistente. Use IXC_LEAD_RESOURCE se precisar de outro WS.
        if getattr(settings, 'IXC_LEAD_CONTATO_ONLY', True):
            return ['contato']
        out = ['contato']
        if getattr(settings, 'IXC_LEAD_AFTER_CONTATO_TRY_CRM', False):
            for r in self.CRM_LEAD_ORDER_CRM:
                if r not in out:
                    out.append(r)
        return out

    def crm_lead_resources_for_export(self):
        """Nomes WS da etapa 1 (debug / export JSON)."""
        return self._crm_lead_resources_to_try()

    def _crm_prospect_resources_to_try(self):
        """Recursos WS da etapa 2 (painel). Ordem: IXC_CRM_PROSPECT_RESOURCE (um só) senão
        ``crm_canditados`` / ``crm_candidatos`` (Postman IXC Provedor — prospecção CRM),
        depois ``crm_prospect`` (legado) + IXC_CRM_PROSPECT_FALLBACK_RESOURCES.
        """
        override = (getattr(settings, 'IXC_CRM_PROSPECT_RESOURCE', None) or '').strip()
        if override:
            return [override]
        fallbacks_raw = (getattr(settings, 'IXC_CRM_PROSPECT_FALLBACK_RESOURCES', '') or '').strip()
        extra = [x.strip() for x in fallbacks_raw.split(',') if x.strip()]
        base = ['crm_canditados', 'crm_candidatos', 'crm_prospect']
        seen = set()
        out = []
        for name in base + extra:
            if name not in seen:
                seen.add(name)
                out.append(name)
        return out

    def _crm_candidatos_resources_to_try(self):
        """Recursos WS para CRM candidatos. Ordem: IXC_CRM_CANDIDATOS_RESOURCE senão
        ``crm_canditados`` (typo URL IXC) + ``crm_candidatos`` + fallbacks do .env.
        """
        override = (getattr(settings, 'IXC_CRM_CANDIDATOS_RESOURCE', None) or '').strip()
        if override:
            return [override]
        fallbacks_raw = (getattr(settings, 'IXC_CRM_CANDIDATOS_FALLBACK_RESOURCES', '') or '').strip()
        extra = [x.strip() for x in fallbacks_raw.split(',') if x.strip()]
        base = ['crm_canditados', 'crm_candidatos']
        seen = set()
        out = []
        for name in base + extra:
            if name not in seen:
                seen.add(name)
                out.append(name)
        return out

    @staticmethod
    def _crm_etapa2_resource_uses_candidatos_payload(resource):
        """POST em ``crm_canditados`` / ``crm_candidatos`` exige o modelo do Postman (``build_crm_candidatos_payload``)."""
        r = (resource or '').strip().lower()
        return r in ('crm_canditados', 'crm_candidatos')

    def __init__(self):
        self.url = self._normalize_base_url(getattr(settings, 'IXC_API_URL', ''))
        self.token = getattr(settings, 'IXC_API_TOKEN', '')
        self.lead_resource_override = (getattr(settings, 'IXC_LEAD_RESOURCE', '') or '').strip()
        self.lead_post_alterar = bool(getattr(settings, 'IXC_LEAD_POST_ALTERAR', False))
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': self._build_authorization_header(self.token)
        }

    @staticmethod
    def _normalize_base_url(url):
        clean_url = (url or '').strip().rstrip('/')
        if clean_url.endswith('/adm.php'):
            clean_url = clean_url[:-8]
        return clean_url

    def _is_demo_ixc_host(self):
        return 'demo.ixcsoft.com.br' in (self.url or '').lower()

    @staticmethod
    def _ixc_fk_value(val):
        """IXC costuma gravar FKs como inteiro no JSON; None omite o campo."""
        if val is None:
            return None
        s = str(val).strip()
        if not s:
            return None
        if s.isdigit():
            return int(s, 10)
        return s

    def _ixc_alterar_mesmo_payload(self, resource, lead_id, full_payload):
        """IXC no `alterar` exige o registro completo (Filial, Nome, data, fones…); não aceita só id + FKs."""
        body = dict(full_payload)
        body['id'] = str(lead_id)
        endpoint = f"{self.url}/webservice/v1/{resource}"
        return self._post_ixc(
            endpoint,
            body,
            'CRM_LEAD_ALTER',
            extra_headers={'ixcsoft': 'alterar'},
        )

    @staticmethod
    def _build_authorization_header(token):
        clean_token = (token or '').strip()
        if not clean_token:
            return ''
        if clean_token.count('.') == 2 and ':' not in clean_token:
            return f'Bearer {clean_token}'
        encoded = base64.b64encode(clean_token.encode('utf-8')).decode('ascii')
        return f'Basic {encoded}'

    def _save_debug_json(self, cadastro_id, payload, etapa):
        """Grava JSON de auditoria FORA de MEDIA_ROOT (logs/ixc_debug/)."""
        try:
            debug_dir = os.path.join(settings.BASE_DIR, 'logs', 'ixc_debug')
            os.makedirs(debug_dir, exist_ok=True)

            filename = f"debug_id_{cadastro_id}_{etapa}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(debug_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=4, ensure_ascii=False)
            return filepath
        except Exception:
            return None

    def _post_ixc(self, endpoint, payload, etapa, extra_headers=None):
        err_logs = [
            f'[{etapa}] endpoint={endpoint}',
            f'[{etapa}] auth={"ok" if bool(self.token) else "ausente"}',
        ]
        headers = {**self.headers, **(extra_headers or {})}
        try:
            response = requests.post(endpoint, json=payload, headers=headers, verify=False, timeout=30)
            err_logs.append(f'[{etapa}] status_http={response.status_code}')

            if response.status_code in [200, 201]:
                raw_text = (response.text or '').strip()
                if not raw_text:
                    return {
                        'status': 'success',
                        'data': {},
                        'logs': [],
                        'http_status': response.status_code,
                    }
                try:
                    body = response.json()
                except ValueError:
                    preview = (response.text or '').strip()[:500]
                    err_logs.append(f'[{etapa}] resposta_nao_json: {preview}')
                    return {
                        'status': 'error',
                        'message': 'Resposta HTTP 200/201 sem JSON válido (IXC ou proxy).',
                        'logs': err_logs,
                        'http_status': response.status_code,
                        'endpoint': endpoint,
                    }
                return {
                    'status': 'success',
                    'data': body,
                    'logs': [],
                    'http_status': response.status_code,
                }

            error_preview = (response.text or '').strip()[:500]
            err_logs.append(f'[{etapa}] erro: {error_preview}')
            return {
                'status': 'error',
                'message': error_preview or f'Falha HTTP {response.status_code}',
                'logs': err_logs,
                'http_status': response.status_code,
                'endpoint': endpoint,
            }
        except requests.RequestException as e:
            err_logs.append(f'[{etapa}] excecao: {str(e)}')
            return {
                'status': 'error',
                'message': f'Falha na conexão: {str(e)}',
                'logs': err_logs,
                'endpoint': endpoint,
            }

    @staticmethod
    def _extract_id(data):
        if isinstance(data, dict):
            for key in (
                'id',
                'id_lead',
                'id_cliente',
                'idcrm_leads',
                'id_prospect',
                'idcrm_prospect',
                'id_crm_prospect',
                'idcrm_canditados',
                'id_crm_canditados',
                'idcrm_candidatos',
                'id_crm_candidatos',
                'id_candidato',
            ):
                value = data.get(key)
                if value not in (None, '', 0, '0'):
                    return value
            for value in data.values():
                found = IXCIntegration._extract_id(value)
                if found not in (None, '', 0, '0'):
                    return found
        elif isinstance(data, list):
            for item in data:
                found = IXCIntegration._extract_id(item)
                if found not in (None, '', 0, '0'):
                    return found
        return None

    @staticmethod
    def _extract_cliente_contrato_id(body):
        """ID do contrato no retorno do POST ``cliente_contrato`` (incluir). Não usa ``id_cliente``."""
        if not isinstance(body, dict):
            return None
        for key in (
            'id_contrato',
            'id_cliente_contrato',
            'idcrm_cliente_contrato',
            'id_crm_cliente_contrato',
            'id',
        ):
            v = body.get(key)
            if v not in (None, '', 0, '0'):
                return v
        for k, v in body.items():
            if not isinstance(k, str) or v in (None, '', 0, '0'):
                continue
            tail = k.split('.')[-1].lower()
            if tail in ('id_contrato', 'id_cliente_contrato'):
                return v
        return None

    @staticmethod
    def _is_resource_unavailable(result):
        message_text = f"{result.get('message', '')}".lower()
        data = result.get('data')
        if isinstance(data, dict):
            response_message = str(data.get('message', '')).lower()
            response_type = str(data.get('type', '')).lower()
            if response_type == 'error':
                message_text = f"{message_text} {response_message}".strip()
            else:
                message_text = f"{message_text} {response_message}".strip()
        return 'recurso' in message_text and 'não está disponível' in message_text

    def _search_ixc_by_document(self, resource, documento):
        endpoint = f"{self.url}/webservice/v1/{resource}"
        qtypes = [
            f"{resource}.cnpj_cpf",
            "cnpj_cpf",
            f"{resource}.cpf_cnpj",
            "cpf_cnpj",
            "documento",
        ]
        for qtype in qtypes:
            payload = {
                'qtype': qtype,
                'query': documento,
                'oper': '=',
                'page': '1',
                'rp': '1',
                'sortname': 'id',
                'sortorder': 'desc',
            }
            result = self._post_ixc(endpoint, payload, 'DUPLICIDADE')
            data = result.get('data') if result.get('status') == 'success' else None
            if not isinstance(data, dict):
                continue
            if str(data.get('type', '')).lower() == 'error':
                continue

            # Formatos comuns de listagem da API IXC.
            registros = data.get('registros')
            if isinstance(registros, list) and registros:
                return registros[0], qtype
            records = data.get('records')
            if isinstance(records, list) and records:
                return records[0], qtype
            if data.get('total') not in (None, '', 0, '0'):
                return data, qtype
        return None, None

    def check_duplicate_before_create(self, cadastro):
        if not self.url or not self.token:
            return {'status': 'ok', 'message': 'API do IXC não configurada.'}

        documento = ''.join(ch for ch in str(cadastro.documento or '') if ch.isdigit())
        if not documento:
            return {'status': 'ok', 'message': 'Documento ausente para checagem.'}

        resources = ['contato', 'cliente']
        for resource in resources:
            found, qtype = self._search_ixc_by_document(resource, documento)
            if found:
                found_id = self._extract_id(found)
                logs = [
                    f'[DUPLICIDADE] documento={documento}',
                    f'[DUPLICIDADE] encontrado em {resource} qtype={qtype} id={found_id}',
                ]
                return {
                    'status': 'duplicate',
                    'message': f'Duplicidade no IXC: documento já existe em {resource}.',
                    'resource': resource,
                    'found_id': found_id,
                    'logs': logs,
                }

        return {'status': 'ok', 'message': 'Sem duplicidade no IXC.', 'logs': []}

    def resolve_filial_id(self, cidade_slug):
        """Filial IXC pela cidade: painel Operação > defaults `ixc_ids.FILIAIS`."""
        return ixc_ids.get_filial_id(cidade_slug) or '2'

    def _resolve_vendedor_ixc(self, cadastro):
        """Resolve o VendedorIXC efetivo para o cadastro.

        Prioridade:
            1) `cadastro.vendedor_responsavel` (FK manual no Cadastro — override).
            2) `cadastro.consultor.vendedor_ixc` (consultor logado tem vínculo IXC).
            3) `VendedorIXC` marcado como `padrao=True` no painel.
            4) None (cai no fallback do .env nas integrações).
        """
        vend = getattr(cadastro, 'vendedor_responsavel', None)
        if vend and getattr(vend, 'ixc_id', '').strip():
            return vend
        consultor = getattr(cadastro, 'consultor', None)
        vend = getattr(consultor, 'vendedor_ixc', None) if consultor else None
        if vend and getattr(vend, 'ixc_id', '').strip() and getattr(vend, 'ativo', True):
            return vend
        try:
            from .operacao_models import VendedorIXC
            return VendedorIXC.objects.filter(ativo=True, padrao=True).first()
        except Exception:
            return None

    @staticmethod
    def _tipo_letra_ixc_from_valor_bruto(v):
        """Converte valor vindo do IXC (letra, dígito, «Internet», …) para a letra usada em ``cliente_contrato.tipo``."""
        if v in (None, '', 0, '0'):
            return ''
        s = str(v).strip()
        if not s:
            return ''
        sl = s.lower()
        # Rótulos da tela IXC (Tipo: Internet / Telefonia / Serviços / SVA)
        word_map = {
            'internet': 'I',
            'telefonia': 'T',
            'servicos': 'S',
            'serviços': 'S',
            'sva': 'V',
        }
        if sl in word_map:
            return word_map[sl]
        # Algumas bases gravam só a letra ou dígito
        if sl in ('i', 't', 's', 'v'):
            return sl.upper()
        # Padrão comum: 1=Internet, 2=Telefonia, 3=Serviços, 4=SVA (ajuste no IXC se divergir)
        digit_map = {'1': 'I', '2': 'T', '3': 'S', '4': 'V'}
        if len(s) == 1 and s in digit_map:
            return digit_map[s]
        if len(s) == 1:
            return s.upper()
        if s[0].isalpha():
            return s[0].upper()
        return ''

    @staticmethod
    def _tipo_ixc_from_vd_sale_plan_row(row):
        """Extrai ``tipo`` (I/T/S/V) da linha do **plano de venda** (vd_contrato).

        Não use linha de ``cliente_contrato`` para isso: o ``tipo`` ali costuma ser do contrato,
        não do vd — reaproveitar gera ``tipo`` errado e o IXC acusa diferença em relação ao vd.
        """
        if not isinstance(row, dict):
            return ''
        prioritized = (
            'tipo',
            'tipo_contrato',
            'tipo_plano',
            'tipo_produtos_plano',
            'tipo_servico',
            'tipo_internet',
            'td_tipo',
            'tipo_contrato_vd',
            'classificacao',
        )
        for key in prioritized:
            t = IXCIntegration._tipo_letra_ixc_from_valor_bruto(row.get(key))
            if t:
                return t
        # Qualquer coluna cujo nome sugira «tipo» (vd_contrato.tipo, …)
        for k, v in row.items():
            if not isinstance(k, str):
                continue
            kl = k.lower()
            if 'tipo' not in kl:
                continue
            t = IXCIntegration._tipo_letra_ixc_from_valor_bruto(v)
            if t:
                return t
        return ''

    def _fetch_vd_contrato_row_by_id(self, id_vd):
        """Listar **somente** ``vd_contrato`` por id do plano de venda (para ``tipo`` coerente no incluir)."""
        logs = []
        vid = str(id_vd or '').strip()
        if not vid or not self.url or not self.token:
            return None, logs
        resource = (getattr(settings, 'IXC_VD_CONTRATO_RESOURCE', None) or 'vd_contrato').strip()
        endpoint = f'{self.url}/webservice/v1/{resource}'
        qtypes = (
            'id',
            'vd_contrato.id',
            'vd_contrato.id_vd_contrato',
            'vd_contrato.id_vd',
            'id_vd_contrato',
            'id_vd',
        )
        for qtype in qtypes:
            payload = {
                'qtype': qtype,
                'query': vid,
                'oper': '=',
                'page': '1',
                'rp': '30',
                'sortname': 'id',
                'sortorder': 'desc',
            }
            result = self._post_ixc(
                endpoint,
                payload,
                'VD_CONTRATO_TIPO_SYNC',
                extra_headers={'ixcsoft': 'listar'},
            )
            if result.get('status') != 'success':
                logs.append(
                    f'[VD_CONTRATO] listar qtype={qtype} http: {(result.get("message") or "")[:100]}'
                )
                continue
            data = result.get('data')
            if not isinstance(data, dict) or str(data.get('type', '')).lower() == 'error':
                msg = str(data.get('message', ''))[:120] if isinstance(data, dict) else ''
                logs.append(f'[VD_CONTRATO] listar qtype={qtype} erro_api: {msg}')
                continue
            rows = data.get('registros')
            if not isinstance(rows, list):
                rows = data.get('records')
            if not isinstance(rows, list) or not rows:
                continue
            for r in rows:
                if not isinstance(r, dict):
                    continue
                rid = str(
                    r.get('id')
                    or r.get('id_vd_contrato')
                    or r.get('id_vd')
                    or ''
                ).strip()
                if rid == vid:
                    logs.append(f'[VD_CONTRATO] linha id={rid} qtype={qtype}')
                    return r, logs
            if rows and isinstance(rows[0], dict):
                logs.append(f'[VD_CONTRATO] aviso: nenhum id exato {vid}; usando primeira linha qtype={qtype}')
                return rows[0], logs
        logs.append('[VD_CONTRATO] sem linha para este id (vd indisponível ou id inválido).')
        return None, logs

    @staticmethod
    def _merge_cliente_contrato_campos_do_vd(payload, vd_row):
        """Copia do ``vd_contrato`` campos que o IXC cruza com o contrato (evita ``tipo``/FK incoerentes)."""
        if not isinstance(vd_row, dict) or not isinstance(payload, dict):
            return
        id_tc = None
        for pref in ('id_tipo_contrato',):
            v = vd_row.get(pref)
            if v not in (None, '', 0, '0'):
                id_tc = str(v).strip()
                break
        if not id_tc:
            for k, v in vd_row.items():
                if not isinstance(k, str) or v in (None, '', 0, '0'):
                    continue
                if k.split('.')[-1].lower() == 'id_tipo_contrato':
                    id_tc = str(v).strip()
                    break
        if not id_tc:
            for k, v in vd_row.items():
                if not isinstance(k, str) or v in (None, '', 0, '0'):
                    continue
                kl = k.lower()
                if 'id' in kl and 'tipo' in kl and 'contrato' in kl and 'document' not in kl:
                    sv = str(v).strip()
                    if sv.isdigit():
                        id_tc = sv
                    break
        if id_tc:
            payload['id_tipo_contrato'] = id_tc
        tpm = vd_row.get('tipo_produtos_plano')
        if tpm in (None, '', 0, '0'):
            for k, v in vd_row.items():
                if not isinstance(k, str) or v in (None, '', 0, '0'):
                    continue
                if 'tipo_produtos' in k.lower():
                    tpm = v
                    break
        if tpm not in (None, '', 0, '0'):
            payload['tipo_produtos_plano'] = str(tpm).strip()

    def _resolve_tipo_contrato_alinhado_ao_plano_venda(self, id_vd, fallback_tipo):
        """Retorna (``tipo`` para o POST, linha ``vd_contrato`` ou None) — regra IXC contrato vs plano."""
        vid = str(id_vd or '').strip()
        fb = (fallback_tipo or 'I').strip() or 'I'
        if not vid or not self.url or not self.token:
            return fb, None
        row, _logs = self._fetch_vd_contrato_row_by_id(vid)
        if row:
            t = IXCIntegration._tipo_ixc_from_vd_sale_plan_row(row)
            if t:
                return t, row
            return fb, row
        return fb, None

    def resolve_cidade_ixc_id(self, cidade_slug):
        """Cidade IXC: painel Operação > defaults `ixc_ids.CIDADES_IXC`."""
        return ixc_ids.get_cidade_ixc_id(cidade_slug) or ''

    def resolve_setor_id(self, cidade_slug):
        """Setor IXC (id_setor): painel Operação > defaults `ixc_ids.SETORES`."""
        return ixc_ids.get_setor_id(cidade_slug) or ''

    def resolve_carteira_cobranca_id(self, cidade_slug):
        """Carteira de cobrança IXC: painel Operação > defaults `ixc_ids.CARTEIRAS_POR_CIDADE`."""
        return ixc_ids.get_carteira_cobranca_id(cidade_slug) or ''

    def resolve_tipo_doc_ativ_id(self, cidade_slug):
        """Tipo de doc opcional (ativação) IXC: painel Operação > defaults por filial."""
        return ixc_ids.get_tipo_doc_ativ_id(cidade_slug) or ''

    def resolve_vencimento_id(self, cidade_slug, dia_str):
        """ID da cobrança (id_carencia) por dia: painel Operação > defaults por filial."""
        return ixc_ids.get_vencimento_id(cidade_slug, dia_str) or ''

    def resolve_plano_venda_id(self, cidade_slug, plano_codigo):
        """ID do plano de venda (vd): Operação > defaults `ixc_ids.PLANOS_POR_FILIAL`.

        Mantém compatibilidade com ``IXC_FORCE_PLANO_VENDA_ID`` (override de emergência por ambiente).
        """
        force = (getattr(settings, 'IXC_FORCE_PLANO_VENDA_ID', None) or '').strip()
        if force:
            return force
        return ixc_ids.get_plano_venda_id(cidade_slug, plano_codigo) or ''

    def resolve_canal_venda_id(self, origem_label):
        """Canal de venda no IXC a partir da origem da ficha: Operação (OrigemCanalVenda) > .env > mapa legado."""
        force = (getattr(settings, 'IXC_FORCE_CANAL_VENDA_ID', None) or '').strip()
        if force:
            return force
        label = (origem_label or '').strip()
        if label:
            try:
                from .operacao_models import OrigemCanalVenda

                o = OrigemCanalVenda.objects.filter(ativo=True, label__iexact=label).first()
                if o and (o.ixc_id or '').strip():
                    return o.ixc_id.strip()
            except Exception:
                pass
            ll = label.lower()
            for k, v in self.ORIGENS_MAP.items():
                if k.lower() == ll:
                    return v
        default_env = (getattr(settings, 'IXC_DEFAULT_CANAL_VENDA_ID', None) or '').strip()
        return default_env

    def _resolve_plano_e_canal_venda(self, cadastro):
        """Tupla (id_plano_venda, id_canal_venda, id_campanha) para payloads comerciais (ex.: teste cliente_contrato)."""
        id_plano = (
            self.resolve_plano_venda_id(
                getattr(cadastro, 'cidade', None), getattr(cadastro, 'plano', None)
            )
            or ''
        ).strip()
        id_canal = (self.resolve_canal_venda_id(getattr(cadastro, 'origem', None)) or '').strip()
        if getattr(settings, 'IXC_SEND_CANAL_AS_ID_CAMPANHA', False) and id_canal:
            id_campanha = id_canal
        else:
            id_campanha = (
                (getattr(settings, 'IXC_FORCE_CAMPANHA_ID', None) or '').strip()
                or (getattr(settings, 'IXC_DEFAULT_CAMPANHA_ID', None) or '').strip()
            )
        return id_plano, id_canal, id_campanha

    @staticmethod
    def _ixc_display_pii(cadastro):
        """CPF/CNPJ, CEP e telefone no padrão BR para o IXC exibir corretamente."""
        from .models import (
            format_cep_display,
            format_cnpj_display,
            format_cpf_display,
            format_telefone_display,
            only_digits_br,
        )

        doc = only_digits_br(cadastro.documento)
        if getattr(cadastro, 'tipo_pessoa', 'pf') == 'pj':
            doc_display = format_cnpj_display(doc)
        else:
            doc_display = format_cpf_display(doc)

        cep_d = only_digits_br(cadastro.cep)
        cep_display = format_cep_display(cep_d) if len(cep_d) == 8 else (cadastro.cep or '').strip()

        tel_d = only_digits_br(cadastro.telefone)
        if tel_d.startswith('55') and len(tel_d) >= 12:
            tel_d = tel_d[2:]
        tel_display = format_telefone_display(tel_d) if tel_d else ''

        return doc_display, cep_display, tel_display

    def build_crm_lead_payload(self, cadastro):
        id_filial = self.resolve_filial_id(cadastro.cidade)
        id_cidade = self.resolve_cidade_ixc_id(cadastro.cidade)
        ixc_data = cadastro.get_ixc_data()
        doc_display, cep_display, tel_display = self._ixc_display_pii(cadastro)
        tipo_ixc = 'J' if getattr(cadastro, 'tipo_pessoa', 'pf') == 'pj' else 'F'

        payload = {
            'id_filial': id_filial,
            'contato': ixc_data['nome_razao'].upper(),
            'nome': ixc_data['nome_razao'].upper(),
            'razao': ixc_data['nome_razao'].upper(),
            'ativo': 'S',
            'principal': 'S',
            'tipo_contato': 'L',
            'tipo': 'L',
            'tipo_pessoa': tipo_ixc,
            'data_cadastro': cadastro.data_cadastro.strftime('%d/%m/%Y %H:%M:%S') if cadastro.data_cadastro else timezone.now().strftime('%d/%m/%Y %H:%M:%S'),
            'cnpj_cpf': doc_display,
            'fone_residencial': tel_display,
            'fone_comercial': tel_display,
            'fone_movel': tel_display,
            'telefone_celular': tel_display,
            'fone_celular': tel_display,
            'whatsapp': tel_display,
            'fone_whatsapp': tel_display,
            'celular_whatsapp': tel_display,
            'email': cadastro.email.lower(),
            'data_nascimento': cadastro.data_nascimento.strftime('%d/%m/%Y') if cadastro.data_nascimento else '',
            'nascimento': cadastro.data_nascimento.strftime('%d/%m/%Y') if cadastro.data_nascimento else '',
            # Sem texto de plano/origem — o IXC pode interpretar como gatilho comercial.
            'descricao': f'PORTAL_WEB cadastro_id={cadastro.pk}'.upper(),
            'cep': cep_display,
            'endereco': ixc_data['endereco'].upper(),
            'numero': ixc_data['numero'].upper(),
            'bairro': ixc_data['bairro'].upper(),
            'complemento': ixc_data['complemento'].upper(),
            'cidade': id_cidade or cadastro.cidade.upper(),
            'uf': (cadastro.uf or '').upper(),
            'referencia': ixc_data['referencia'].upper(),
        }
        # Sem FKs de plano/canal/campanha/contrato — só ficha CRM (evita venda automática no IXC).
        return payload

    def build_crm_prospect_payload(self, cadastro, *, link_contato_id=None, ixc_lead_resource=None):
        """Monta JSON para prospecção CRM. Sem FKs de venda — ficha + vínculo ao lead/contato."""
        id_filial = self.resolve_filial_id(cadastro.cidade)
        id_cidade = self.resolve_cidade_ixc_id(cadastro.cidade)
        ixc_data = cadastro.get_ixc_data()
        doc_display, cep_display, tel_display = self._ixc_display_pii(cadastro)
        tipo_ixc = 'J' if getattr(cadastro, 'tipo_pessoa', 'pf') == 'pj' else 'F'
        idf = self._ixc_fk_value(id_filial) if str(id_filial).strip().isdigit() else id_filial
        fantasia = ((cadastro.nome_fantasia or '').strip() or ixc_data['nome_razao']).upper()
        if getattr(cadastro, 'tipo_pessoa', 'pf') == 'pj':
            ie_ident = ((cadastro.inscricao_estadual or '').strip()).upper()
        else:
            ie_ident = str(cadastro.rg or '').strip().upper()

        payload = {
            'razao': ixc_data['nome_razao'].upper(),
            'fantasia': fantasia,
            'ie_identidade': ie_ident,
            'nome': ixc_data['nome_razao'].upper(),
            'contato': None,
            'tipo_pessoa': tipo_ixc,
            'id_filial': idf,
            'ativo': 'S',
            'data_cadastro': (
                cadastro.data_cadastro.strftime('%d/%m/%Y %H:%M:%S')
                if cadastro.data_cadastro
                else timezone.now().strftime('%d/%m/%Y %H:%M:%S')
            ),
            'cnpj_cpf': doc_display,
            'email': cadastro.email.lower(),
            'fone': tel_display,
            'fone_celular': tel_display,
            'fone_residencial': tel_display,
            'fone_comercial': tel_display,
            'telefone_comercial': tel_display,
            'fone_movel': tel_display,
            'telefone_celular': tel_display,
            'whatsapp': tel_display,
            'fone_whatsapp': tel_display,
            'celular_whatsapp': tel_display,
            'cep': cep_display,
            'endereco': ixc_data['endereco'].upper(),
            'numero': ixc_data['numero'].upper(),
            'bairro': ixc_data['bairro'].upper(),
            'complemento': ixc_data['complemento'].upper(),
            'cidade': id_cidade or str(cadastro.cidade or '').upper(),
            'uf': (cadastro.uf or '').upper(),
            'referencia': ixc_data['referencia'].upper(),
            # Só vínculo interno; sem plano/origem (evita sinal de venda no CRM IXC).
            'descricao': f'PORTAL_WEB cadastro_id={cadastro.pk}'.upper(),
        }
        if cadastro.data_nascimento:
            payload['data_nascimento'] = cadastro.data_nascimento.strftime('%d/%m/%Y')
            payload['nascimento'] = cadastro.data_nascimento.strftime('%d/%m/%Y')

        lid = None
        if link_contato_id not in (None, '', 0, '0'):
            lid = self._ixc_fk_value(str(link_contato_id).strip())
        res = (ixc_lead_resource or '').strip().lower()
        if lid is not None:
            if res in ('contato', 'local', ''):
                payload['id_contato'] = lid
            elif res in ('crm_leads', 'crm_sp_leads', 'crm_lead'):
                payload['id_lead'] = lid
            else:
                payload['id_contato'] = lid
        return payload

    def build_crm_candidatos_payload(self, cadastro, *, link_contato_id=None, ixc_lead_resource=None):
        """Monta o JSON do POST ``crm_canditados`` conforme o modelo do IXC Provedor (Postman).

        Referência: `API - IXC Provedor` — inclusão em ``/webservice/v1/crm_canditados``
        (obrigatórios: ``razao``, ``status_prospeccao``, ``tipo_pessoa``, ``cidade``, ``ativo``,
        ``crm``; e na prática **pelo menos um** de ``telefone_celular`` / ``fone`` / ``email``).

        Campos comerciais opcionais (``id_vd_contrato_desejado``, ``id_campanha``, …) permanecem
        como string vazia ``''`` para não amarrar venda.
        """
        from .models import only_digits_br

        id_filial = self.resolve_filial_id(cadastro.cidade)
        id_cidade = self.resolve_cidade_ixc_id(cadastro.cidade)
        ixc_data = cadastro.get_ixc_data()
        doc_display, cep_display, tel_display = self._ixc_display_pii(cadastro)
        tipo_ixc = 'J' if getattr(cadastro, 'tipo_pessoa', 'pf') == 'pj' else 'F'

        tel_digits = only_digits_br(cadastro.telefone)
        if tel_digits.startswith('55') and len(tel_digits) >= 12:
            tel_digits = tel_digits[2:]
        email_l = (cadastro.email or '').strip().lower()

        # Doc: celular costuma ir só com dígitos; se não houver telefone mas houver e-mail, ok.
        cel_ixc = tel_digits
        if not cel_ixc and not email_l:
            cel_ixc = '11999999999'

        id_cidadex = (id_cidade or '').strip()
        if id_cidadex.isdigit():
            cidade_str = str(id_cidadex)
        else:
            cidade_str = (getattr(settings, 'IXC_CRM_CANDIDATOS_CIDADE_FALLBACK', None) or '1').strip() or '1'

        filial_str = str(id_filial).strip() if str(id_filial).strip() else ''
        setor_str = (self.resolve_setor_id(cadastro.cidade) or '').strip()
        razao = (ixc_data.get('nome_razao') or '').strip().upper() or 'CADASTRO_WEB'
        fantasia = ((cadastro.nome_fantasia or '').strip() or (ixc_data.get('nome_razao') or '').strip()).upper()
        # Vendedor responsável: ficha (override) > consultor logado vinculado > VendedorIXC padrão.
        vendedor = self._resolve_vendedor_ixc(cadastro)
        vendedor_ixc_id = (str(vendedor.ixc_id).strip() if vendedor and vendedor.ixc_id else '')
        vendedor_resp_id = (str(vendedor.responsavel_ixc_id).strip() if vendedor and vendedor.responsavel_ixc_id else vendedor_ixc_id)
        vendedor_nome = (vendedor.nome.upper() if vendedor and vendedor.nome else '')
        if getattr(cadastro, 'tipo_pessoa', 'pf') == 'pj':
            ie_ident = ((cadastro.inscricao_estadual or '').strip()).upper()
        else:
            ie_ident = str(cadastro.rg or '').strip().upper()

        dt_cad = (
            cadastro.data_cadastro.strftime('%d/%m/%Y %H:%M:%S')
            if cadastro.data_cadastro
            else timezone.now().strftime('%d/%m/%Y %H:%M:%S')
        )
        dt_nasc = cadastro.data_nascimento.strftime('%d/%m/%Y') if cadastro.data_nascimento else ''

        payload = {
            'razao': razao,
            'fantasia': fantasia,
            # Nome do campo conforme exemplo do Postman (IXC Provedor); algumas bases aceitam também ``id_candidato_tipo``.
            'id_candato_tipo': '',
            'id_campanha': '',
            'id_concorrente': '',
            'id_perfil': '',
            # Em `crm_canditados` o `responsavel` é texto (nome) e o IXC tem
            # um campo numérico separado (`id_responsavel`). Mandamos os dois
            # para que a tela do IXC apareça preenchida tanto na visualização
            # quanto na busca/relatório.
            'responsavel': vendedor_nome,
            'id_responsavel': vendedor_resp_id,
            'indicado_por': '',
            'status_prospeccao': 'N',
            'tipo_pessoa': tipo_ixc,
            'cnpj_cpf': doc_display,
            'ie_identidade': ie_ident,
            'data_nascimento': dt_nasc,
            'filial_id': filial_str,
            'id_setor': setor_str,
            'ativo': 'S',
            'data_cadastro': dt_cad,
            'prospeccao_ultimo_contato': '',
            'prospeccao_proximo_contato': '',
            'id_vendedor': vendedor_ixc_id,
            'id_conta': '',
            'id_vd_contrato_desejado': '',
            'cadastrado_via_viabilidade': '',
            'id_contato_principal': '',
            'fone': tel_digits,
            'telefone_comercial': tel_digits,
            'telefone_celular': cel_ixc,
            'whatsapp': tel_digits,
            'ramal': '',
            'email': email_l,
            'contato': '',
            'website': '',
            'skype': '',
            'facebook': '',
            'id_condominio': '',
            'bloco': '',
            'apartamento': '',
            'cep': cep_display,
            'endereco': (ixc_data.get('endereco') or '').upper(),
            'numero': (ixc_data.get('numero') or '').upper(),
            'bairro': (ixc_data.get('bairro') or '').upper(),
            'cidade': cidade_str,
            'complemento': (ixc_data.get('complemento') or '').upper(),
            'referencia': (ixc_data.get('referencia') or '').upper(),
            'uf': (cadastro.uf or '').upper(),
            'moradia': '',
            'tipo_localidade': '',
            'latitude': '',
            'longitude': '',
            'external_id': '',
            'external_system': '',
            'crm': 'S',
            'pipe_id_organizacao': '',
            'idx': '',
            'crm_data_novo': '',
            'crm_data_sondagem': '',
            'crm_data_apresentando': '',
            'crm_data_negociando': '',
            'crm_data_vencemos': '',
            'crm_data_perdemos': '',
            'crm_data_abortamos': '',
            'crm_data_sem_viabilidade': '',
            'crm_data_sem_porta_disponivel': '',
            # Observação mínima; sem plano/origem (não alimentar automações comerciais no IXC).
            'obs': f'PORTAL_WEB cadastro_id={cadastro.pk}'.upper()[:500],
            'alerta': '',
            'status_viabilidade': '',
            'tipo_rede': '',
            'rede_ativacao': '',
            'operador_neutro': '',
            'resultado_calc_vel': '',
            'qtd_pessoas_calc_vel': '',
            'qtd_smart_calc_vel': '',
            'qtd_celular_calc_vel': '',
            'qtd_computador_calc_vel': '',
            'qtd_console_calc_vel': '',
            'plano_negociacao_auto_viab': '',
            'tipo_cobranca_auto_viab': '',
            'data_reserva_auto_viab': '',
        }

        lid = None
        if link_contato_id not in (None, '', 0, '0'):
            lid = self._ixc_fk_value(str(link_contato_id).strip())
        res = (ixc_lead_resource or '').strip().lower()
        if lid is not None:
            if res in ('crm_leads', 'crm_sp_leads', 'crm_lead'):
                payload['id_lead'] = str(lid)
            else:
                payload['id_contato_principal'] = str(lid)

        return payload

    def create_crm_candidatos(self, cadastro, *, link_contato_id=None, ixc_lead_resource=None, force=False):
        """Cria ``crm_canditados`` / ``crm_candidatos``. ``force=True`` ignora IXC_CREATE_CRM_CANDIDATOS."""
        if not force and not getattr(settings, 'IXC_CREATE_CRM_CANDIDATOS', True):
            return {
                'status': 'skipped',
                'message': 'IXC_CREATE_CRM_CANDIDATOS=False',
                'logs': ['[CRM_CANDIDATOS] desativado nas configurações.'],
            }
        if not self.url or not self.token:
            return {
                'status': 'error',
                'message': 'API do IXC não configurada.',
                'logs': ['[CRM_CANDIDATOS] IXC_API_URL/IXC_API_TOKEN ausentes.'],
            }
        payload = self.build_crm_candidatos_payload(
            cadastro,
            link_contato_id=link_contato_id,
            ixc_lead_resource=ixc_lead_resource,
        )
        debug_path = self._save_debug_json(cadastro.pk, payload, 'CRM_CANDIDATOS')
        all_logs = []
        if debug_path:
            all_logs.append(f'[CRM_CANDIDATOS] debug_json={debug_path}')
        if link_contato_id:
            all_logs.append(
                f'[CRM_CANDIDATOS] vinculo_ixc_id={link_contato_id} recurso_etapa1={ixc_lead_resource or "(vazio)"}'
            )

        resources_to_try = self._crm_candidatos_resources_to_try()
        last_error = None
        for idx, resource in enumerate(resources_to_try):
            endpoint = f"{self.url}/webservice/v1/{resource}"
            result = self._post_ixc(
                endpoint,
                payload,
                'CRM_CANDIDATOS',
                extra_headers={'ixcsoft': 'incluir'},
            )
            all_logs.extend(result.get('logs', []))

            response_data = result.get('data') if result.get('status') == 'success' else None
            response_message = ''
            response_type = ''
            if isinstance(response_data, dict):
                response_message = str(response_data.get('message', ''))
                response_type = str(response_data.get('type', '')).lower()

            if self._is_resource_unavailable(result) or (
                response_type == 'error' and 'recurso' in response_message.lower()
            ):
                nxt = resources_to_try[idx + 1] if idx + 1 < len(resources_to_try) else None
                if nxt:
                    all_logs.append(
                        f'[CRM_CANDIDATOS] recurso `{resource}` indisponível no IXC; tentando `{nxt}`.'
                    )
                else:
                    all_logs.append(
                        f'[CRM_CANDIDATOS] recurso `{resource}` indisponível no IXC (sem mais recursos na fila).'
                    )
                last_error = result
                continue

            if result.get('status') != 'success':
                return {
                    'status': 'error',
                    'message': result.get('message') or 'Falha HTTP ao criar CRM candidatos.',
                    'logs': all_logs,
                }

            if response_type == 'error':
                return {
                    'status': 'error',
                    'message': response_message or 'IXC retornou erro ao criar CRM candidatos.',
                    'logs': all_logs + [f'[CRM_CANDIDATOS] erro_api: {response_message}'],
                }

            candidato_id = self._extract_id(response_data)
            if candidato_id in (None, '', 0, '0'):
                return {
                    'status': 'error',
                    'message': 'IXC não retornou ID do CRM candidatos.',
                    'logs': all_logs + ['[CRM_CANDIDATOS] id ausente na resposta'],
                }
            return {
                'status': 'success',
                'candidato_id': candidato_id,
                'candidato_resource': resource,
                'message': '',
                'logs': [],
            }

        msg_tail = ''
        if last_error and isinstance(last_error.get('data'), dict):
            msg_tail = str(last_error['data'].get('message', '') or '')
        base_msg = msg_tail or 'Nenhum recurso de CRM candidatos disponível neste IXC.'
        if self._is_demo_ixc_host() and last_error and self._is_resource_unavailable(last_error):
            base_msg = (
                f'{base_msg} '
                'No IXC demo os webservices ``crm_canditados`` / ``crm_candidatos`` costumam não existir. '
                'No provedor real use o Postman e IXC_CRM_CANDIDATOS_RESOURCE / IXC_CRM_CANDIDATOS_FALLBACK_RESOURCES.'
            )
        return {
            'status': 'error',
            'message': base_msg,
            'logs': all_logs or (last_error.get('logs', []) if last_error else []),
        }

    def create_crm_prospect(self, cadastro, *, link_contato_id=None, ixc_lead_resource=None, force=False):
        """
        Etapa 2 no painel: POST de prospecção CRM no IXC (Postman — ``/webservice/v1/crm_canditados`` em primeiro lugar).
        Para ``crm_canditados`` / ``crm_candidatos`` usa ``build_crm_candidatos_payload``; para ``crm_prospect`` (legado)
        usa ``build_crm_prospect_payload``. Ordem dos recursos: ``IXC_CRM_PROSPECT_RESOURCE`` ou fila padrão em
        ``_crm_prospect_resources_to_try``. ``force=True`` ignora IXC_CREATE_CRM_PROSPECT.
        """
        if not force and not getattr(settings, 'IXC_CREATE_CRM_PROSPECT', False):
            return {
                'status': 'skipped',
                'message': 'IXC_CREATE_CRM_PROSPECT=False',
                'logs': ['[CRM_ETAPA2] desativado nas configurações (use etapa 2 com force ou ative o .env).'],
            }
        if not self.url or not self.token:
            return {
                'status': 'error',
                'message': 'API do IXC não configurada.',
                'logs': ['[CRM_ETAPA2] IXC_API_URL/IXC_API_TOKEN ausentes.'],
            }
        all_logs = []
        if link_contato_id:
            all_logs.append(
                f'[CRM_ETAPA2] vinculo_ixc_id={link_contato_id} recurso_etapa1={ixc_lead_resource or "(vazio)"}'
            )

        resources_to_try = self._crm_prospect_resources_to_try()
        last_error = None
        for idx, resource in enumerate(resources_to_try):
            if self._crm_etapa2_resource_uses_candidatos_payload(resource):
                payload = self.build_crm_candidatos_payload(
                    cadastro,
                    link_contato_id=link_contato_id,
                    ixc_lead_resource=ixc_lead_resource,
                )
            else:
                payload = self.build_crm_prospect_payload(
                    cadastro,
                    link_contato_id=link_contato_id,
                    ixc_lead_resource=ixc_lead_resource,
                )
            debug_path = self._save_debug_json(cadastro.pk, payload, f'CRM_ETAPA2_{resource}')
            if debug_path:
                all_logs.append(f'[CRM_ETAPA2] debug_json={debug_path}')

            endpoint = f"{self.url}/webservice/v1/{resource}"
            result = self._post_ixc(
                endpoint,
                payload,
                'CRM_ETAPA2',
                extra_headers={'ixcsoft': 'incluir'},
            )
            all_logs.extend(result.get('logs', []))

            response_data = result.get('data') if result.get('status') == 'success' else None
            response_message = ''
            response_type = ''
            if isinstance(response_data, dict):
                response_message = str(response_data.get('message', ''))
                response_type = str(response_data.get('type', '')).lower()

            if self._is_resource_unavailable(result) or (
                response_type == 'error' and 'recurso' in response_message.lower()
            ):
                nxt = resources_to_try[idx + 1] if idx + 1 < len(resources_to_try) else None
                if nxt:
                    all_logs.append(
                        f'[CRM_ETAPA2] recurso `{resource}` indisponível no IXC; tentando `{nxt}`.'
                    )
                else:
                    all_logs.append(
                        f'[CRM_ETAPA2] recurso `{resource}` indisponível no IXC (sem mais recursos na fila).'
                    )
                last_error = result
                continue

            if result.get('status') != 'success':
                return {
                    'status': 'error',
                    'message': result.get('message') or 'Falha HTTP na etapa 2 (IXC).',
                    'logs': all_logs,
                }

            if response_type == 'error':
                return {
                    'status': 'error',
                    'message': response_message or 'IXC retornou erro na etapa 2.',
                    'logs': all_logs + [f'[CRM_ETAPA2] erro_api: {response_message}'],
                }

            prospect_id = self._extract_id(response_data)
            if prospect_id in (None, '', 0, '0'):
                if isinstance(response_data, dict) and len(response_data) == 0:
                    all_logs.append(
                        '[CRM_ETAPA2] IXC retornou 200 com JSON vazio (doc: sem corpo). '
                        'Confira no CRM se o registro foi criado.'
                    )
                    return {
                        'status': 'warning',
                        'prospect_id': None,
                        'prospect_resource': resource,
                        'message': 'IXC aceitou o cadastro sem retornar ID no JSON. Verifique no IXC.',
                        'logs': all_logs,
                    }
                return {
                    'status': 'error',
                    'message': 'IXC não retornou ID do registro (etapa 2).',
                    'logs': all_logs + ['[CRM_ETAPA2] id ausente na resposta'],
                }
            return {
                'status': 'success',
                'prospect_id': prospect_id,
                'prospect_resource': resource,
                'message': '',
                'logs': [],
            }

        msg_tail = ''
        if last_error and isinstance(last_error.get('data'), dict):
            msg_tail = str(last_error['data'].get('message', '') or '')
        base_msg = msg_tail or 'Nenhum recurso da etapa 2 disponível neste IXC.'
        demo_recurso_indisponivel = (
            self._is_demo_ixc_host()
            and last_error
            and self._is_resource_unavailable(last_error)
        )
        if demo_recurso_indisponivel:
            base_msg = (
                f'{base_msg} '
                'No IXC demo alguns webservices podem estar desativados. No provedor real use '
                '`crm_canditados` (Postman) ou configure `IXC_CRM_PROSPECT_RESOURCE` / '
                '`IXC_CRM_PROSPECT_FALLBACK_RESOURCES`.'
            )
            return {
                'status': 'warning',
                'message': base_msg,
                'prospect_id': None,
                'logs': all_logs or (last_error.get('logs', []) if last_error else []),
            }
        return {
            'status': 'error',
            'message': base_msg,
            'logs': all_logs or (last_error.get('logs', []) if last_error else []),
        }

    def create_crm_lead(self, cadastro):
        """
        Passo 1: Cria um Lead no CRM do IXC.
        """
        if not self.url or not self.token:
            return {
                'status': 'error',
                'message': 'API do IXC não configurada.',
                'logs': ['[CRM_LEAD] variaveis IXC_API_URL/IXC_API_TOKEN ausentes.']
            }

        payload = self.build_crm_lead_payload(cadastro)

        # Salva o JSON para auditoria (ficheiro em logs/ixc_debug/; não polui a resposta JSON).
        self._save_debug_json(cadastro.pk, payload, 'CRM_LEAD')

        try:
            all_logs: list[str] = []
            last_error = None
            resources_to_try = self._crm_lead_resources_to_try()

            for idx, resource in enumerate(resources_to_try):
                endpoint = f'{self.url}/webservice/v1/{resource}'
                result = self._post_ixc(
                    endpoint,
                    payload,
                    'CRM_LEAD',
                    extra_headers={'ixcsoft': 'incluir'},
                )
                all_logs.extend(result.get('logs', []))

                response_data = result.get('data') if result.get('status') == 'success' else None

                response_message = ''
                response_type = ''
                if isinstance(response_data, dict):
                    response_message = str(response_data.get('message', ''))
                    response_type = str(response_data.get('type', '')).lower()

                message_text = f"{result.get('message', '')} {response_message}".lower()
                if ('recurso' in message_text and 'não está disponível' in message_text) or (
                    response_type == 'error' and 'recurso' in response_message.lower()
                ):
                    nxt = resources_to_try[idx + 1] if idx + 1 < len(resources_to_try) else None
                    if nxt:
                        all_logs.append(
                            f'[CRM_LEAD] recurso `{resource}` indisponível no IXC; tentando `{nxt}`.'
                        )
                    else:
                        all_logs.append(
                            f'[CRM_LEAD] recurso `{resource}` indisponível no IXC (sem mais recursos na fila).'
                        )
                    last_error = result
                    continue

                if result.get('status') != 'success':
                    result['logs'] = all_logs
                    return result

                if response_type == 'error':
                    result['status'] = 'error'
                    result['message'] = response_message or 'IXC retornou erro ao criar lead.'
                    all_logs.append(f'[CRM_LEAD] erro_api: {result["message"]}')
                    result['logs'] = all_logs
                    return result

                lead_id = self._extract_id(response_data)
                if lead_id in (None, '', 0, '0'):
                    result['status'] = 'error'
                    result['message'] = 'IXC respondeu HTTP 200, mas não retornou ID do Lead.'
                    all_logs.append('[CRM_LEAD] erro: id ausente na resposta')
                    result['logs'] = all_logs
                    return result

                result['lead_id'] = lead_id
                result['lead_resource'] = resource
                lead_logs: list[str] = []
                if self.lead_post_alterar and resource in (
                    'contato',
                    'crm_lead',
                    'crm_sp_leads',
                    'crm_leads',
                ):
                    patch = self._ixc_alterar_mesmo_payload(resource, lead_id, payload)
                    pdata = patch.get('data') if isinstance(patch.get('data'), dict) else {}
                    if patch.get('status') != 'success' or str(pdata.get('type', '')).lower() == 'error':
                        msg = patch.get('message') or pdata.get('message') or ''
                        lead_logs.append(
                            f'[CRM_LEAD] aviso pós-alterar (IXC_LEAD_POST_ALTERAR): {msg or "sem detalhe"}'
                        )
                        lead_logs.extend(patch.get('logs') or [])
                result['logs'] = lead_logs
                return result

            return {
                'status': 'error',
                'message': 'Nenhum recurso de lead disponível.',
                'logs': all_logs or (last_error.get('logs', []) if last_error else []),
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e), 'logs': [f"[CRM_LEAD] excecao: {str(e)}"]}

    def _load_cliente_contrato_template(self):
        path = os.path.join(os.path.dirname(__file__), 'data', 'ixc_cliente_contrato_incluir_template.json')
        with open(path, encoding='utf-8') as f:
            return json.load(f)

    def _ixc_id_cliente_for_cadastro(self, cadastro):
        """id_cliente IXC: vínculo da ficha (prospecção > contato) > .env só se a ficha não tiver IXC.

        ``IXC_CONTRATO_TEST_ID_CLIENTE`` é fallback de homologação; se vier **antes** do vínculo da ficha,
        todo contrato/teste ia para o cliente fixo (ex.: 2306) mesmo após novo lead/prospect.
        """
        pid = (cadastro.ixc_prospect_id or '').strip()
        if pid:
            return pid
        lid = (cadastro.ixc_lead_id or '').strip()
        if lid:
            return lid
        return (settings.IXC_CONTRATO_TEST_ID_CLIENTE or '').strip()

    def build_cliente_contrato_test_payload(self, cadastro):
        """Monta JSON para POST ``cliente_contrato`` (teste). Retorna (payload, erro_msg)."""
        try:
            payload = self._load_cliente_contrato_template()
        except (OSError, json.JSONDecodeError) as e:
            return None, f'Arquivo template data/ixc_cliente_contrato_incluir_template.json: {e}'

        id_cliente = self._ixc_id_cliente_for_cadastro(cadastro)
        if not id_cliente:
            return None, (
                'id_cliente ausente: conclua «Enviar para IXC» nesta ficha (ixc_prospect_id ou ixc_lead_id) ou defina '
                'IXC_CONTRATO_TEST_ID_CLIENTE no .env (fallback só sem vínculo IXC no cadastro).'
            )

        id_plano, _, _ = self._resolve_plano_e_canal_venda(cadastro)
        id_vd = ''
        v = self._ixc_fk_value(id_plano)
        if v is not None:
            id_vd = str(v).strip()
        # Override de emergência por ambiente (homologação): IXC_FORCE_PLANO_VENDA_ID.
        force_vd = (getattr(settings, 'IXC_FORCE_PLANO_VENDA_ID', None) or '').strip()
        if force_vd:
            id_vd = force_vd
        if not id_vd and self._is_demo_ixc_host():
            id_vd = '19'
        if not id_vd:
            return None, (
                'id_vd_contrato vazio: cadastre o plano em '
                '/admin-dash/operacao/planos/ com `ixc_plano_venda_id` preenchido '
                'ou ajuste o default em cadastros/ixc_ids.PLANOS_POR_FILIAL.'
            )

        # Filial: cidade do cadastro (painel Operação → defaults `ixc_ids.FILIAIS`).
        # Demo IXC sempre vai para a filial 1.
        if self._is_demo_ixc_host():
            id_filial = '1'
        else:
            id_filial = (self.resolve_filial_id(cadastro.cidade) or '').strip() or '1'

        payload['id_cliente'] = str(id_cliente)
        payload['id_vd_contrato'] = str(id_vd)
        payload['id_filial'] = str(id_filial)
        base_tipo = (settings.IXC_CONTRATO_TEST_TIPO or 'I').strip() or 'I'
        desc_contrato = (getattr(settings, 'IXC_CONTRATO_TEST_CONTRATO_DESCRICAO', None) or '').strip()
        if desc_contrato:
            payload['contrato'] = desc_contrato[:200]
        else:
            payload['contrato'] = str(cadastro.plano_velocidade or cadastro.plano or 'Contrato teste')[:200]
        payload['data'] = timezone.now().strftime('%d/%m/%Y')
        # id_modelo é fixo do provedor (ajustável via AppConfigOperacao no futuro).
        payload['id_modelo'] = (settings.IXC_CONTRATO_TEST_ID_MODELO or '1').strip()
        # Tipo de documento da fatura → AppConfigOperacao.ixc_tipo_documento_fatura_id (padrão 501).
        payload['id_tipo_documento'] = ixc_ids.get_tipo_documento_fatura_id() or '501'
        # Carteira de cobrança: painel por cidade > default por cidade > 1.
        payload['id_carteira_cobranca'] = (self.resolve_carteira_cobranca_id(cadastro.cidade) or '1').strip()
        # Vendedor / responsável: prioridade
        #   1) `cadastro.vendedor_responsavel` (override manual da ficha).
        #   2) `cadastro.consultor.vendedor_ixc` (consultor logado tem vínculo IXC).
        #   3) fallback `.env` (homologação).
        _vend = self._resolve_vendedor_ixc(cadastro)
        if _vend:
            _vend_id = (str(_vend.ixc_id).strip() if _vend.ixc_id else '')
            _resp_id = (str(_vend.responsavel_ixc_id).strip() if _vend.responsavel_ixc_id else _vend_id)
            payload['id_vendedor'] = _vend_id
            payload['id_responsavel'] = _resp_id or _vend_id
            payload['id_vendedor_ativ'] = _vend_id
        else:
            # Mantém compatibilidade com o legado de homologação (ainda preenche no .env).
            _vend_default = (settings.IXC_CONTRATO_TEST_ID_VENDEDOR or '1').strip()
            payload['id_vendedor'] = _vend_default
        comissao_v = (getattr(settings, 'IXC_CONTRATO_TEST_COMISSAO', None) or '').strip()
        if comissao_v:
            payload['comissao'] = comissao_v
        # Tipo doc opcional/ativação: painel por cidade > default por filial.
        tipo_doc_ativ = self.resolve_tipo_doc_ativ_id(cadastro.cidade)
        # id_carencia (cobrança/vencimento): a ficha já guarda o id IXC pronto
        # (foi escolhido pelo cliente em uma `OpcaoVencimento`). Se for um dia
        # (ex.: "13"), resolve pelo painel/defaults; se já for id IXC (3 dígitos
        # ou >31), envia direto.
        venc_raw = (getattr(cadastro, 'vencimento_id', '') or '').strip()
        id_carencia = ''
        if venc_raw.isdigit():
            if 1 <= int(venc_raw) <= 31:
                id_carencia = self.resolve_vencimento_id(cadastro.cidade, venc_raw)
            else:
                id_carencia = venc_raw
        if id_carencia:
            payload['id_carencia'] = id_carencia
        # Produto da taxa de instalação (R$ 100,00 — produto 146 por padrão).
        taxa_reais = ixc_ids.get_instalacao_taxa_reais(cadastro)
        if taxa_reais and taxa_reais > 0:
            payload['taxa_instalacao'] = (
                f'{taxa_reais:.2f}'.replace('.', ',') if isinstance(taxa_reais, float) else
                f'{float(taxa_reais):.2f}'.replace('.', ',')
            )
            produto_ativ = ixc_ids.get_produto_instalacao_id()
            if produto_ativ:
                payload['id_produto_ativ'] = produto_ativ
            if tipo_doc_ativ:
                payload['id_tipo_doc_ativ'] = tipo_doc_ativ
        elif tipo_doc_ativ:
            # Mantém o tipo doc opcional preenchido mesmo se não houver taxa cobrada.
            payload['id_tipo_doc_ativ'] = tipo_doc_ativ
        payload['cc_previsao'] = (settings.IXC_CONTRATO_TEST_CC_PREVISAO or 'M').strip()
        payload['tipo_cobranca'] = (settings.IXC_CONTRATO_TEST_TIPO_COBRANCA_ID or 'P').strip()
        # Fidelidade: 12 meses se aceitou na ficha, senão vazio (IXC entende sem fidelidade).
        payload['fidelidade'] = ixc_ids.get_fidelidade_meses(bool(getattr(cadastro, 'fidelidade', False)))
        payload['renovacao_automatica'] = (settings.IXC_CONTRATO_TEST_RENOVACAO_AUTOMATICA or 'S').strip()
        payload['base_geracao_tipo_doc'] = (settings.IXC_CONTRATO_TEST_BASE_GERACAO_TIPO_DOC or 'P').strip()
        payload['bloqueio_automatico'] = (settings.IXC_CONTRATO_TEST_BLOQUEIO_AUTOMATICO or 'S').strip()
        payload['aviso_atraso'] = (settings.IXC_CONTRATO_TEST_AVISO_ATRASO or 'S').strip()
        payload['endereco_padrao_cliente'] = (settings.IXC_CONTRATO_TEST_ENDERECO_PADRAO_CLIENTE or 'S').strip()
        payload['obs'] = f'[CADASTRO_WEB] cadastro_id={cadastro.pk} teste cliente_contrato.'[:2000]
        if getattr(settings, 'IXC_CONTRATO_AGUARDANDO_ASSINATURA_INCLUIR', True):
            ad = (getattr(settings, 'IXC_CONTRATO_TEST_ASSINATURA_DIGITAL', None) or 'S').strip()
            if ad:
                payload['assinatura_digital'] = ad
            integ = (getattr(settings, 'IXC_CONTRATO_TEST_INTEGRACAO_ASSINATURA_DIGITAL', None) or '').strip()
            if integ:
                payload['integracao_assinatura_digital'] = integ
            gf = (getattr(settings, 'IXC_CONTRATO_TEST_GERAR_FINAN_ASSIN_DIGITAL', None) or '').strip()
            if gf:
                payload['gerar_finan_assin_digital_contrato'] = gf
            st = (getattr(settings, 'IXC_CONTRATO_TEST_STATUS', None) or '').strip()
            if st:
                payload['status'] = st
        sync_plano = getattr(settings, 'IXC_CONTRATO_TEST_TIPO_SINCR_COM_PLANO', True)
        if sync_plano:
            # Evita enviar id_tipo_contrato / tipo_produtos_plano do template antes do merge — o IXC
            # valida contrato vs plano de venda (vd) e rejeita FK genérica (ex.: 10) com id_vd=124.
            payload['id_tipo_contrato'] = ''
            payload['tipo_produtos_plano'] = ''
            tipo_resolved, vd_row = self._resolve_tipo_contrato_alinhado_ao_plano_venda(id_vd, base_tipo)
            payload['tipo'] = tipo_resolved
            if vd_row:
                IXCIntegration._merge_cliente_contrato_campos_do_vd(payload, vd_row)
            id_tc_ok = str(payload.get('id_tipo_contrato') or '').strip()
            if not id_tc_ok:
                env_tc = (getattr(settings, 'IXC_CONTRATO_TEST_ID_TIPO_CONTRATO', None) or '').strip()
                if env_tc:
                    # Tela «Contrato»: tipo de cobrança (ex. 10) — use quando o listar vd não devolve a FK.
                    payload['id_tipo_contrato'] = env_tc
                elif vd_row:
                    payload.pop('id_tipo_contrato', None)
                else:
                    payload['id_tipo_contrato'] = '10'
            if not str(payload.get('tipo_produtos_plano') or '').strip():
                payload.pop('tipo_produtos_plano', None)
        else:
            payload['id_tipo_contrato'] = (
                (getattr(settings, 'IXC_CONTRATO_TEST_ID_TIPO_CONTRATO', None) or '').strip()
                or str(payload.get('id_tipo_contrato') or '').strip()
                or '10'
            )
            payload['tipo'] = base_tipo
        return payload, None

    def _post_cliente_contrato_aguardando_assinatura(self, contrato_id, logs):
        """POST opcional no recurso configurado (ex. ``cliente_contrato_23529``) para deixar o contrato aguardando assinatura."""
        resource = (getattr(settings, 'IXC_CLIENTE_CONTRATO_ASSINATURA_RESOURCE', None) or '').strip()
        if not resource or not self.url or not self.token:
            return None, None
        cid = str(contrato_id or '').strip()
        if not cid:
            return None, None
        endpoint = f'{self.url}/webservice/v1/{resource}'
        key = (getattr(settings, 'IXC_CLIENTE_CONTRATO_ASSINATURA_JSON_KEY', None) or 'id_contrato').strip() or 'id_contrato'
        ping = {key: cid}
        xh = (getattr(settings, 'IXC_CLIENTE_CONTRATO_ASSINATURA_IXCSOFT', None) or '').strip()
        extra_headers = {'ixcsoft': xh} if xh else None
        result = self._post_ixc(
            endpoint,
            ping,
            'CLIENTE_CONTRATO_ASSINATURA',
            extra_headers=extra_headers,
        )
        logs.extend(result.get('logs', []))
        if result.get('status') != 'success':
            msg = result.get('message') or 'Falha HTTP no POST de assinatura.'
            logs.append(f'[CLIENTE_CONTRATO] aguardando_assinatura: {msg[:200]}')
            return False, msg
        body = result.get('data') if isinstance(result.get('data'), dict) else {}
        if str(body.get('type', '')).lower() == 'error':
            msg = str(body.get('message', ''))[:500]
            logs.append(f'[CLIENTE_CONTRATO] aguardando_assinatura erro_api: {msg}')
            return False, msg or 'erro_api'
        return True, None

    def create_cliente_contrato_test(self, cadastro):
        """POST ``webservice/v1/cliente_contrato`` com ``ixcsoft: incluir`` (somente teste operado pelo painel)."""
        if not self.url or not self.token:
            return {
                'status': 'error',
                'message': 'API do IXC não configurada (IXC_API_URL / IXC_API_TOKEN).',
                'logs': ['[CLIENTE_CONTRATO] IXC ausente.'],
            }
        payload, err = self.build_cliente_contrato_test_payload(cadastro)
        if err:
            return {'status': 'error', 'message': err, 'logs': [f'[CLIENTE_CONTRATO] {err}']}

        resource = (settings.IXC_CLIENTE_CONTRATO_RESOURCE or 'cliente_contrato').strip()
        endpoint = f'{self.url}/webservice/v1/{resource}'
        debug_path = self._save_debug_json(cadastro.pk, payload, 'CLIENTE_CONTRATO_TEST')

        def _contrato_err_logs(*lines: str) -> list[str]:
            out: list[str] = []
            if debug_path:
                out.append(f'[CLIENTE_CONTRATO] debug_json={debug_path}')
            out.extend(lines)
            return out

        result = self._post_ixc(
            endpoint,
            payload,
            'CLIENTE_CONTRATO',
            extra_headers={'ixcsoft': 'incluir'},
        )

        if result.get('status') != 'success':
            return {
                'status': 'error',
                'message': result.get('message') or 'Falha HTTP ao criar contrato.',
                'logs': _contrato_err_logs(*(result.get('logs') or [])),
            }

        body = result.get('data') if isinstance(result.get('data'), dict) else {}
        response_type = str(body.get('type', '')).lower()
        response_message = str(body.get('message', ''))
        if response_type == 'error':
            return {
                'status': 'error',
                'message': response_message or 'IXC retornou erro ao incluir contrato.',
                'logs': _contrato_err_logs(f'[CLIENTE_CONTRATO] erro_api: {response_message}'),
            }

        contrato_id = self._extract_cliente_contrato_id(body)
        if contrato_id not in (None, '', 0, '0'):
            msg_ok = f'Contrato criado no IXC (teste). ID: {contrato_id}.'
            from .models import Cadastro

            cid = str(contrato_id).strip()
            Cadastro.objects.filter(pk=cadastro.pk).update(ixc_contrato_id=cid)
            sig_logs: list[str] = []
            ok_sig, sig_err = self._post_cliente_contrato_aguardando_assinatura(cid, sig_logs)
            if ok_sig is True:
                msg_ok = f'{msg_ok} Aguardando assinatura (WS auxiliar aplicado).'
            elif ok_sig is False and sig_err:
                msg_ok = (
                    f'{msg_ok} Aviso: não foi possível aplicar «aguardando assinatura» no WS auxiliar: '
                    f'{str(sig_err)[:160]}'
                )

            return {
                'status': 'success',
                'message': msg_ok,
                'contrato_id': contrato_id,
                'logs': list(sig_logs),
            }

        miss_line = (
            f'[CLIENTE_CONTRATO] id do contrato não extraído do JSON; '
            f'chaves_resposta={list(body.keys())[:25]}'
        )
        id_sent = str(payload.get('id_cliente', '')).strip()
        lead_only = (
            id_sent
            and id_sent == str(cadastro.ixc_lead_id or '').strip()
            and not str(cadastro.ixc_prospect_id or '').strip()
        )

        if lead_only:
            return {
                'status': 'warning',
                'message': (
                    'IXC respondeu 200 sem ID de contrato. O id_cliente veio só do contato (ixc_lead_id). '
                    'Conclua a prospecção (crm_canditados) para gravar ixc_prospect_id e teste de novo com esse ID.'
                ),
                'contrato_id': None,
                'logs': [
                    miss_line,
                    '[CLIENTE_CONTRATO] causa provável: id_cliente ainda é só contato; use ixc_prospect_id após CRM.',
                ],
            }

        msg_ok = 'Contrato enviado ao IXC (teste).'
        if not body:
            msg_ok = 'IXC aceitou o POST sem corpo JSON; confira o contrato no IXC.'
        return {
            'status': 'success',
            'message': msg_ok,
            'contrato_id': contrato_id,
            'logs': [miss_line],
        }

    # ------------------------------------------------------------------ #
    # ARQUIVOS DO CLIENTE — POST `webservice/v1/cliente_arquivos`        #
    # ------------------------------------------------------------------ #
    # Multipart/form-data com:
    #   - data: { 'descricao': str, 'id_cliente': str }
    #   - files: { 'local_arquivo': (filename, fp, mime) }
    # ``id_cliente`` é o ID do cliente no IXC; tentamos resolver por:
    #   1) parâmetro explícito do chamador,
    #   2) ``ixc_prospect_id`` (após prospecção crm_canditados),
    #   3) ``ixc_candidato_id``,
    #   4) ``ixc_lead_id`` (lead/contato).
    # Retorno consolidado para a UI: `status`, `message`, `uploads`, `logs`.

    # Campos do `Cadastro` que viram POST cliente_arquivos. Ordem importa só
    # para o log de auditoria; não há acoplamento com a API IXC.
    _ARQUIVOS_FIELDS = (
        ('selfie_documento', 'SELFIE'),
        ('foto_documento_frente', 'RG (frente)'),
        ('foto_documento_verso', 'RG (verso)'),
        ('comprovante_residencia', 'Comprovante de residência'),
    )

    def _ixc_files_to_upload(self, cadastro):
        """[(campo, descricao_padrao, file_field)] filtrando vazios."""
        items = []
        for fname, label in self._ARQUIVOS_FIELDS:
            f = getattr(cadastro, fname, None)
            items.append((fname, label, f))
        # PJ → contrato social também vai junto.
        if (getattr(cadastro, 'tipo_pessoa', '') or '').strip().lower() == 'pj':
            items.append(('contrato_social', 'Contrato social', getattr(cadastro, 'contrato_social', None)))
        return items

    def _resolve_id_cliente_for_arquivos(self, cadastro):
        """Ordem: prospect > candidato > lead. Retorna (id_str, origem) ou (None, None)."""
        candidates = (
            ('ixc_prospect_id', getattr(cadastro, 'ixc_prospect_id', None)),
            ('ixc_candidato_id', getattr(cadastro, 'ixc_candidato_id', None)),
            ('ixc_lead_id', getattr(cadastro, 'ixc_lead_id', None)),
        )
        for origem, val in candidates:
            s = str(val).strip() if val is not None else ''
            if s:
                return s, origem
        return None, None

    def _post_ixc_multipart(self, endpoint, data, files, etapa, extra_headers=None):
        """Igual a ``_post_ixc`` mas em multipart/form-data (não envia Content-Type;
        o requests gera o boundary correto). Mantém o mesmo formato de retorno.
        """
        headers = {'Authorization': self.headers.get('Authorization', '')}
        if extra_headers:
            headers.update(extra_headers)
        try:
            response = requests.post(
                endpoint,
                data=data,
                files=files,
                headers=headers,
                verify=False,
                timeout=60,
            )
            if response.status_code in (200, 201):
                raw_text = (response.text or '').strip()
                if not raw_text:
                    return {
                        'status': 'success',
                        'data': {},
                        'logs': [],
                        'http_status': response.status_code,
                    }
                try:
                    body = response.json()
                except ValueError:
                    preview = (response.text or '').strip()[:500]
                    return {
                        'status': 'error',
                        'message': 'Resposta HTTP 200/201 sem JSON válido (IXC ou proxy).',
                        'logs': [
                            f'[{etapa}] endpoint={endpoint}',
                            f'[{etapa}] status_http={response.status_code}',
                            f'[{etapa}] resposta_nao_json: {preview}',
                        ],
                        'http_status': response.status_code,
                        'endpoint': endpoint,
                    }
                return {
                    'status': 'success',
                    'data': body,
                    'logs': [],
                    'http_status': response.status_code,
                }
            error_preview = (response.text or '').strip()[:500]
            return {
                'status': 'error',
                'message': error_preview or f'Falha HTTP {response.status_code}',
                'logs': [
                    f'[{etapa}] endpoint={endpoint}',
                    f'[{etapa}] status_http={response.status_code}',
                    f'[{etapa}] erro: {error_preview}',
                ],
                'http_status': response.status_code,
                'endpoint': endpoint,
            }
        except requests.RequestException as e:
            return {
                'status': 'error',
                'message': f'Falha na conexão: {str(e)}',
                'logs': [
                    f'[{etapa}] endpoint={endpoint}',
                    f'[{etapa}] excecao_rede: {str(e)}',
                ],
                'endpoint': endpoint,
            }

    @staticmethod
    def _guess_mime(filename):
        m, _ = mimetypes.guess_type(filename or '')
        return m or 'application/octet-stream'

    def upload_cliente_arquivos(self, cadastro, *, id_cliente=None, descricao_prefix=None):
        """POST `webservice/v1/cliente_arquivos` para cada arquivo do cadastro.

        Args:
            cadastro: instância de `Cadastro` com FileFields preenchidos.
            id_cliente: opcional. ID do cliente no IXC. Quando omitido, tenta
                resolver a partir de `ixc_prospect_id` > `ixc_candidato_id` > `ixc_lead_id`.
            descricao_prefix: opcional. Texto prepended à descrição (ex.: "Cad #42").

        Returns:
            dict { status, message, uploads: [...], logs: [...], id_cliente }.
        """
        if not self.url or not self.token:
            return {
                'status': 'error',
                'message': 'API do IXC não configurada (IXC_API_URL / IXC_API_TOKEN).',
                'logs': ['[ARQUIVOS] IXC_API_URL/IXC_API_TOKEN ausentes.'],
                'uploads': [],
            }

        resolved_id = (str(id_cliente).strip() if id_cliente else '') or None
        origem_id = 'explicito' if resolved_id else None
        if not resolved_id:
            resolved_id, origem_id = self._resolve_id_cliente_for_arquivos(cadastro)
        if not resolved_id:
            return {
                'status': 'error',
                'message': (
                    'Cadastro sem ID de cliente no IXC. Envie o lead/prospecção primeiro '
                    '(modal IXC → opções 1 e 2) para gravar ixc_prospect_id ou ixc_lead_id.'
                ),
                'logs': [
                    '[ARQUIVOS] sem id_cliente: ordem buscada = '
                    'ixc_prospect_id > ixc_candidato_id > ixc_lead_id.'
                ],
                'uploads': [],
            }

        resource = (getattr(settings, 'IXC_ARQUIVOS_RESOURCE', 'cliente_arquivos') or 'cliente_arquivos').strip()
        endpoint = f'{self.url}/webservice/v1/{resource}'

        items = self._ixc_files_to_upload(cadastro)
        error_logs: list[str] = []
        uploads = []
        ok_count = 0
        fail_count = 0
        skip_count = 0

        prefix = (descricao_prefix or f'Cadastro #{cadastro.pk}').strip()

        for field_name, label, file_field in items:
            # Sem arquivo neste campo → pula
            if not file_field or not getattr(file_field, 'name', None):
                uploads.append({
                    'campo': field_name,
                    'status': 'skipped',
                    'message': 'arquivo ausente neste cadastro',
                })
                skip_count += 1
                continue

            raw_full = b''
            try:
                fp = file_field.open('rb')
                try:
                    raw_full = fp.read() or b''
                finally:
                    try:
                        fp.close()
                    except Exception:
                        pass
            except Exception as e:
                uploads.append({
                    'campo': field_name,
                    'status': 'error',
                    'message': f'falha ao abrir arquivo: {e}',
                    'filename': (os.path.basename(file_field.name) or f'{field_name}.dat'),
                })
                error_logs.append(
                    f'[ARQUIVOS] {field_name}: não foi possível ler do storage '
                    f'(name={file_field.name!r}): {e}'
                )
                fail_count += 1
                continue

            if not raw_full:
                uploads.append({
                    'campo': field_name,
                    'status': 'error',
                    'message': 'arquivo vazio ao ler do storage',
                    'filename': (os.path.basename(file_field.name) or f'{field_name}.dat'),
                })
                error_logs.append(
                    f'[ARQUIVOS] {field_name}: leitura retornou 0 bytes (name={file_field.name!r}).'
                )
                fail_count += 1
                continue

            raw_full, ext, _webp_ixc = prepare_bytes_for_ixc_upload(raw_full, field_name)

            doc_digits = only_digits_br(getattr(cadastro, 'documento', '') or '')
            filename = build_cliente_document_filename(doc_digits, field_name, ext)
            descricao = f'{prefix} — {label}'
            mime = mimetype_for_doc_extension(ext)
            upload_buf = BytesIO(raw_full)

            try:
                files_payload = {'local_arquivo': (filename, upload_buf, mime)}
                data_payload = {'descricao': descricao, 'id_cliente': str(resolved_id)}
                result = self._post_ixc_multipart(
                    endpoint, data_payload, files_payload,
                    f'ARQUIVOS:{field_name}',
                )
            finally:
                try:
                    upload_buf.close()
                except Exception:
                    pass

            if result.get('status') == 'success':
                body = result.get('data') if isinstance(result.get('data'), dict) else {}
                arquivo_id = self._extract_id(body)
                uploads.append({
                    'campo': field_name,
                    'status': 'success',
                    'id': arquivo_id,
                    'filename': filename,
                    'descricao': descricao,
                })
                ok_count += 1
            else:
                msg = (result.get('message', '') or 'falha no POST').strip()
                uploads.append({
                    'campo': field_name,
                    'status': 'error',
                    'message': msg,
                    'filename': filename,
                })
                error_logs.append(
                    f'[ARQUIVOS] {field_name}: IXC rejeitou ou falhou (filename={filename!r}). {msg}'
                )
                for lg in (result.get('logs') or []):
                    if lg and lg not in error_logs:
                        error_logs.append(lg)
                fail_count += 1

        if ok_count and not fail_count:
            status_final = 'success'
            msg = f'{ok_count} arquivo(s) enviado(s) ao IXC com sucesso.'
        elif ok_count and fail_count:
            status_final = 'warning'
            msg = f'{ok_count} enviado(s) e {fail_count} com erro. Consulte o detalhe abaixo.'
        elif fail_count and not ok_count:
            status_final = 'error'
            msg = f'Nenhum arquivo enviado ({fail_count} falha[s]). Consulte o detalhe abaixo.'
        else:
            status_final = 'warning'
            msg = 'Nenhum arquivo encontrado neste cadastro para enviar ao IXC.'

        if skip_count:
            msg = f'{msg} ({skip_count} campo[s] sem arquivo ignorado[s].)'

        # Persistência local — auditoria em ixc_envio_logs.arquivos
        try:
            envio = cadastro.ixc_envio_logs if isinstance(cadastro.ixc_envio_logs, dict) else {}
            envio = dict(envio)
            envio['arquivos'] = {
                'ultimo_envio_em': timezone.now().isoformat(),
                'id_cliente_ixc': str(resolved_id),
                'origem_id_cliente': origem_id,
                'status_global': status_final,
                'uploads': uploads,
            }
            cadastro.ixc_envio_logs = envio
            cadastro.save(update_fields=['ixc_envio_logs'])
        except Exception as e:
            error_logs.append(f'[ARQUIVOS] falha ao gravar auditoria local (ixc_envio_logs): {e}')

        return {
            'status': status_final,
            'message': msg,
            'uploads': uploads,
            'logs': error_logs if error_logs else [],
            'id_cliente': str(resolved_id),
            'origem_id_cliente': origem_id,
        }

    def create_os(self, cadastro, ixc_id):
        pass
