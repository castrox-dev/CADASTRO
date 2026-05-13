import requests
import base64
import json
import os
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
        ep_low = (endpoint or '').lower()
        if 'radusuario' in ep_low:
            return {
                'status': 'error',
                'message': 'Chamadas a radusuarios (PPPoE) estão desativadas neste portal.',
                'logs': [f'[{etapa}] BLOQUEADO (política): {endpoint}'],
                'endpoint': endpoint,
            }
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

    def create_os(self, cadastro, ixc_id):
        pass
