import requests
import base64
import json
import os
import re
import unicodedata
from django.conf import settings
from django.utils import timezone


class IXCIntegration:
    """
    Classe para gerenciar a integração com o ERP IXCSoft.
    """

    # Mapeamento de Filiais
    FILIAIS_MAP = {
        'marica': '2',
        'minas_gerais': '6',
        'jacone': '7',
        'araruama': '7',
        'saquarema': '7',
        'unamar': '7',
        'muqui': '8',
        'mimoso': '8',
        'piuma': '9',
        'sao_paulo': '11',
    }

    # Mapeamento de Cidades (IDs reais do banco do IXC)
    CIDADES_MAP = {
        'marica': '3214',
        'minas_gerais': '2949', # Santos Dumont
        'araruama': '3176',
        'jacone': '3176',
        'unamar': '3176',
        'saquarema': '3254',
        'cabo_frio': '3185',
        'muqui': '3147',
        'mimoso': '3143',
        'sao_paulo': '3828',
    }

    # Mapeamento de Planos de Venda
    PLANOS_MAP = {
        'essencial': '174', # 240 MEGA
        'rapido': '175',    # 400 MEGA
        'turbo': '176',     # 500 MEGA
        'ultra': '124',     # 600 MEGA
        'prime': '',        # 700 MEGA — preencher id IXC em Operação ou .env se aplicável
        '1giga': '560',     # 1 GIGA
    }

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
        # no IXC (venda, contrato, login PPPoE) de forma inconsistente. Use IXC_LEAD_RESOURCE se precisar de outro WS.
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
        """Recursos WS para incluir prospecção. Ordem: IXC_CRM_PROSPECT_RESOURCE (um só) senão
        ``crm_prospect`` + IXC_CRM_PROSPECT_FALLBACK_RESOURCES (Postman IXC Provedor).
        """
        override = (getattr(settings, 'IXC_CRM_PROSPECT_RESOURCE', None) or '').strip()
        if override:
            return [override]
        fallbacks_raw = (getattr(settings, 'IXC_CRM_PROSPECT_FALLBACK_RESOURCES', '') or '').strip()
        extra = [x.strip() for x in fallbacks_raw.split(',') if x.strip()]
        base = ['crm_prospect']
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
        logs = [
            f"[{etapa}] endpoint: {endpoint}",
            f"[{etapa}] auth: {'ok' if bool(self.token) else 'ausente'}",
        ]
        headers = {**self.headers, **(extra_headers or {})}
        try:
            response = requests.post(endpoint, json=payload, headers=headers, verify=False, timeout=30)
            logs.append(f"[{etapa}] status_http: {response.status_code}")

            if response.status_code in [200, 201]:
                raw_text = (response.text or '').strip()
                if not raw_text:
                    return {
                        'status': 'success',
                        'data': {},
                        'logs': logs + [f'[{etapa}] corpo_vazio: IXC aceitou sem JSON (comum em alguns POST).'],
                        'http_status': response.status_code,
                    }
                try:
                    body = response.json()
                except ValueError:
                    preview = (response.text or '').strip()[:500]
                    logs.append(f"[{etapa}] resposta_nao_json: {preview}")
                    return {
                        'status': 'error',
                        'message': 'Resposta HTTP 200/201 sem JSON válido (IXC ou proxy).',
                        'logs': logs,
                        'http_status': response.status_code,
                        'endpoint': endpoint,
                    }
                return {
                    'status': 'success',
                    'data': body,
                    'logs': logs,
                    'http_status': response.status_code,
                }

            error_preview = (response.text or '').strip()[:500]
            logs.append(f"[{etapa}] erro: {error_preview}")
            return {
                'status': 'error',
                'message': error_preview or f'Falha HTTP {response.status_code}',
                'logs': logs,
                'http_status': response.status_code,
                'endpoint': endpoint,
            }
        except requests.RequestException as e:
            logs.append(f"[{etapa}] excecao: {str(e)}")
            return {
                'status': 'error',
                'message': f"Falha na conexão: {str(e)}",
                'logs': logs,
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
        logs = [f"[DUPLICIDADE] documento={documento}"]
        for resource in resources:
            found, qtype = self._search_ixc_by_document(resource, documento)
            if found:
                found_id = self._extract_id(found)
                logs.append(f"[DUPLICIDADE] encontrado em {resource} qtype={qtype} id={found_id}")
                return {
                    'status': 'duplicate',
                    'message': f'Duplicidade no IXC: documento já existe em {resource}.',
                    'resource': resource,
                    'found_id': found_id,
                    'logs': logs,
                }
            logs.append(f"[DUPLICIDADE] sem registro em {resource}")

        return {'status': 'ok', 'message': 'Sem duplicidade no IXC.', 'logs': logs}

    def resolve_filial_id(self, cidade_slug):
        try:
            from .operacao_models import CidadeOperacao

            c = CidadeOperacao.objects.get(slug=cidade_slug)
            if (c.ixc_filial_id or '').strip():
                return c.ixc_filial_id.strip()
        except Exception:
            pass
        return self.FILIAIS_MAP.get(cidade_slug, '2')

    def _fetch_first_contrato_id_for_id_cliente(self, id_cliente):
        """Lista contratos no IXC por id_cliente (``ixcsoft: listar``). Retorna (id_contrato ou None, logs)."""
        logs = []
        qid = str(id_cliente or '').strip()
        if not qid or not self.url or not self.token:
            return None, logs

        resource = (settings.IXC_CLIENTE_CONTRATO_RESOURCE or 'cliente_contrato').strip()
        endpoint = f'{self.url}/webservice/v1/{resource}'
        qtypes = (
            'id_cliente',
            'cliente_contrato.id_cliente',
            'contrato.id_cliente',
            'cliente_id',
        )

        for qtype in qtypes:
            payload = {
                'qtype': qtype,
                'query': qid,
                'oper': '=',
                'page': '1',
                'rp': '15',
                'sortname': 'id',
                'sortorder': 'desc',
            }
            result = self._post_ixc(
                endpoint,
                payload,
                'CLIENTE_CONTRATO_LIST',
                extra_headers={'ixcsoft': 'listar'},
            )
            if result.get('status') != 'success':
                logs.append(
                    f'[RADUSUARIOS] listar_contrato qtype={qtype} http_falha: {result.get("message", "")[:120]}'
                )
                continue

            data = result.get('data')
            if not isinstance(data, dict):
                continue
            if str(data.get('type', '')).lower() == 'error':
                msg = str(data.get('message', ''))[:200]
                logs.append(f'[RADUSUARIOS] listar_contrato qtype={qtype} erro_api: {msg}')
                continue

            rows = data.get('registros')
            if not isinstance(rows, list):
                rows = data.get('records')
            if not isinstance(rows, list) or not rows:
                logs.append(f'[RADUSUARIOS] listar_contrato qtype={qtype} sem_registros total={data.get("total")!r}')
                continue

            for row in rows:
                if not isinstance(row, dict):
                    continue
                cid = (
                    str(row.get('id') or row.get('id_contrato') or row.get('id_cliente_contrato') or '')
                    .strip()
                )
                row_cliente = str(row.get('id_cliente') or row.get('cliente_id') or '').strip()
                if row_cliente and row_cliente != qid:
                    continue
                if cid and cid not in ('0', 'null'):
                    logs.append(
                        f'[RADUSUARIOS] id_contrato obtido via listar (qtype={qtype}): {cid}'
                    )
                    return cid, logs

        logs.append(
            '[RADUSUARIOS] listar_contrato: nenhum contrato encontrado para este id_cliente '
            '(confira permissão do token e nomes de campo no IXC).'
        )
        return None, logs

    def _fetch_cliente_contrato_row_by_id(self, id_contrato):
        """Uma linha de ``cliente_contrato`` (listar) pelo id do contrato — para endereço no radusuarios."""
        logs = []
        cid = str(id_contrato or '').strip()
        if not cid or not self.url or not self.token:
            return None, logs
        resource = (settings.IXC_CLIENTE_CONTRATO_RESOURCE or 'cliente_contrato').strip()
        endpoint = f'{self.url}/webservice/v1/{resource}'
        qtypes = (
            'cliente_contrato.id',
            'id',
            'contrato.id',
            'id_contrato',
        )
        for qtype in qtypes:
            payload = {
                'qtype': qtype,
                'query': cid,
                'oper': '=',
                'page': '1',
                'rp': '100',
                'sortname': 'id',
                'sortorder': 'desc',
            }
            result = self._post_ixc(
                endpoint,
                payload,
                'CLIENTE_CONTRATO_BY_ID',
                extra_headers={'ixcsoft': 'listar'},
            )
            if result.get('status') != 'success':
                logs.append(
                    f'[RADUSUARIOS] listar_contrato_por_id qtype={qtype} http: {result.get("message", "")[:80]}'
                )
                continue
            data = result.get('data')
            if not isinstance(data, dict) or str(data.get('type', '')).lower() == 'error':
                msg = str(data.get('message', ''))[:120] if isinstance(data, dict) else ''
                logs.append(f'[RADUSUARIOS] listar_contrato_por_id qtype={qtype} erro_api: {msg}')
                continue
            rows = data.get('registros')
            if not isinstance(rows, list):
                rows = data.get('records')
            if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
                continue
            logs.append(f'[RADUSUARIOS] contrato_por_id qtype={qtype} encontrado')
            return rows[0], logs
        logs.append('[RADUSUARIOS] contrato_por_id: nenhuma linha retornada')
        return None, logs

    @staticmethod
    def _cliente_contrato_row_id_contrato(row):
        """Id numérico do contrato na linha listar (chave simples ou ``tabela.campo``)."""
        if not isinstance(row, dict):
            return ''
        for pref in ('id', 'id_contrato', 'id_cliente_contrato'):
            v = row.get(pref)
            if v not in (None, '', 0, '0'):
                return str(v).strip()
        for k, v in row.items():
            if not isinstance(k, str) or v in (None, '', 0, '0'):
                continue
            tail = k.split('.')[-1]
            if tail in ('id', 'id_contrato') and str(v).strip():
                return str(v).strip()
        return ''

    @staticmethod
    def _id_cliente_from_cliente_contrato_row(row):
        """``id_cliente`` dono do contrato na resposta listar ``cliente_contrato`` (pode ser prospecção, não o contato)."""
        if not isinstance(row, dict):
            return ''
        for pref in ('id_cliente', 'cliente_id'):
            v = row.get(pref)
            if v not in (None, '', 0, '0'):
                return str(v).strip()
        for k, v in row.items():
            if not isinstance(k, str) or v in (None, '', 0, '0'):
                continue
            tail = k.split('.')[-1].lower()
            if tail in ('id_cliente', 'cliente_id'):
                return str(v).strip()
        return ''

    def _radusuarios_postar_id_vd_contrato_no_ixc(self, merged_plano):
        """True = incluir ``id_vd_contrato`` (e FKs de plano) no POST ``radusuarios``."""
        if getattr(settings, 'IXC_RADUSUARIOS_ENVIAR_ID_VD_CONTRATO', False):
            return True
        if getattr(settings, 'IXC_RADUSUARIOS_ENVIAR_ID_VD_SE_MERGE_CONTRATO', True):
            return isinstance(merged_plano, list) and 'id_vd_contrato' in merged_plano
        return False

    @staticmethod
    def _pick_contrato_row_for_vd_lookup(rows, id_contrato_prefer):
        if not rows:
            return None
        cid = str(id_contrato_prefer or '').strip()
        if not cid:
            return rows[0]
        for r in rows:
            if not isinstance(r, dict):
                continue
            rid = IXCIntegration._cliente_contrato_row_id_contrato(r)
            if rid and rid == cid:
                return r
        return rows[0]

    def _vd_lookup_qtypes_for_resource(self, resource):
        r = (resource or '').strip()
        rlow = r.lower()
        base_cc = (settings.IXC_CLIENTE_CONTRATO_RESOURCE or 'cliente_contrato').strip().lower()
        if rlow == base_cc or rlow.split('/')[-1] == base_cc:
            return (
                'cliente_contrato.id_vd_contrato',
                'id_vd_contrato',
            )
        short = rlow.split('/')[-1].replace('-', '_')
        return (f'{short}.id', 'id')

    def _fetch_radusuarios_plano_aux_row_via_vd(self, id_vd, id_contrato=None):
        """Listagens auxiliares pelo ``id_vd_contrato`` (vd_contrato indisponível no demo → ``cliente_contrato``)."""
        logs = []
        vid = str(id_vd or '').strip()
        if not vid or not self.url or not self.token:
            return None, logs
        raw = (getattr(settings, 'IXC_RADUSUARIOS_VD_LOOKUP_RESOURCES', None) or '').strip()
        if raw:
            resources = [x.strip() for x in raw.split(',') if x.strip()]
        else:
            resources = [(getattr(settings, 'IXC_VD_CONTRATO_RESOURCE', None) or 'vd_contrato').strip()]
        for resource in resources:
            endpoint = f'{self.url}/webservice/v1/{resource}'
            for qtype in self._vd_lookup_qtypes_for_resource(resource):
                payload = {
                    'qtype': qtype,
                    'query': vid,
                    'oper': '=',
                    'page': '1',
                    'rp': '50',
                    'sortname': 'id',
                    'sortorder': 'desc',
                }
                etapa = f'PLANO_AUX_{resource.replace("/", "_")}'
                result = self._post_ixc(
                    endpoint,
                    payload,
                    etapa,
                    extra_headers={'ixcsoft': 'listar'},
                )
                if result.get('status') != 'success':
                    logs.append(
                        f'[RADUSUARIOS] listar_plano_aux recurso={resource} qtype={qtype} http: '
                        f'{result.get("message", "")[:80]}'
                    )
                    continue
                data = result.get('data')
                if not isinstance(data, dict) or str(data.get('type', '')).lower() == 'error':
                    msg = str(data.get('message', ''))[:120] if isinstance(data, dict) else ''
                    logs.append(
                        f'[RADUSUARIOS] listar_plano_aux recurso={resource} qtype={qtype} erro_api: {msg}'
                    )
                    continue
                rows = data.get('registros')
                if not isinstance(rows, list):
                    rows = data.get('records')
                if not isinstance(rows, list) or not rows:
                    continue
                dict_rows = [r for r in rows if isinstance(r, dict)]
                if not dict_rows:
                    continue
                chosen = self._pick_contrato_row_for_vd_lookup(dict_rows, id_contrato)
                if chosen is None:
                    continue
                logs.append(
                    f'[RADUSUARIOS] plano_aux recurso={resource} qtype={qtype} linhas={len(dict_rows)} '
                    f'(id_contrato_pref={id_contrato or "-"})'
                )
                return chosen, logs
        logs.append('[RADUSUARIOS] plano_aux: nenhuma listagem retornou linha para este id_vd_contrato')
        return None, logs

    @staticmethod
    def _radusuarios_row_id_contrato(row):
        if not isinstance(row, dict):
            return ''
        for pref in ('id_contrato', 'contrato_id'):
            v = row.get(pref)
            if v not in (None, '', 0, '0'):
                return str(v).strip()
        for k, v in row.items():
            if not isinstance(k, str) or v in (None, '', 0, '0'):
                continue
            if k.split('.')[-1] in ('id_contrato', 'contrato_id'):
                return str(v).strip()
        return ''

    @staticmethod
    def _radusuarios_row_id_vd_contrato(row):
        if not isinstance(row, dict):
            return ''
        for pref in ('id_vd_contrato',):
            v = row.get(pref)
            if v not in (None, '', 0, '0'):
                return str(v).strip()
        for k, v in row.items():
            if not isinstance(k, str) or v in (None, '', 0, '0'):
                continue
            if k.split('.')[-1] == 'id_vd_contrato':
                return str(v).strip()
        return ''

    def _fetch_radusuarios_primeiro_por_id_contrato(self, id_contrato, id_vd_contrato_prefer=None):
        """Linha ``radusuarios`` (listar) com o mesmo ``id_contrato``.

        Se ``id_vd_contrato_prefer`` for informado, usa só linha cujo ``id_vd_contrato`` coincida
        (evita copiar grupo/mapa de login de outro plano no mesmo contrato → «plano não existe»).
        """
        logs = []
        cid = str(id_contrato or '').strip()
        vd_pref = str(id_vd_contrato_prefer or '').strip()
        if not cid or not self.url or not self.token:
            return None, logs
        resource = (getattr(settings, 'IXC_RADUSUARIOS_RESOURCE', None) or 'radusuarios').strip()
        endpoint = f'{self.url}/webservice/v1/{resource}'
        for qtype in ('radusuarios.id_contrato', 'id_contrato'):
            payload = {
                'qtype': qtype,
                'query': cid,
                'oper': '=',
                'page': '1',
                'rp': '30',
                'sortname': 'id',
                'sortorder': 'asc',
            }
            result = self._post_ixc(
                endpoint,
                payload,
                'RADUSUARIOS_LISTAR_CONTRATO',
                extra_headers={'ixcsoft': 'listar'},
            )
            if result.get('status') != 'success':
                logs.append(
                    f'[RADUSUARIOS] listar_radusuarios_contrato qtype={qtype} http: '
                    f'{(result.get("message") or "")[:100]}'
                )
                continue
            data = result.get('data')
            if not isinstance(data, dict) or str(data.get('type', '')).lower() == 'error':
                msg = str(data.get('message', ''))[:120] if isinstance(data, dict) else ''
                logs.append(f'[RADUSUARIOS] listar_radusuarios_contrato qtype={qtype} erro_api: {msg}')
                continue
            rows = data.get('registros')
            if not isinstance(rows, list):
                rows = data.get('records')
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list):
                continue
            dict_rows = [r for r in rows if isinstance(r, dict)]
            if not dict_rows:
                logs.append(f'[RADUSUARIOS] listar_radusuarios_contrato qtype={qtype} sem_registros')
                continue
            chosen = None
            if vd_pref:
                for r in dict_rows:
                    if self._radusuarios_row_id_vd_contrato(r) == vd_pref:
                        chosen = r
                        break
                if chosen is None:
                    logs.append(
                        f'[RADUSUARIOS] listar_radusuarios_contrato qtype={qtype} linhas={len(dict_rows)} '
                        f'sem id_vd_contrato={vd_pref!r} no radius — não reutilizar grupo/mapa de outro plano.'
                    )
                    continue
            else:
                chosen = dict_rows[0]
            logs.append(
                f'[RADUSUARIOS] listar_radusuarios_contrato qtype={qtype} linhas={len(dict_rows)} '
                f'(modelo grupo/mapa{" id_vd=" + vd_pref if vd_pref else ""})'
            )
            return chosen, logs
        logs.append('[RADUSUARIOS] listar_radusuarios_contrato: sem linha neste id_contrato' + (f' id_vd={vd_pref!r}' if vd_pref else ''))
        return None, logs

    def _fetch_radusuarios_modelo_por_cliente_e_plano(self, id_cliente, id_vd, id_contrato):
        """Listar ``radusuarios`` por id_cliente; prefere mesma id_contrato, senão mesmo id_vd_contrato, senão 1ª linha."""
        logs = []
        icy = str(id_cliente or '').strip()
        if not icy or not self.url or not self.token:
            return None, logs
        resource = (getattr(settings, 'IXC_RADUSUARIOS_RESOURCE', None) or 'radusuarios').strip()
        endpoint = f'{self.url}/webservice/v1/{resource}'
        vd_w = str(id_vd or '').strip()
        ctr_w = str(id_contrato or '').strip()
        for qtype in (
            'radusuarios.id_cliente',
            'radusuarios.cliente_id',
            'id_cliente',
            'cliente_id',
            'radusuarios.id_cliente_principal',
        ):
            payload = {
                'qtype': qtype,
                'query': icy,
                'oper': '=',
                'page': '1',
                'rp': '80',
                'sortname': 'id',
                'sortorder': 'desc',
            }
            result = self._post_ixc(
                endpoint,
                payload,
                'RADUSUARIOS_LISTAR_CLIENTE',
                extra_headers={'ixcsoft': 'listar'},
            )
            if result.get('status') != 'success':
                logs.append(
                    f'[RADUSUARIOS] listar_radusuarios_cliente qtype={qtype} http: '
                    f'{(result.get("message") or "")[:100]}'
                )
                continue
            data = result.get('data')
            if not isinstance(data, dict) or str(data.get('type', '')).lower() == 'error':
                msg = str(data.get('message', ''))[:120] if isinstance(data, dict) else ''
                logs.append(f'[RADUSUARIOS] listar_radusuarios_cliente qtype={qtype} erro_api: {msg}')
                continue
            rows = data.get('registros')
            if not isinstance(rows, list):
                rows = data.get('records')
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list):
                logs.append(
                    f'[RADUSUARIOS] listar_radusuarios_cliente qtype={qtype} rows_nao_lista '
                    f'type={type(rows).__name__} data_keys={list(data.keys())[:12]!r}'
                )
                continue
            dict_rows = [r for r in rows if isinstance(r, dict)]
            if not dict_rows:
                logs.append(f'[RADUSUARIOS] listar_radusuarios_cliente qtype={qtype} sem_registros')
                continue
            chosen = None
            if ctr_w:
                for r in dict_rows:
                    if self._radusuarios_row_id_contrato(r) == ctr_w:
                        chosen = r
                        break
            if chosen is None and vd_w:
                for r in dict_rows:
                    if self._radusuarios_row_id_vd_contrato(r) == vd_w:
                        chosen = r
                        break
            if chosen is None:
                chosen = dict_rows[0]
            logs.append(
                f'[RADUSUARIOS] listar_radusuarios_cliente qtype={qtype} linhas={len(dict_rows)} '
                f'(modelo grupo/mapa por contrato/vd)'
            )
            return chosen, logs
        logs.append('[RADUSUARIOS] listar_radusuarios_cliente: falhou')
        return None, logs

    @staticmethod
    def _merge_radusuarios_grupo_tipo_apenas_de_linha_radius(row, payload, merged_plano):
        """Copia só ``id_grupo`` / ``tipo_conexao_mapa`` (e sinônimos) de uma linha ``listar radusuarios``."""
        applied = []
        if not isinstance(row, dict) or not isinstance(payload, dict) or not isinstance(merged_plano, list):
            return applied
        grupo_tails = (
            'id_grupo',
            'id_grupo_login',
            'id_grupo_radius',
            'id_grupo_pppoe',
            'id_grupo_internet',
            'id_grupo_rad',
        )
        mapa_tails = (
            'tipo_conexao_mapa',
            'id_tipo_conexao_mapa',
            'id_mapa_acesso',
            'id_mapa',
            'id_tipo_conexao',
        )
        for tail in grupo_tails:
            hit = None
            for k, v in row.items():
                if not isinstance(k, str) or v in (None, '', 0, '0'):
                    continue
                if k == tail or k.split('.')[-1] == tail:
                    hit = v
                    break
            if hit is not None:
                payload['id_grupo'] = hit
                if 'id_grupo' not in merged_plano:
                    merged_plano.append('id_grupo')
                applied.append('id_grupo')
                break
        for tail in mapa_tails:
            hit = None
            for k, v in row.items():
                if not isinstance(k, str) or v in (None, '', 0, '0'):
                    continue
                if k == tail or k.split('.')[-1] == tail:
                    hit = v
                    break
            if hit is not None:
                payload['tipo_conexao_mapa'] = hit
                if 'tipo_conexao_mapa' not in merged_plano:
                    merged_plano.append('tipo_conexao_mapa')
                applied.append('tipo_conexao_mapa')
                break
        return applied

    @staticmethod
    def _merge_radusuarios_fallback_desde_linha_cc(row, payload, merged_plano, lookup_logs, enabled):
        """Sem modelo ``radusuarios``: tenta mapa/grupo a partir de colunas comuns no ``listar cliente_contrato``."""
        if (
            not enabled
            or not isinstance(row, dict)
            or not isinstance(payload, dict)
            or not isinstance(merged_plano, list)
            or not isinstance(lookup_logs, list)
        ):
            return
        if 'tipo_conexao_mapa' not in merged_plano:
            for tail in ('id_tipo_conexao_mapa', 'id_mapa', 'id_mapa_acesso', 'id_tipo_contrato'):
                for k, v in row.items():
                    if not isinstance(k, str) or v in (None, '', 0, '0'):
                        continue
                    if k.split('.')[-1] != tail:
                        continue
                    s = str(v).strip()
                    if s.isdigit():
                        payload['tipo_conexao_mapa'] = s
                        merged_plano.append('tipo_conexao_mapa')
                        lookup_logs.append(
                            f'[RADUSUARIOS] tipo_conexao_mapa via {tail} da linha cliente_contrato (fallback).'
                        )
                        break
                else:
                    continue
                break
        if 'id_grupo' not in merged_plano:
            for k, v in row.items():
                if not isinstance(k, str) or v in (None, '', 0, '0'):
                    continue
                tail = k.split('.')[-1].lower()
                if tail != 'tipo_produtos_plano':
                    continue
                s = str(v).strip()
                m = re.search(r'\d{1,12}', s)
                if m:
                    payload['id_grupo'] = m.group(0)
                    merged_plano.append('id_grupo')
                    lookup_logs.append(
                        '[RADUSUARIOS] id_grupo via 1º número em tipo_produtos_plano (fallback; valide no IXC).'
                    )
                break
        if 'id_grupo' not in merged_plano:
            for k, v in row.items():
                if not isinstance(k, str) or v in (None, '', 0, '0'):
                    continue
                tail = k.split('.')[-1].lower()
                if 'grupo' not in tail or any(x in tail for x in ('descont', 'cancel', 'vended', 'comis', 'cobr')):
                    continue
                s = str(v).strip()
                if s.isdigit():
                    payload['id_grupo'] = s
                    merged_plano.append('id_grupo')
                    lookup_logs.append(f'[RADUSUARIOS] id_grupo via coluna {tail} (fallback).')
                    break

    @staticmethod
    def _merge_radusuarios_plano_desde_contrato(row, payload):
        """Sobrescreve FKs de plano/conexão com o que está no contrato (evita «plano não existe neste contrato»).

        A listagem IXC costuma trazer chaves com prefixo (ex.: ``cliente_contrato.id_grupo``) — usamos o sufixo.
        Retorna lista de chaves canônicas efetivamente aplicadas ao payload.
        """
        merged = []
        if not isinstance(row, dict) or not isinstance(payload, dict):
            return merged
        wanted = {
            'id_vd_contrato',
            'id_plano',
            'id_plano_venda',
            'id_plano_velocidade',
            'id_grupo',
            'tipo_conexao_mapa',
            'id_tipo_conexao_mapa',
            'id_mapa_acesso',
            'id_concentrador',
            'id_porta_servico',
            'id_tipo_conexao',
            'id_mapa',
            'id_servico',
            'id_servico_plano',
            'id_produto',
            'id_produto_plano',
        }
        synonyms = (
            ('id_grupo', ('id_grupo_rad', 'id_grupo_radius', 'grupo_id', 'id_grupo_internet', 'id_grupo_login', 'id_grupo_pppoe')),
            (
                'tipo_conexao_mapa',
                (
                    'id_tipo_conexao_mapa',
                    'tipo_conexao',
                    'id_mapa_conexao',
                    'id_matriz_conexao',
                    'id_mapa_acesso',
                    'mapa_conexao',
                    'id_tipo_conexao_mapa_cliente',
                ),
            ),
            ('id_vd_contrato', ('vd_contrato', 'id_vd_contrato_plano', 'id_plano_contrato')),
        )

        for k, v in row.items():
            if not isinstance(k, str) or v in (None, '', 0, '0'):
                continue
            tail = k.split('.')[-1]
            if tail in wanted:
                payload[tail] = v
                if tail not in merged:
                    merged.append(tail)

        for dst, srcs in synonyms:
            if dst in merged:
                continue
            for s in srcs:
                hit = None
                for k, v in row.items():
                    if not isinstance(k, str) or v in (None, '', 0, '0'):
                        continue
                    if k == s or k.split('.')[-1] == s:
                        hit = v
                        break
                if hit is not None:
                    payload[dst] = hit
                    merged.append(dst)
                    break

        # Heurística: ``tipo_conexao`` (sem _mapa) ou chave com tipo+conexao+mapa no nome.
        for k, v in row.items():
            if not isinstance(k, str) or v in (None, '', 0, '0'):
                continue
            if 'tipo_conexao_mapa' in merged:
                break
            tail = k.split('.')[-1].lower()
            if 'tipo' in tail and 'conex' in tail and ('mapa' in tail or tail == 'tipo_conexao'):
                payload['tipo_conexao_mapa'] = v
                merged.append('tipo_conexao_mapa')
                break

        if 'tipo_conexao_mapa' not in merged:
            for k, v in row.items():
                if not isinstance(k, str) or v in (None, '', 0, '0'):
                    continue
                tail = k.split('.')[-1].lower()
                if tail in ('id_mapa', 'id_tipo_conexao_mapa', 'tipo_conexao_mapa'):
                    payload['tipo_conexao_mapa'] = v
                    merged.append('tipo_conexao_mapa')
                    break

        if 'id_grupo' not in merged:
            for k, v in row.items():
                if not isinstance(k, str) or v in (None, '', 0, '0'):
                    continue
                tail = k.split('.')[-1].lower()
                if tail == 'grupo':
                    payload['id_grupo'] = v
                    merged.append('id_grupo')
                    break
                if re.match(r'^id_.*grupo.*$', tail) and 'cancel' not in tail and 'descont' not in tail:
                    payload['id_grupo'] = v
                    merged.append('id_grupo')
                    break

        # Scavenge: colunas fora do conjunto ``wanted`` (ex.: id_grupo_login, id_tipo_conexao_mapa_cliente).
        if not str(payload.get('id_grupo', '') or '').strip():
            best_v = None
            best_rank = 999
            for k, v in row.items():
                if not isinstance(k, str) or v in (None, '', 0, '0'):
                    continue
                tail = k.split('.')[-1].lower()
                rank = None
                if tail in ('id_grupo', 'grupo_id'):
                    rank = 0
                elif tail in ('id_grupo_login', 'id_grupo_radius', 'id_grupo_pppoe', 'id_grupo_internet'):
                    rank = 2
                elif re.match(r'^id_[a-z0-9_]*grupo[a-z0-9_]*$', tail) and not any(
                    x in tail for x in ('descont', 'cancel', 'vended', 'comiss', 'cobr', 'filial')
                ):
                    rank = 10 + len(tail)
                if rank is not None and rank < best_rank:
                    best_rank = rank
                    best_v = v
            if best_v is not None:
                payload['id_grupo'] = best_v
                merged.append('id_grupo')

        if not str(payload.get('tipo_conexao_mapa', '') or '').strip():
            best_v = None
            best_rank = 999
            for k, v in row.items():
                if not isinstance(k, str) or v in (None, '', 0, '0'):
                    continue
                tail = k.split('.')[-1].lower()
                rank = None
                if tail in ('id_mapa', 'id_tipo_conexao_mapa', 'tipo_conexao_mapa', 'id_tipo_conexao'):
                    rank = len(tail)
                elif tail == 'tipo_conexao':
                    rank = 20
                elif 'conex' in tail and 'mapa' in tail:
                    rank = 40 + len(tail)
                if rank is not None and rank < best_rank:
                    best_rank = rank
                    best_v = v
            if best_v is not None:
                payload['tipo_conexao_mapa'] = best_v
                merged.append('tipo_conexao_mapa')

        # IXC às vezes expõe o mapa só no nome longo da coluna (ex.: cliente_contrato.id_tipo_conexao_mapa_acesso).
        if 'tipo_conexao_mapa' not in merged:
            for k, v in row.items():
                if not isinstance(k, str) or v in (None, '', 0, '0'):
                    continue
                lk = k.lower()
                if ('tipo_conexao' in lk) or ('tipo' in lk and ('mapa' in lk or 'conex' in lk)):
                    payload['tipo_conexao_mapa'] = v
                    merged.append('tipo_conexao_mapa')
                    break

        # O POST ``radusuarios`` valida ``tipo_conexao_mapa``; a listagem pode expor só id_mapa / id_tipo_conexao.
        if not str(payload.get('tipo_conexao_mapa', '') or '').strip():
            for alt in ('id_mapa', 'id_tipo_conexao_mapa', 'id_tipo_conexao'):
                v = payload.get(alt)
                if v in (None, '', 0, '0'):
                    continue
                payload['tipo_conexao_mapa'] = v
                if 'tipo_conexao_mapa' not in merged:
                    merged.append('tipo_conexao_mapa')
                break

        return merged

    @staticmethod
    def _merge_radusuarios_endereco_desde_contrato(row, payload):
        """Copia chaves de endereço do retorno listar cliente_contrato para o POST radusuarios."""
        if not isinstance(row, dict) or not isinstance(payload, dict):
            return
        prefer = (
            'endereco',
            'numero',
            'bairro',
            'complemento',
            'cep',
            'cidade',
            'id_cidade',
            'referencia',
            'uf',
            'latitude',
            'longitude',
            'endereco_padrao_cliente',
            'endereco_novo',
            'numero_novo',
            'bairro_novo',
            'cep_novo',
            'cidade_novo',
            'complemento_novo',
            'referencia_novo',
            'id_endereco',
        )
        for k in prefer:
            if k not in row:
                continue
            v = row.get(k)
            if v in (None, ''):
                continue
            if k == 'cidade' and str(v).strip() in ('0',):
                continue
            if k == 'id_cidade' and str(v).strip() in ('0',):
                continue
            payload[k] = v

    def _completar_radusuarios_campos_obrigatorios(self, payload, lookup_logs):
        """Remove duplicatas id_plano=id_vd. Completa tipo/grupo do .env quando ainda vazios (IXC exige ambos).
        Com só ``id_contrato`` (sem ``id_vd_contrato`` no POST), também completa a partir do .env.
        ``IXC_RADUSUARIOS_FORCAR_GRUPO_MAPA_COM_VD_CONTRATO``: sobrescreve sempre com .env (pode gerar «plano não existe»)."""
        vd_raw = str(payload.get('id_vd_contrato', '') or '').strip()
        id_ctr = str(payload.get('id_contrato', '') or '').strip()
        if not vd_raw and not id_ctr:
            return
        if vd_raw:
            vd_norm = self._ixc_fk_value(vd_raw)
            for k in ('id_plano', 'id_plano_venda', 'id_plano_velocidade'):
                if k not in payload:
                    continue
                pv = self._ixc_fk_value(str(payload.get(k, '')).strip())
                if vd_norm is not None and pv is not None and str(pv) == str(vd_norm):
                    del payload[k]
                    lookup_logs.append(
                        f'[RADUSUARIOS] removido {k} (igual a id_vd_contrato; evita «plano não existe neste contrato»)'
                    )
        forcar = getattr(settings, 'IXC_RADUSUARIOS_FORCAR_GRUPO_MAPA_COM_VD_CONTRATO', False)
        if forcar:
            payload['tipo_conexao_mapa'] = (settings.IXC_RADUSUARIOS_TIPO_CONEXAO_MAPA or '58').strip()
            payload['id_grupo'] = (settings.IXC_RADUSUARIOS_ID_GRUPO or '9').strip()
            lookup_logs.append(
                '[RADUSUARIOS] tipo_conexao_mapa+id_grupo=forçados .env (IXC_RADUSUARIOS_FORCAR_GRUPO_MAPA_COM_VD_CONTRATO=True)'
            )
            return
        if not str(payload.get('tipo_conexao_mapa', '') or '').strip():
            payload['tipo_conexao_mapa'] = (settings.IXC_RADUSUARIOS_TIPO_CONEXAO_MAPA or '58').strip()
            lookup_logs.append(
                '[RADUSUARIOS] tipo_conexao_mapa=complemento .env'
                + (' (há id_vd_contrato)' if vd_raw else ' (id_contrato sem id_vd no POST)')
            )
        if not str(payload.get('id_grupo', '') or '').strip():
            payload['id_grupo'] = (settings.IXC_RADUSUARIOS_ID_GRUPO or '9').strip()
            lookup_logs.append(
                '[RADUSUARIOS] id_grupo=complemento .env'
                + (' (há id_vd_contrato)' if vd_raw else ' (id_contrato sem id_vd no POST)')
            )

    def resolve_cidade_ixc_id(self, cidade_slug):
        try:
            from .operacao_models import CidadeOperacao

            c = CidadeOperacao.objects.get(slug=cidade_slug)
            if (c.ixc_cidade_id or '').strip():
                return c.ixc_cidade_id.strip()
        except Exception:
            pass
        return self.CIDADES_MAP.get(cidade_slug, '') or ''

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
        razao = (ixc_data.get('nome_razao') or '').strip().upper() or 'CADASTRO_WEB'
        fantasia = ((cadastro.nome_fantasia or '').strip() or (ixc_data.get('nome_razao') or '').strip()).upper()
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
            'responsavel': '',
            'indicado_por': '',
            'status_prospeccao': 'N',
            'tipo_pessoa': tipo_ixc,
            'cnpj_cpf': doc_display,
            'ie_identidade': ie_ident,
            'data_nascimento': dt_nasc,
            'filial_id': filial_str,
            'ativo': 'S',
            'data_cadastro': dt_cad,
            'prospeccao_ultimo_contato': '',
            'prospeccao_proximo_contato': '',
            'id_vendedor': '',
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
            all_logs.append(f'[CRM_CANDIDATOS] recurso_ativo={resource} id={candidato_id}')
            return {
                'status': 'success',
                'candidato_id': candidato_id,
                'candidato_resource': resource,
                'message': '',
                'logs': all_logs,
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
        Cria prospecção no IXC, reutilizando a ficha do cadastro.
        Tenta vários nomes de recurso até um aceitar o POST (configurável por IXC_CRM_PROSPECT_RESOURCE).
        `force=True` ignora IXC_CREATE_CRM_PROSPECT (etapa 2 do painel).
        """
        if not force and not getattr(settings, 'IXC_CREATE_CRM_PROSPECT', False):
            return {
                'status': 'skipped',
                'message': 'IXC_CREATE_CRM_PROSPECT=False',
                'logs': ['[CRM_PROSPECT] desativado nas configurações (use etapa 2 com force ou ative o .env).'],
            }
        if not self.url or not self.token:
            return {
                'status': 'error',
                'message': 'API do IXC não configurada.',
                'logs': ['[CRM_PROSPECT] IXC_API_URL/IXC_API_TOKEN ausentes.'],
            }
        payload = self.build_crm_prospect_payload(
            cadastro,
            link_contato_id=link_contato_id,
            ixc_lead_resource=ixc_lead_resource,
        )
        debug_path = self._save_debug_json(cadastro.pk, payload, 'CRM_PROSPECT')
        all_logs = []
        if debug_path:
            all_logs.append(f'[CRM_PROSPECT] debug_json={debug_path}')
        if link_contato_id:
            all_logs.append(
                f'[CRM_PROSPECT] vinculo_ixc_id={link_contato_id} recurso_etapa1={ixc_lead_resource or "(vazio)"}'
            )

        resources_to_try = self._crm_prospect_resources_to_try()
        last_error = None
        for idx, resource in enumerate(resources_to_try):
            endpoint = f"{self.url}/webservice/v1/{resource}"
            result = self._post_ixc(
                endpoint,
                payload,
                'CRM_PROSPECT',
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
                        f'[CRM_PROSPECT] recurso `{resource}` indisponível no IXC; tentando `{nxt}`.'
                    )
                else:
                    all_logs.append(
                        f'[CRM_PROSPECT] recurso `{resource}` indisponível no IXC (sem mais recursos na fila).'
                    )
                last_error = result
                continue

            if result.get('status') != 'success':
                return {
                    'status': 'error',
                    'message': result.get('message') or 'Falha HTTP ao criar prospecção.',
                    'logs': all_logs,
                }

            if response_type == 'error':
                return {
                    'status': 'error',
                    'message': response_message or 'IXC retornou erro ao criar prospecção.',
                    'logs': all_logs + [f'[CRM_PROSPECT] erro_api: {response_message}'],
                }

            prospect_id = self._extract_id(response_data)
            if prospect_id in (None, '', 0, '0'):
                if isinstance(response_data, dict) and len(response_data) == 0:
                    all_logs.append(
                        '[CRM_PROSPECT] IXC retornou 200 com JSON vazio (doc: sem corpo). '
                        'Confira no CRM se a prospecção foi criada.'
                    )
                    return {
                        'status': 'warning',
                        'prospect_id': None,
                        'prospect_resource': resource,
                        'message': 'IXC aceitou o cadastro da prospecção sem retornar ID no JSON. Verifique no IXC.',
                        'logs': all_logs,
                    }
                return {
                    'status': 'error',
                    'message': 'IXC não retornou ID da prospecção.',
                    'logs': all_logs + ['[CRM_PROSPECT] id ausente na resposta'],
                }
            all_logs.append(f'[CRM_PROSPECT] recurso_ativo={resource} id={prospect_id}')
            return {
                'status': 'success',
                'prospect_id': prospect_id,
                'prospect_resource': resource,
                'message': '',
                'logs': all_logs,
            }

        msg_tail = ''
        if last_error and isinstance(last_error.get('data'), dict):
            msg_tail = str(last_error['data'].get('message', '') or '')
        base_msg = msg_tail or 'Nenhum recurso de prospecção disponível neste IXC.'
        if self._is_demo_ixc_host() and last_error and self._is_resource_unavailable(last_error):
            base_msg = (
                f'{base_msg} '
                'No IXC demo (demo.ixcsoft.com.br) o webservice de prospecção costuma não existir; '
                'a etapa 1 em `contato` é a suportada. Para a etapa 2, use o IXC do seu provedor e o recurso '
                'indicado no Postman (IXC_CRM_PROSPECT_RESOURCE / IXC_CRM_PROSPECT_FALLBACK_RESOURCES).'
            )
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

        # Salva o JSON para auditoria
        debug_path = self._save_debug_json(cadastro.pk, payload, 'CRM_LEAD')

        try:
            all_logs = []
            all_logs.append(
                '[CRM_LEAD] payload sem plano/canal/campanha/contrato — só ficha CRM (contato/crm_*).'
            )
            if getattr(settings, 'IXC_LEAD_CONTATO_ONLY', True) and not self.lead_resource_override:
                all_logs.append(
                    '[CRM_LEAD] IXC_LEAD_CONTATO_ONLY=True — apenas webservice `contato` (sem fallback crm_leads).'
                )
            if debug_path:
                all_logs.append(f"[DEBUG] JSON gerado em: {debug_path}")

            last_error = None
            resources_to_try = self._crm_lead_resources_to_try()

            for idx, resource in enumerate(resources_to_try):
                endpoint = f"{self.url}/webservice/v1/{resource}"
                result = self._post_ixc(
                    endpoint,
                    payload,
                    'CRM_LEAD',
                    extra_headers={'ixcsoft': 'incluir'},
                )
                all_logs.extend(result.get('logs', []))

                response_data = result.get('data') if result.get('status') == 'success' else None
                response_preview = json.dumps(response_data, ensure_ascii=False)[:600] if response_data is not None else ''
                if response_preview:
                    all_logs.append(f"[CRM_LEAD] resposta: {response_preview}")

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
                    all_logs.append(f"[CRM_LEAD] erro_api: {result['message']}")
                    result['logs'] = all_logs
                    return result

                lead_id = self._extract_id(response_data)
                if lead_id in (None, '', 0, '0'):
                    result['status'] = 'error'
                    result['message'] = "IXC respondeu HTTP 200, mas não retornou ID do Lead."
                    all_logs.append("[CRM_LEAD] erro: id ausente na resposta")
                    result['logs'] = all_logs
                    return result

                result['lead_id'] = lead_id
                result['lead_resource'] = resource
                all_logs.append(f"[CRM_LEAD] recurso_ativo={resource}")
                # Segundo POST pode duplicar lead em alguns ambientes IXC — desativado por padrão.
                if self.lead_post_alterar and resource in (
                    'contato',
                    'crm_lead',
                    'crm_sp_leads',
                    'crm_leads',
                ):
                    patch = self._ixc_alterar_mesmo_payload(resource, lead_id, payload)
                    all_logs.append('[CRM_LEAD] pós-inclusão: alterar (IXC_LEAD_POST_ALTERAR=True)')
                    all_logs.extend(patch.get('logs', []))
                    pdata = patch.get('data') if isinstance(patch.get('data'), dict) else {}
                    if patch.get('status') != 'success' or str(pdata.get('type', '')).lower() == 'error':
                        msg = patch.get('message') or pdata.get('message') or ''
                        all_logs.append(f"[CRM_LEAD] aviso pós-alterar: {msg or 'sem detalhe'}")
                result['logs'] = all_logs
                return result

            return {
                'status': 'error',
                'message': "Nenhum recurso de lead disponível.",
                'logs': all_logs or (last_error.get('logs', []) if last_error else []),
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e), 'logs': [f"[CRM_LEAD] excecao: {str(e)}"]}

    def _load_cliente_contrato_template(self):
        path = os.path.join(os.path.dirname(__file__), 'data', 'ixc_cliente_contrato_incluir_template.json')
        with open(path, encoding='utf-8') as f:
            return json.load(f)

    def _ixc_id_cliente_for_cadastro(self, cadastro):
        """id_cliente IXC: .env > prospecção (crm_canditados) > contato (lead)."""
        ex = (settings.IXC_CONTRATO_TEST_ID_CLIENTE or '').strip()
        if ex:
            return ex
        pid = (cadastro.ixc_prospect_id or '').strip()
        if pid:
            return pid
        return (cadastro.ixc_lead_id or '').strip()

    def _id_cliente_para_radusuarios(self, cadastro):
        """id_cliente no POST radusuarios: .env > lead ou prospect (configurável), não misturar com teste contrato."""
        ex = (settings.IXC_CONTRATO_TEST_ID_CLIENTE or '').strip()
        if ex:
            return ex
        modo = (getattr(settings, 'IXC_RADUSUARIOS_ID_CLIENTE_FONTE', None) or 'lead').strip().lower()
        lead = (cadastro.ixc_lead_id or '').strip()
        prospect = (cadastro.ixc_prospect_id or '').strip()
        if modo == 'prospect':
            return prospect or lead
        return lead or prospect

    @staticmethod
    def _slug_pppoe_login_part(text, max_len=48):
        """Apenas [a-z0-9], minúsculo, sem acentos (trecho login PPPoE)."""
        if not text:
            return ''
        nfd = unicodedata.normalize('NFD', str(text))
        ascii_v = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
        buf = []
        for c in ascii_v.lower():
            if c.isalnum():
                buf.append(c)
        return ''.join(buf)[:max_len]

    def build_pppoe_login_for_cadastro(self, cadastro):
        """Login no formato nomedarua.nomedocliente (minúsculo, só letras/números e um ponto)."""
        rua = self._slug_pppoe_login_part(cadastro.endereco, 44)
        nome = self._slug_pppoe_login_part(cadastro.nome_razao, 44)
        if not nome:
            nome = 'cliente'
        if not rua:
            rua = self._slug_pppoe_login_part(cadastro.bairro, 24) or 'rua'
        login = f'{rua}.{nome}'.lower()
        login = re.sub(r'[^a-z0-9.]', '', login)
        login = re.sub(r'\.{2,}', '.', login).strip('.')
        if len(login) > 64:
            login = login[:64].rstrip('.')
        return login or f'cli{cadastro.pk}'

    def build_radusuarios_pppoe_payload(self, cadastro):
        """POST ``radusuarios`` — login PPPoE + senha = CPF (dígitos). Retorna (payload, erro_msg, lookup_logs)."""
        from .models import only_digits_br

        lookup_logs = []

        id_cliente = self._id_cliente_para_radusuarios(cadastro)
        if not id_cliente:
            return None, (
                'id_cliente ausente para radusuarios: envie ao IXC (lead+prospecção) ou defina '
                'IXC_CONTRATO_TEST_ID_CLIENTE. Com lead e prospect, o padrão é usar o lead (contato); '
                'ajuste IXC_RADUSUARIOS_ID_CLIENTE_FONTE=prospect se o seu IXC exigir o id da prospecção.'
            ), lookup_logs

        id_contrato = (getattr(cadastro, 'ixc_contrato_id', None) or '').strip()
        if not id_contrato:
            id_contrato = (settings.IXC_RADUSUARIOS_TEST_ID_CONTRATO or '').strip()
        if not id_contrato:
            id_contrato = (settings.IXC_CONTRATO_TEST_ID_CONTRATO or '').strip()
        if not id_contrato and getattr(settings, 'IXC_RADUSUARIOS_LOOKUP_CONTRATO_LISTAR', True):
            fetched, flogs = self._fetch_first_contrato_id_for_id_cliente(id_cliente)
            lookup_logs.extend(flogs)
            if fetched:
                id_contrato = fetched
        if not id_contrato:
            return None, (
                'id_contrato ausente. O IXC exige o contrato. Opções: '
                '(1) teste «contrato + PPPoE» com sucesso — grava ixc_contrato_id; '
                '(2) IXC_RADUSUARIOS_TEST_ID_CONTRATO ou IXC_CONTRATO_TEST_ID_CONTRATO no .env; '
                '(3) contrato já existente no IXC para o mesmo id_cliente — com '
                'IXC_RADUSUARIOS_LOOKUP_CONTRATO_LISTAR=True (padrão) tentamos listar automaticamente. '
                'Confira logs acima e logs/ixc_debug/.'
            ), lookup_logs

        senha = only_digits_br(cadastro.documento)
        if not senha:
            return None, 'Documento (CPF/CNPJ) ausente para senha PPPoE.', lookup_logs
        if getattr(cadastro, 'tipo_pessoa', 'pf') == 'pf':
            if len(senha) != 11:
                return None, f'CPF deve ter 11 dígitos para senha PPPoE (encontrado {len(senha)}).', lookup_logs
        elif len(senha) != 14:
            return None, f'CNPJ deve ter 14 dígitos para senha PPPoE (encontrado {len(senha)}).', lookup_logs

        login = self.build_pppoe_login_for_cadastro(cadastro)

        ixc_data = cadastro.get_ixc_data()
        id_cidade_rs = (self.resolve_cidade_ixc_id(cadastro.cidade) or '').strip()
        _, cep_display, _ = self._ixc_display_pii(cadastro)
        endereco = (ixc_data.get('endereco') or '').strip().upper()
        if not endereco:
            endereco = 'ENDERECO NAO INFORMADO'
        bairro = (ixc_data.get('bairro') or '').strip().upper()
        if not bairro:
            bairro = 'NAO INFORMADO'
        numero = (ixc_data.get('numero') or 'S/N').strip().upper()
        cidade_val = id_cidade_rs if id_cidade_rs else (str(cadastro.cidade or '').strip() or '1')
        if str(cidade_val).strip().isdigit():
            cidade_val = self._ixc_fk_value(str(cidade_val).strip())
            payload_cidade_id = cidade_val
        else:
            payload_cidade_id = None

        payload = {
            'autenticacao': (settings.IXC_RADUSUARIOS_AUTENTICACAO or 'L').strip(),
            'id_cliente': str(id_cliente),
            'id_contrato': str(id_contrato),
            'login': login,
            'senha_md5': (settings.IXC_RADUSUARIOS_SENHA_MD5 or 'N').strip(),
            'senha': senha,
            'login_simultaneo': (settings.IXC_RADUSUARIOS_LOGIN_SIMULTANEO or '1').strip(),
            'ativo': (settings.IXC_RADUSUARIOS_ATIVO or 'S').strip(),
            'auto_preencher_ip': (settings.IXC_RADUSUARIOS_AUTO_PREENCHER_IP or 'S').strip(),
            'fixar_ip': (settings.IXC_RADUSUARIOS_FIXAR_IP or 'N').strip(),
            'relacionar_ip_ao_login': (settings.IXC_RADUSUARIOS_RELACIONAR_IP_AO_LOGIN or 'N').strip(),
            'autenticacao_por_mac': (settings.IXC_RADUSUARIOS_AUTENTICACAO_POR_MAC or 'N').strip(),
            'auto_preencher_mac': (settings.IXC_RADUSUARIOS_AUTO_PREENCHER_MAC or 'S').strip(),
            'relacionar_mac_ao_login': (settings.IXC_RADUSUARIOS_RELACIONAR_MAC_AO_LOGIN or 'S').strip(),
            'tipo_vinculo_plano': (settings.IXC_RADUSUARIOS_TIPO_VINCULO_PLANO or 'D').strip(),
            # Vários IXC exigem endereço no WS radusuarios (erro «Preencha Endereço» sem estes campos).
            'endereco': endereco,
            'numero': numero,
            'bairro': bairro,
            'complemento': (ixc_data.get('complemento') or '').strip().upper(),
            'cep': cep_display or (cadastro.cep or '').strip(),
            'cidade': cidade_val,
            'referencia': (ixc_data.get('referencia') or '').strip().upper(),
        }
        if payload_cidade_id is not None:
            payload['id_cidade'] = payload_cidade_id

        ed_pad = (getattr(settings, 'IXC_RADUSUARIOS_ENDERECO_PADRAO_CLIENTE', None) or '').strip()
        if ed_pad:
            payload['endereco_padrao_cliente'] = ed_pad
            # Algumas bases IXC validam só o nome curto do formulário.
            payload['endereco_padrao'] = ed_pad

        row = None
        merged_plano = []
        do_merge = getattr(settings, 'IXC_RADUSUARIOS_MERGE_ENDERECO_CONTRATO', True)
        if do_merge:
            row, flogs = self._fetch_cliente_contrato_row_by_id(id_contrato)
            lookup_logs.extend(flogs)
            if row:
                self._merge_radusuarios_endereco_desde_contrato(row, payload)
                merged_plano = self._merge_radusuarios_plano_desde_contrato(row, payload)
                lookup_logs.append('[RADUSUARIOS] endereco_e_plano_mesclados_do_cliente_contrato')
                lookup_logs.append(f'[RADUSUARIOS] plano_mesclado_chaves={merged_plano}')
                if not merged_plano:
                    lookup_logs.append(
                        f'[RADUSUARIOS] aviso: nenhuma FK de plano reconhecida na linha do contrato; '
                        f'amostra_chaves_ixc={sorted(row.keys())[:80]}'
                    )
                ex_cli = (settings.IXC_CONTRATO_TEST_ID_CLIENTE or '').strip()
                id_cli_ixc = self._id_cliente_from_cliente_contrato_row(row)
                cur_cli = str(payload.get('id_cliente', '') or '').strip()
                if not ex_cli and id_cli_ixc and id_cli_ixc != cur_cli:
                    payload['id_cliente'] = id_cli_ixc
                    lookup_logs.append(
                        f'[RADUSUARIOS] id_cliente alinhado ao contrato IXC: {cur_cli!r} -> {id_cli_ixc!r} '
                        f'(IXC_RADUSUARIOS_ID_CLIENTE_FONTE={getattr(settings, "IXC_RADUSUARIOS_ID_CLIENTE_FONTE", "lead")!r} '
                        'apontava outro vínculo; o listar cliente_contrato traz o dono real do contrato.)'
                    )
                elif id_cli_ixc and id_cli_ixc == cur_cli:
                    lookup_logs.append(f'[RADUSUARIOS] id_cliente conferido com listagem contrato: {cur_cli!r}')
                elif not id_cli_ixc:
                    lookup_logs.append(
                        '[RADUSUARIOS] aviso: listagem contrato sem id_cliente reconhecido nas chaves; '
                        'se «plano não existe neste contrato», tente IXC_RADUSUARIOS_ID_CLIENTE_FONTE=prospect.'
                    )
                if isinstance(merged_plano, list) and merged_plano == ['id_vd_contrato']:
                    hint = sorted(
                        k
                        for k in row
                        if isinstance(k, str)
                        and any(
                            x in k.lower()
                            for x in ('tipo', 'mapa', 'grupo', 'conex', 'plano', 'vd', 'radius', 'fibra')
                        )
                    )[:50]
                    lookup_logs.append(
                        f'[RADUSUARIOS] dica_ixc: só id_vd no merge; confira no IXC o ID de «Fibra» e do grupo. '
                        f'Chaves da listagem do contrato com tipo/map/grupo/plano (amostra)={hint}'
                    )

        # Plano de venda (id_vd_contrato): priorizar o valor do listar cliente_contrato quando o merge
        # trouxe esse campo — no IXC o ID 1 pode ser o Plano de venda real do contrato (ex.: demo).
        # Só substituímos pela ficha/Operação para '0' (inválido) ou '1' quando NÃO veio do contrato
        # (ex.: resquício sem merge), para não quebrar «Este plano não existe neste contrato!».
        vd_cur = str(payload.get('id_vd_contrato', '') or '').strip()
        ip_op = (self.resolve_plano_venda_id(cadastro.cidade, cadastro.plano) or '').strip()
        vd_veio_do_contrato = isinstance(merged_plano, list) and 'id_vd_contrato' in merged_plano
        substituir_vd_pela_ficha = False
        if ip_op and vd_cur in ('0', '1'):
            if vd_cur == '0':
                substituir_vd_pela_ficha = True
            elif vd_cur == '1' and not vd_veio_do_contrato:
                substituir_vd_pela_ficha = True
        if substituir_vd_pela_ficha:
            vnorm = self._ixc_fk_value(ip_op.strip())
            payload['id_vd_contrato'] = vnorm if vnorm is not None else ip_op.strip()
            lookup_logs.append(
                f'[RADUSUARIOS] id_vd_contrato ajustado: valor anterior {vd_cur!r} (sem plano de venda '
                f'confiável do contrato); usando ficha/Operação (resolve_plano_venda_id): {ip_op!r}'
            )
        elif vd_cur == '1' and vd_veio_do_contrato and ip_op and ip_op.strip() != '1':
            lookup_logs.append(
                '[RADUSUARIOS] id_vd_contrato=1 mantido (Plano de venda vindo do cliente_contrato; '
                f'não substituir pela ficha id={ip_op!r} — o IXC valida o plano junto ao contrato).'
            )

        icid = payload.get('id_cidade')
        if icid not in (None, '', 0, '0'):
            cval = payload.get('cidade')
            if cval in (None, '', 0, '0') or str(cval).strip() in ('0', ''):
                payload['cidade'] = str(icid).strip()
                lookup_logs.append('[RADUSUARIOS] cidade alinhada a id_cidade (evita 0 vindo do merge IXC).')

        if getattr(settings, 'IXC_RADUSUARIOS_LOOKUP_VD_CONTRATO_LISTAR', True) and self._radusuarios_postar_id_vd_contrato_no_ixc(
            merged_plano
        ):
            ivd = str(payload.get('id_vd_contrato') or '').strip()
            if ivd:
                falta_tipo = not str(payload.get('tipo_conexao_mapa') or '').strip()
                falta_grupo = not str(payload.get('id_grupo') or '').strip()
                if falta_tipo or falta_grupo:
                    aux_row, vlogs = self._fetch_radusuarios_plano_aux_row_via_vd(ivd, id_contrato)
                    lookup_logs.extend(vlogs)
                    if aux_row:
                        extra = self._merge_radusuarios_plano_desde_contrato(aux_row, payload)
                        for k in extra:
                            if k not in merged_plano:
                                merged_plano.append(k)
                        lookup_logs.append(f'[RADUSUARIOS] plano_complementado_via_listagem_vd chaves={extra}')

        env_fallback = getattr(
            settings, 'IXC_RADUSUARIOS_USAR_GRUPO_MAPA_ENV_SE_CONTRATO_SEM_FK', False
        )
        usar_grupo_env = (not do_merge) or (row is None) or (do_merge and row is not None and not merged_plano and env_fallback)
        if usar_grupo_env:
            payload['tipo_conexao_mapa'] = (settings.IXC_RADUSUARIOS_TIPO_CONEXAO_MAPA or '58').strip()
            payload['id_grupo'] = (settings.IXC_RADUSUARIOS_ID_GRUPO or '9').strip()
            lookup_logs.append(
                '[RADUSUARIOS] id_grupo+tipo_conexao_mapa via .env '
                '(merge off, sem linha de contrato, ou IXC_RADUSUARIOS_USAR_GRUPO_MAPA_ENV_SE_CONTRATO_SEM_FK=True)'
            )

        if getattr(settings, 'IXC_RADUSUARIOS_LISTAR_MODELO_RADIUS', True) and isinstance(merged_plano, list):
            falta_grupo_no_merge = 'id_grupo' not in merged_plano
            falta_mapa_no_merge = 'tipo_conexao_mapa' not in merged_plano
            if falta_grupo_no_merge or falta_mapa_no_merge:
                ivd_rad = str(payload.get('id_vd_contrato', '') or '').strip()
                rad_mod, rlogs = self._fetch_radusuarios_primeiro_por_id_contrato(
                    str(id_contrato),
                    id_vd_contrato_prefer=ivd_rad or None,
                )
                lookup_logs.extend(rlogs)
                if isinstance(rad_mod, dict):
                    ex = self._merge_radusuarios_grupo_tipo_apenas_de_linha_radius(rad_mod, payload, merged_plano)
                    if ex:
                        lookup_logs.append(
                            f'[RADUSUARIOS] grupo_mapa_de_radusuarios_mesmo_contrato chaves={ex}'
                        )
                falta_grupo_no_merge = 'id_grupo' not in merged_plano
                falta_mapa_no_merge = 'tipo_conexao_mapa' not in merged_plano
                if (falta_grupo_no_merge or falta_mapa_no_merge) and str(
                    payload.get('id_cliente', '') or ''
                ).strip():
                    icy = str(payload['id_cliente']).strip()
                    ivd = str(payload.get('id_vd_contrato', '') or '').strip()
                    rad2, rlogs2 = self._fetch_radusuarios_modelo_por_cliente_e_plano(icy, ivd, str(id_contrato))
                    lookup_logs.extend(rlogs2)
                    if isinstance(rad2, dict):
                        ex2 = self._merge_radusuarios_grupo_tipo_apenas_de_linha_radius(rad2, payload, merged_plano)
                        if ex2:
                            lookup_logs.append(
                                f'[RADUSUARIOS] grupo_mapa_de_radusuarios_mesmo_cliente_plano chaves={ex2}'
                            )

        if row and isinstance(row, dict):
            IXCIntegration._merge_radusuarios_fallback_desde_linha_cc(
                row,
                payload,
                merged_plano,
                lookup_logs,
                getattr(settings, 'IXC_RADUSUARIOS_FALLBACK_CC_LINHA_PARA_MAPA', True),
            )

        self._completar_radusuarios_campos_obrigatorios(payload, lookup_logs)

        if getattr(settings, 'IXC_RADUSUARIOS_OMITIR_GRUPO_MAPA_ENV_COM_VD_MERGE', True) and isinstance(
            merged_plano, list
        ) and 'id_vd_contrato' in merged_plano:
            if 'id_grupo' not in merged_plano and 'id_grupo' in payload:
                payload.pop('id_grupo', None)
                lookup_logs.append(
                    '[RADUSUARIOS] omitido id_grupo (merge do contrato não trouxe; 9 do .env costuma invalidar o plano). '
                    'IXC_RADUSUARIOS_OMITIR_GRUPO_MAPA_ENV_COM_VD_MERGE=False para forçar .env.'
                )
            if 'tipo_conexao_mapa' not in merged_plano and 'tipo_conexao_mapa' in payload:
                payload.pop('tipo_conexao_mapa', None)
                lookup_logs.append(
                    '[RADUSUARIOS] omitido tipo_conexao_mapa (idem; 58 do .env). '
                    'Se o IXC pedir «Preencha tipo/plano», preencha IXC_RADUSUARIOS_ID_GRUPO/TIPO_CONEXAO_MAPA com os IDs do plano no seu IXC.'
                )

        postar_vd = self._radusuarios_postar_id_vd_contrato_no_ixc(merged_plano)
        if postar_vd:
            lookup_logs.append(
                '[RADUSUARIOS] id_vd_contrato permanece no POST (veio do merge cliente_contrato; '
                'IXC valida plano junto ao contrato).'
            )
        if not postar_vd:
            removed = []
            for k in (
                'id_vd_contrato',
                'id_vd_contrato_desejado',
                'id_plano',
                'id_plano_venda',
                'id_plano_velocidade',
            ):
                if k in payload:
                    del payload[k]
                    removed.append(k)
            if removed:
                lookup_logs.append(
                    f'[RADUSUARIOS] omitidos_do_post_ixc (sem id_vd no POST; JSON mínimo provedor): {removed}'
                )

        uf = (cadastro.uf or '').strip().upper()
        if uf and not (isinstance(payload.get('uf'), str) and payload['uf'].strip()):
            payload['uf'] = uf

        addr_keys = sorted(
            k
            for k in payload
            if any(
                t in k.lower()
                for t in ('endereco', 'cidade', 'cep', 'bairro', 'numero', 'complemento', 'referencia', 'latitude', 'longitude')
            )
        )
        plano_keys = sorted(
            k
            for k in payload
            if any(
                t in k.lower()
                for t in (
                    'plano',
                    'vd_contrato',
                    'grupo',
                    'conexao_mapa',
                    'concentrador',
                    'porta_serv',
                    'tipo_conexao',
                    'servico',
                    'produto',
                )
            )
        )
        lookup_logs.append(f'[RADUSUARIOS] chaves_endereco_no_payload={addr_keys}')
        lookup_logs.append(f'[RADUSUARIOS] chaves_plano_conexao_no_payload={plano_keys}')
        return payload, None, lookup_logs

    def create_radusuarios_pppoe_test(self, cadastro):
        """POST ``webservice/v1/radusuarios`` com ``ixcsoft: incluir`` (teste PPPoE)."""
        if not self.url or not self.token:
            return {
                'status': 'error',
                'message': 'API do IXC não configurada (IXC_API_URL / IXC_API_TOKEN).',
                'logs': ['[RADUSUARIOS] IXC ausente.'],
            }
        prev_contrato = (getattr(cadastro, 'ixc_contrato_id', None) or '').strip()
        payload, err, lookup_logs = self.build_radusuarios_pppoe_payload(cadastro)
        logs = list(lookup_logs)
        if err:
            return {'status': 'error', 'message': err, 'logs': logs + [f'[RADUSUARIOS] {err}']}

        if not prev_contrato and any('obtido via listar' in line for line in lookup_logs):
            cid = str(payload.get('id_contrato', '')).strip()
            if cid:
                from .models import Cadastro

                Cadastro.objects.filter(pk=cadastro.pk).update(ixc_contrato_id=cid)
                logs.append('[RADUSUARIOS] ixc_contrato_id gravado no cadastro (listagem IXC).')

        resource = (settings.IXC_RADUSUARIOS_RESOURCE or 'radusuarios').strip()
        endpoint = f'{self.url}/webservice/v1/{resource}'
        debug_path = self._save_debug_json(cadastro.pk, payload, 'RADUSUARIOS_TEST')
        if debug_path:
            logs.append(f'[RADUSUARIOS] debug_json={debug_path}')
        logs.append(f'[RADUSUARIOS] login={payload.get("login")!r}')

        result = self._post_ixc(
            endpoint,
            payload,
            'RADUSUARIOS',
            extra_headers={'ixcsoft': 'incluir'},
        )
        logs.extend(result.get('logs', []))

        if result.get('status') != 'success':
            return {
                'status': 'error',
                'message': result.get('message') or 'Falha HTTP ao criar login PPPoE.',
                'logs': logs,
            }

        body = result.get('data') if isinstance(result.get('data'), dict) else {}
        response_type = str(body.get('type', '')).lower()
        response_message = str(body.get('message', ''))
        if response_type == 'error':
            return {
                'status': 'error',
                'message': response_message or 'IXC retornou erro ao incluir radusuarios.',
                'logs': logs + [f'[RADUSUARIOS] erro_api: {response_message}'],
            }

        rad_id = self._extract_id(body)
        msg_ok = f'Login PPPoE criado: {payload.get("login")}.'
        if rad_id not in (None, '', 0, '0'):
            msg_ok = f'Login PPPoE criado: {payload.get("login")} (ID: {rad_id}).'
        return {
            'status': 'success',
            'message': msg_ok,
            'radusuario_id': rad_id,
            'pppoe_login': payload.get('login'),
            'logs': logs,
        }

    def build_cliente_contrato_test_payload(self, cadastro):
        """Monta JSON para POST ``cliente_contrato`` (teste). Retorna (payload, erro_msg)."""
        try:
            payload = self._load_cliente_contrato_template()
        except (OSError, json.JSONDecodeError) as e:
            return None, f'Arquivo template data/ixc_cliente_contrato_incluir_template.json: {e}'

        id_cliente = self._ixc_id_cliente_for_cadastro(cadastro)
        if not id_cliente:
            return None, (
                'id_cliente ausente: defina IXC_CONTRATO_TEST_ID_CLIENTE no .env ou conclua «Enviar para IXC» '
                'para gravar ixc_prospect_id (crm_canditados), de preferência; senão ixc_lead_id (contato).'
            )

        id_plano, _, _ = self._resolve_plano_e_canal_venda(cadastro)
        id_vd = (settings.IXC_CONTRATO_TEST_ID_VD_CONTRATO or '').strip()
        if not id_vd:
            v = self._ixc_fk_value(id_plano)
            id_vd = str(v).strip() if v is not None else ''
        if not id_vd and self._is_demo_ixc_host():
            id_vd = '19'
        if not id_vd:
            return None, (
                'id_vd_contrato vazio: IXC_CONTRATO_TEST_ID_VD_CONTRATO no .env ou plano com ixc_plano_venda_id '
                '(Operação). No demo IXC o padrão de teste é 19.'
            )

        id_filial = (settings.IXC_CONTRATO_TEST_ID_FILIAL or '').strip()
        if not id_filial:
            if self._is_demo_ixc_host():
                id_filial = '1'
            else:
                id_filial = (self.resolve_filial_id(cadastro.cidade) or '').strip() or '1'

        payload['tipo'] = (settings.IXC_CONTRATO_TEST_TIPO or 'I').strip() or 'I'
        payload['id_cliente'] = str(id_cliente)
        # Plano de venda (IXC): continua vindo do cadastro / Operação ou IXC_CONTRATO_TEST_ID_VD_CONTRATO.
        payload['id_vd_contrato'] = str(id_vd)
        payload['id_filial'] = str(id_filial)
        payload['contrato'] = str(cadastro.plano_velocidade or cadastro.plano or 'Contrato teste')[:200]
        payload['data'] = timezone.now().strftime('%d/%m/%Y')
        payload['id_tipo_contrato'] = (settings.IXC_CONTRATO_TEST_ID_TIPO_CONTRATO or '10').strip()
        # Plano 19, modelo 4, tipo doc 501, tipo cobrança ID 10, vendedor 9, filial 1 — demo IXC (telas de referência).
        payload['id_modelo'] = (settings.IXC_CONTRATO_TEST_ID_MODELO or '4').strip()
        payload['id_tipo_documento'] = (settings.IXC_CONTRATO_TEST_ID_TIPO_DOCUMENTO or '501').strip()
        payload['id_carteira_cobranca'] = (settings.IXC_CONTRATO_TEST_ID_CARTEIRA_COBRANCA or '1').strip()
        payload['id_vendedor'] = (settings.IXC_CONTRATO_TEST_ID_VENDEDOR or '9').strip()
        payload['cc_previsao'] = (settings.IXC_CONTRATO_TEST_CC_PREVISAO or 'M').strip()
        payload['tipo_cobranca'] = (settings.IXC_CONTRATO_TEST_TIPO_COBRANCA_ID or '10').strip()
        # Fidelidade em meses: 12 se o cliente marcou fidelidade na ficha, senão 0.
        payload['fidelidade'] = '12' if getattr(cadastro, 'fidelidade', True) else '0'
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
        logs.append(
            f'[CLIENTE_CONTRATO] aguardando_assinatura ok (recurso={resource}, {key}={cid}).'
        )
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
        logs = []
        if debug_path:
            logs.append(f'[CLIENTE_CONTRATO] debug_json={debug_path}')

        result = self._post_ixc(
            endpoint,
            payload,
            'CLIENTE_CONTRATO',
            extra_headers={'ixcsoft': 'incluir'},
        )
        logs.extend(result.get('logs', []))

        if result.get('status') != 'success':
            return {
                'status': 'error',
                'message': result.get('message') or 'Falha HTTP ao criar contrato.',
                'logs': logs,
            }

        body = result.get('data') if isinstance(result.get('data'), dict) else {}
        response_type = str(body.get('type', '')).lower()
        response_message = str(body.get('message', ''))
        if response_type == 'error':
            return {
                'status': 'error',
                'message': response_message or 'IXC retornou erro ao incluir contrato.',
                'logs': logs + [f'[CLIENTE_CONTRATO] erro_api: {response_message}'],
            }

        contrato_id = self._extract_cliente_contrato_id(body)
        if contrato_id in (None, '', 0, '0'):
            logs.append(
                f'[CLIENTE_CONTRATO] id_contrato_nao_extraido; chaves_resposta={list(body.keys())[:25]}'
            )
        id_sent = str(payload.get('id_cliente', '')).strip()
        lead_only = (
            id_sent
            and id_sent == str(cadastro.ixc_lead_id or '').strip()
            and not str(cadastro.ixc_prospect_id or '').strip()
        )

        if contrato_id not in (None, '', 0, '0'):
            msg_ok = f'Contrato criado no IXC (teste). ID: {contrato_id}.'
            from .models import Cadastro

            cid = str(contrato_id).strip()
            Cadastro.objects.filter(pk=cadastro.pk).update(ixc_contrato_id=cid)
            logs.append(f'[CLIENTE_CONTRATO] ixc_contrato_id={cid} gravado no cadastro pk={cadastro.pk}.')
            ok_sig, sig_err = self._post_cliente_contrato_aguardando_assinatura(cid, logs)
            if ok_sig is True:
                msg_ok = f'{msg_ok} Aguardando assinatura (WS auxiliar aplicado).'
            elif ok_sig is False and sig_err:
                msg_ok = f'{msg_ok} Aviso: não foi possível aplicar «aguardando assinatura» no WS auxiliar: {str(sig_err)[:160]}'

            out = {
                'status': 'success',
                'message': msg_ok,
                'contrato_id': contrato_id,
                'logs': logs,
            }
            if getattr(settings, 'IXC_CLIENTE_CONTRATO_CRIAR_RADUSUARIOS_APOS_INCLUIR', True):
                cadastro.ixc_contrato_id = cid
                logs.append('[CLIENTE_CONTRATO] tentando radusuarios (PPPoE) após sucesso do contrato.')
                rad_out = self.create_radusuarios_pppoe_test(cadastro)
                logs.extend(rad_out.get('logs', []))
                out['radusuarios'] = {
                    'status': rad_out.get('status', 'error'),
                    'message': rad_out.get('message', ''),
                    'radusuario_id': rad_out.get('radusuario_id'),
                    'pppoe_login': rad_out.get('pppoe_login'),
                }
                if rad_out.get('status') == 'success':
                    tail = str(rad_out.get('message') or '').strip()
                    if tail:
                        out['message'] = f'{out["message"]} {tail}'.strip()[:900]
                else:
                    rmsg = str(rad_out.get('message') or 'falha').strip()[:220]
                    out['message'] = (
                        f'{out["message"]} Aviso: login PPPoE (radusuarios) não foi criado: {rmsg}'
                    ).strip()[:900]
            return out

        if lead_only:
            return {
                'status': 'warning',
                'message': (
                    'IXC respondeu 200 sem ID de contrato. O id_cliente veio só do contato (ixc_lead_id). '
                    'Conclua a prospecção (crm_canditados) para gravar ixc_prospect_id e teste de novo com esse ID.'
                ),
                'contrato_id': None,
                'logs': logs + ['[CLIENTE_CONTRATO] id_cliente=contato; prefira ixc_prospect_id após crm_canditados.'],
            }

        msg_ok = 'Contrato enviado ao IXC (teste).'
        if not body:
            msg_ok = 'IXC aceitou o POST sem corpo JSON; confira o contrato no IXC.'
        return {
            'status': 'success',
            'message': msg_ok,
            'contrato_id': contrato_id,
            'logs': logs,
        }

    def create_os(self, cadastro, ixc_id):
        pass
