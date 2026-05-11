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
    CRM_LEAD_RESOURCES = ['crm_leads', 'crm_sp_leads', 'crm_lead', 'contato']
    # Prospecção: padrão só `crm_prospect` (exemplos públicos IXC/SDK). Nomes extras = Postman do provedor
    # em IXC_CRM_PROSPECT_FALLBACK_RESOURCES (vírgula), não lista “chutada” no código.

    def _crm_lead_resources_to_try(self):
        """Ordem de recursos para criar lead. No demo público só `contato` responde — 1 POST por vez, sem fila em crm_* inexistentes."""
        if self.lead_resource_override:
            return [self.lead_resource_override]
        if self._is_demo_ixc_host():
            return ['contato']
        return list(self.CRM_LEAD_RESOURCES)

    def _crm_prospect_resources_to_try(self):
        """Recursos WS para incluir prospecção. Ordem: IXC_CRM_PROSPECT_RESOURCE (um só) senão
        `crm_prospect` + opcionais em IXC_CRM_PROSPECT_FALLBACK_RESOURCES (conforme doc Postman do provedor).
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

    def __init__(self):
        self.url = self._normalize_base_url(getattr(settings, 'IXC_API_URL', ''))
        self.token = getattr(settings, 'IXC_API_TOKEN', '')
        self.lead_resource_override = (getattr(settings, 'IXC_LEAD_RESOURCE', '') or '').strip()
        self.force_plano_venda_id = getattr(settings, 'IXC_FORCE_PLANO_VENDA_ID', '') or ''
        self.force_canal_venda_id = getattr(settings, 'IXC_FORCE_CANAL_VENDA_ID', '') or ''
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

    def _merge_crm_venda_fks(self, payload, id_plano, id_origem, id_canal):
        """Plano, origem (CRM) e canal de venda são FKs distintas no IXC — não repetir o mesmo ID nos três."""
        io = self._ixc_fk_value(id_origem)
        ic = self._ixc_fk_value(id_canal)
        ip = self._ixc_fk_value(id_plano)
        if io is not None:
            payload['id_origem'] = io
        if ic is not None:
            payload['id_canal_venda'] = ic
            # Tela CRM: label «Canal de venda» costuma ser input#id_candidato_tipo (IXC amarra outro nome no WS).
            payload['id_candidato_tipo'] = ic
        if ip is not None:
            payload['id_plano_venda'] = ip
            # Vários IXC amarram o combo «Plano de venda» do lead a prospecção / plano.
            payload['id_prospeccao'] = ip
            # Tela CRM: «Plano de venda» costuma ser input#id_vd_contrato — webservice espelha este nome.
            payload['id_vd_contrato'] = ip

        # «Campanha» na tela = input#id_campanha (cadastro distinto de canal em muitas bases).
        camp_force = (getattr(settings, 'IXC_FORCE_CAMPANHA_ID', '') or '').strip()
        camp_default = (getattr(settings, 'IXC_DEFAULT_CAMPANHA_ID', '') or '').strip()
        id_camp_raw = camp_force or camp_default
        id_camp = self._ixc_fk_value(id_camp_raw) if id_camp_raw else None
        if id_camp is not None:
            payload['id_campanha'] = id_camp
        elif getattr(settings, 'IXC_SEND_CANAL_AS_ID_CAMPANHA', False) and ic is not None:
            payload['id_campanha'] = ic
        return payload

    @classmethod
    def _origens_map_lookup(cls, label):
        """Match case-insensitive no mapa legado de origens."""
        if not label:
            return None
        raw = str(label).strip()
        for k, v in cls.ORIGENS_MAP.items():
            if k.lower() == raw.lower():
                return v
        return None

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

    def _resolve_plano_e_canal_venda(self, cadastro):
        """Resolve plano de venda, origem CRM e canal de venda (campos diferentes no IXC)."""
        id_plano = self.resolve_plano_venda_id(cadastro.cidade, cadastro.plano)
        id_origem = self.resolve_origem_ixc_id(cadastro.origem)

        if self.force_plano_venda_id:
            id_plano = self.force_plano_venda_id
        elif self._is_demo_ixc_host():
            id_plano = '1'

        id_plano = (id_plano or '').strip()
        if not id_plano:
            id_plano = (getattr(settings, 'IXC_DEFAULT_PLANO_VENDA_ID', '') or '').strip()

        id_origem = (id_origem or '').strip()
        if not id_origem:
            id_origem = '1'

        # Canal de venda: tabela própria no IXC — use FORCE/DEFAULT; senão demo 1; senão cai na mesma origem (legado).
        id_canal = (self.force_canal_venda_id or '').strip()
        if not id_canal:
            id_canal = (getattr(settings, 'IXC_DEFAULT_CANAL_VENDA_ID', '') or '').strip()
        if not id_canal and self._is_demo_ixc_host():
            id_canal = '1'
        if not id_canal:
            id_canal = id_origem

        return id_plano, id_origem, id_canal

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

    def resolve_plano_venda_id(self, cidade_slug, plano_codigo):
        slug = (cidade_slug or '').strip()
        codigo = (plano_codigo or '').strip()
        try:
            from .operacao_models import CidadeOperacao, PlanoDefinicao

            c = CidadeOperacao.objects.select_related('grupo_planos').filter(slug__iexact=slug).first()
            if not c:
                return self.PLANOS_MAP.get(codigo, '') or self.PLANOS_MAP.get(codigo.lower(), '')
            p = PlanoDefinicao.objects.filter(grupo=c.grupo_planos, codigo__iexact=codigo).first()
            if p and (p.ixc_plano_venda_id or '').strip():
                return p.ixc_plano_venda_id.strip()
        except Exception:
            pass
        return self.PLANOS_MAP.get(codigo, '') or self.PLANOS_MAP.get(codigo.lower(), '')

    def resolve_origem_ixc_id(self, origem_label, default='1'):
        """Resolve o ID IXC para a origem informada.

        Usa OrigemCanalVenda(label=origem_label) primeiro; cai no ORIGENS_MAP
        legado se não houver registro; e retorna `default` em último caso.
        """
        if not origem_label:
            return default
        label = str(origem_label).strip()
        try:
            from .operacao_models import OrigemCanalVenda

            row = OrigemCanalVenda.objects.filter(label__iexact=label, ativo=True).first()
            if row and (row.ixc_id or '').strip():
                return row.ixc_id.strip()
        except Exception:
            pass
        return self._origens_map_lookup(label) or default

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
        id_plano, id_origem, id_canal = self._resolve_plano_e_canal_venda(cadastro)
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
            'descricao': f"Interesse no plano: {cadastro.plano_velocidade}. Origem: {cadastro.origem}".upper() if cadastro.plano_velocidade and cadastro.origem else '',
            'cep': cep_display,
            'endereco': ixc_data['endereco'].upper(),
            'numero': ixc_data['numero'].upper(),
            'bairro': ixc_data['bairro'].upper(),
            'complemento': ixc_data['complemento'].upper(),
            'cidade': id_cidade or cadastro.cidade.upper(),
            'uf': (cadastro.uf or '').upper(),
            'referencia': ixc_data['referencia'].upper(),
        }
        self._merge_crm_venda_fks(payload, id_plano, id_origem, id_canal)
        return payload

    def build_crm_prospect_payload(self, cadastro, *, link_contato_id=None, ixc_lead_resource=None):
        """Monta JSON para prospecção CRM a partir da mesma ficha do lead.

        `link_contato_id`: ID retornado na etapa 1 no IXC (mesmo valor de `ixc_lead_id` local).
        `ixc_lead_resource`: recurso usado na etapa 1 (`contato`, `crm_leads`, …) — define vínculo
        (`id_contato` vs `id_lead`).
        """
        id_plano, id_origem, id_canal = self._resolve_plano_e_canal_venda(cadastro)
        id_filial = self.resolve_filial_id(cadastro.cidade)
        id_cidade = self.resolve_cidade_ixc_id(cadastro.cidade)
        ixc_data = cadastro.get_ixc_data()
        doc_display, cep_display, tel_display = self._ixc_display_pii(cadastro)
        tipo_ixc = 'J' if getattr(cadastro, 'tipo_pessoa', 'pf') == 'pj' else 'F'
        idf = self._ixc_fk_value(id_filial) if str(id_filial).strip().isdigit() else id_filial

        payload = {
            'razao': ixc_data['nome_razao'].upper(),
            'nome': ixc_data['nome_razao'].upper(),
            'contato': ixc_data['nome_razao'].upper(),
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
            'descricao': (
                f"Ficha web cadastro_id={cadastro.pk} | Plano: {cadastro.plano_velocidade} | "
                f"Origem: {cadastro.origem}"
            ).upper(),
        }
        if cadastro.data_nascimento:
            payload['data_nascimento'] = cadastro.data_nascimento.strftime('%d/%m/%Y')
            payload['nascimento'] = cadastro.data_nascimento.strftime('%d/%m/%Y')
        self._merge_crm_venda_fks(payload, id_plano, id_origem, id_canal)

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
            id_plano_chk, id_origem_chk, id_canal_chk = self._resolve_plano_e_canal_venda(cadastro)
            all_logs.append(
                '[CRM_LEAD] resolvido '
                f"plano={id_plano_chk or '(vazio)'} origem={id_origem_chk or '(vazio)'} "
                f"canal_venda={id_canal_chk or '(vazio)'} cidade_slug={cadastro.cidade!r} "
                f"plano_codigo={cadastro.plano!r} origem_label={cadastro.origem!r} demo={self._is_demo_ixc_host()}"
            )
            if self._ixc_fk_value(id_plano_chk) is None:
                all_logs.append(
                    '[CRM_LEAD] aviso: id_plano_venda vazio — configure ixc_plano_venda_id no plano '
                    '(Operação) ou IXC_FORCE_PLANO_VENDA_ID / IXC_DEFAULT_PLANO_VENDA_ID no .env'
                )
            if self._ixc_fk_value(id_canal_chk) is None:
                all_logs.append(
                    '[CRM_LEAD] aviso: id_canal_venda vazio — use IXC_FORCE_CANAL_VENDA_ID / '
                    'IXC_DEFAULT_CANAL_VENDA_ID (ID da tela CRM > Canal de vendas), não só Origens.'
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