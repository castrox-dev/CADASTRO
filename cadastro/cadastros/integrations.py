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
        '1giga': '560',     # 1 GIGA
    }

    # Mapeamento de Canais de Venda (Origens) baseado nos prints do IXC
    ORIGENS_MAP = {
        'Instagram': '6',
        'Facebook': '9',
        'Google': '7',
        'Google Ads': '12',
        'Indicação': '4', # Indicação de outros clientes
        'Site': '10',
        'WhatsApp': '1', # Solicitado pelo cliente
        'TikTok': '13', # Tráfego mídias
    }
    CRM_LEAD_RESOURCES = ['crm_leads', 'crm_sp_leads', 'crm_lead', 'contato']
    CRM_PROSPECT_CONVERT_RESOURCES = ['crm_sp_leads', 'crm_leads', 'crm_lead']
    CRM_PROSPECT_NEW_RESOURCES = ['cliente']

    def __init__(self):
        self.url = self._normalize_base_url(getattr(settings, 'IXC_API_URL', ''))
        self.token = getattr(settings, 'IXC_API_TOKEN', '')
        self.lead_resource_override = (getattr(settings, 'IXC_LEAD_RESOURCE', '') or '').strip()
        self.prospect_strategy = (getattr(settings, 'IXC_PROSPECT_STRATEGY', 'auto') or 'auto').strip().lower()
        self.prospect_tipo_assinante = str(getattr(settings, 'IXC_PROSPECT_TIPO_ASSINANTE', '1') or '1').strip()
        self.prospect_classificacao_iss = self._normalize_iss_classificacao(
        )
        self.prospect_contribuinte_icms = str(getattr(settings, 'IXC_PROSPECT_CONTRIBUINTE_ICMS', 'N') or 'N').strip().upper()
        self.prospect_tipo_localidade = str(getattr(settings, 'IXC_PROSPECT_TIPO_LOCALIDADE', 'U') or 'U').strip().upper()
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

    @staticmethod
    def _build_authorization_header(token):
        clean_token = (token or '').strip()
        if not clean_token:
            return ''
        if clean_token.count('.') == 2 and ':' not in clean_token:
            return f'Bearer {clean_token}'
        encoded = base64.b64encode(clean_token.encode('utf-8')).decode('ascii')
        return f'Basic {encoded}'

    @staticmethod
    def _normalize_iss_classificacao(value):
        # IXC normalmente espera codigos 2 digitos: 00, 01, 02, 03 ou 99.
        raw = str(value or '').strip()
        if raw.isdigit() and len(raw) == 1:
            return f"0{raw}"
        return raw or '99'

    @classmethod
    def _parse_iss_fallbacks(cls, value):
        raw_items = [item.strip() for item in str(value or '').split(',') if item.strip()]
        normalized = [cls._normalize_iss_classificacao(item) for item in raw_items]
        return normalized or ['99', '00', '01']

    def _save_debug_json(self, cadastro_id, payload, etapa):
        try:
            debug_dir = os.path.join(settings.BASE_DIR, 'media', 'ixc_debug')
            if not os.path.exists(debug_dir):
                os.makedirs(debug_dir)
            
            filename = f"debug_id_{cadastro_id}_{etapa}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(debug_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=4, ensure_ascii=False)
            return filepath
        except Exception:
            return None

    def _post_ixc(self, endpoint, payload, etapa):
        logs = [
            f"[{etapa}] endpoint: {endpoint}",
            f"[{etapa}] auth: {'ok' if bool(self.token) else 'ausente'}",
        ]
        try:
            response = requests.post(endpoint, json=payload, headers=self.headers, verify=False, timeout=30)
            logs.append(f"[{etapa}] status_http: {response.status_code}")

            if response.status_code in [200, 201]:
                return {
                    'status': 'success',
                    'data': response.json(),
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
            for key in ('id', 'id_lead', 'id_cliente', 'idcrm_leads'):
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

    def build_crm_lead_payload(self, cadastro):
        id_plano = self.PLANOS_MAP.get(cadastro.plano, '')
        id_origem = self.ORIGENS_MAP.get(cadastro.origem, '1')
        id_filial = self.FILIAIS_MAP.get(cadastro.cidade, '2')
        id_cidade = self.CIDADES_MAP.get(cadastro.cidade, '')
        ixc_data = cadastro.get_ixc_data()

        return {
            'id_filial': id_filial,
            'contato': ixc_data['nome_razao'].upper(),
            'nome': ixc_data['nome_razao'].upper(),
            'razao': ixc_data['nome_razao'].upper(),
            'ativo': 'S',
            'principal': 'S',
            'tipo_contato': 'L',
            'tipo': 'L',
            'data_cadastro': cadastro.data_cadastro.strftime('%d/%m/%Y %H:%M:%S') if cadastro.data_cadastro else timezone.now().strftime('%d/%m/%Y %H:%M:%S'),
            'cnpj_cpf': cadastro.documento,
            'fone_residencial': cadastro.telefone,
            'fone_comercial': cadastro.telefone,
            'fone_movel': cadastro.telefone,
            'telefone_celular': cadastro.telefone,
            'fone_celular': cadastro.telefone,
            'whatsapp': cadastro.telefone,
            'fone_whatsapp': cadastro.telefone,
            'celular_whatsapp': cadastro.telefone,
            'email': cadastro.email.lower(),
            'data_nascimento': cadastro.data_nascimento.strftime('%d/%m/%Y') if cadastro.data_nascimento else '',
            'nascimento': cadastro.data_nascimento.strftime('%d/%m/%Y') if cadastro.data_nascimento else '',
            'descricao': f"Interesse no plano: {cadastro.plano_velocidade}. Origem: {cadastro.origem}".upper() if cadastro.plano_velocidade and cadastro.origem else '',
            'id_origem': id_origem,
            'id_prospeccao': id_plano,
            'id_plano_venda': id_plano,
            'cep': cadastro.cep.upper(),
            'endereco': ixc_data['endereco'].upper(),
            'numero': ixc_data['numero'].upper(),
            'bairro': ixc_data['bairro'].upper(),
            'complemento': ixc_data['complemento'].upper(),
            'cidade': id_cidade or cadastro.cidade.upper(),
            'uf': cadastro.uf.upper(),
            'referencia': ixc_data['referencia'].upper(),
        }

    def build_prospect_payloads(self, cadastro, crm_lead_id=None):
        id_filial = self.FILIAIS_MAP.get(cadastro.cidade, '2')
        id_canal = self.ORIGENS_MAP.get(cadastro.origem, '1')
        id_cidade = self.CIDADES_MAP.get(cadastro.cidade, '')
        ixc_data = cadastro.get_ixc_data()

        payload_cliente = {
            'id_filial': id_filial,
            'razao': ixc_data['nome_razao'],
            'fantasia': ixc_data['nome_razao'],
            'cnpj_cpf': cadastro.documento,
            'ie_rg': cadastro.rg or '',
            'endereco': ixc_data['endereco'],
            'numero': ixc_data['numero'],
            'bairro': ixc_data['bairro'],
            'cidade': id_cidade or cadastro.cidade,
            'cep': cadastro.cep,
            'telefone': cadastro.telefone,
            'email': (cadastro.email or '').lower(),
            'tipo_pessoa': 'F' if cadastro.tipo_pessoa == 'pf' else 'J',
            'tipo_cliente': 'P',
            'id_vendedor': '1',
            'id_canal_venda': id_canal,
            'ativo': 'S',
            'origem': 'Sistema de Cadastro Externo',
            'tipo_assinante': self.prospect_tipo_assinante,
            'classificacao_iss': self.prospect_classificacao_iss,
            'classificacao_issqn': self.prospect_classificacao_iss,
            'id_classificacao_iss': self.prospect_classificacao_iss_id or self.prospect_classificacao_iss,
            'id_classificacao_issqn': self.prospect_classificacao_iss_id or self.prospect_classificacao_iss,
            'id_classificacao_tributaria_iss': self.prospect_classificacao_iss_id or self.prospect_classificacao_iss,
            'contribuinte_icms': self.prospect_contribuinte_icms,
            'tipo_localidade': self.prospect_tipo_localidade,
        }
        if crm_lead_id:
            payload_cliente['id_lead'] = crm_lead_id

        payload_contato = {
            'id_filial': id_filial,
            'razao': ixc_data['nome_razao'],
            'nome': ixc_data['nome_razao'],
            'fantasia': ixc_data['nome_razao'],
            'status_prospeccao': 'N',
            'tipo_pessoa': 'F' if cadastro.tipo_pessoa == 'pf' else 'J',
            'cnpj_cpf': cadastro.documento,
            'ie_identidade': cadastro.rg or '',
            'filial_id': id_filial,
            'ativo': 'S',
            'data_cadastro': cadastro.data_cadastro.strftime('%d/%m/%Y %H:%M:%S') if cadastro.data_cadastro else timezone.now().strftime('%d/%m/%Y %H:%M:%S'),
            'id_vendedor': '1',
            'telefone_celular': cadastro.telefone,
            'email': (cadastro.email or '').lower(),
            'contato': ixc_data['nome_razao'],
            'cep': cadastro.cep,
            'endereco': ixc_data['endereco'],
            'numero': ixc_data['numero'],
            'bairro': ixc_data['bairro'],
            'cidade': id_cidade or cadastro.cidade,
            'complemento': ixc_data['complemento'],
            'referencia': ixc_data['referencia'],
            'uf': cadastro.uf or '',
            'tipo_localidade': self.prospect_tipo_localidade,
            'crm': 'S',
            'origem': 'Sistema de Cadastro Externo',
        }
        if crm_lead_id:
            payload_contato['id_lead'] = crm_lead_id

        return {
            'payload_cliente': payload_cliente,
            'payload_contato': payload_contato,
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
            if debug_path:
                all_logs.append(f"[DEBUG] JSON gerado em: {debug_path}")
            
            last_error = None
            resources_to_try = [self.lead_resource_override] if self.lead_resource_override else self.CRM_LEAD_RESOURCES
            
            for resource in resources_to_try:
                endpoint = f"{self.url}/webservice/v1/{resource}"
                result = self._post_ixc(endpoint, payload, 'CRM_LEAD')
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
                    all_logs.append(f"[CRM_LEAD] recurso indisponível, tentando fallback: {resource}")
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
                result['logs'] = all_logs
                return result

            return {
                'status': 'error',
                'message': "Nenhum recurso de lead disponível.",
                'logs': all_logs or (last_error.get('logs', []) if last_error else []),
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e), 'logs': [f"[CRM_LEAD] excecao: {str(e)}"]}

    def create_prospect(self, cadastro, crm_lead_id=None):
        if not self.url or not self.token:
            return {'status': 'error', 'message': 'API do IXC não configurada.'}

        prospect_payloads = self.build_prospect_payloads(cadastro, crm_lead_id=crm_lead_id)
        payload_cliente = prospect_payloads['payload_cliente']
        payload_contato = prospect_payloads['payload_contato']

        debug_path = self._save_debug_json(
            cadastro.pk,
            {'payload_contato': payload_contato, 'payload_cliente': payload_cliente},
            'PROSPECT_NEW'
        )

        try:
            all_logs = []
            if debug_path:
                all_logs.append(f"[DEBUG] JSON gerado em: {debug_path}")
            all_logs.append(
                "[PROSPECT_NEW] obrigatorios tipo_assinante="
                f"{self.prospect_tipo_assinante} classificacao_iss={self.prospect_classificacao_iss} "
                f"contribuinte_icms={self.prospect_contribuinte_icms} tipo_localidade={self.prospect_tipo_localidade}"
            )
            iss_candidates = [self.prospect_classificacao_iss_id] if self.prospect_classificacao_iss_id else [self.prospect_classificacao_iss] + [
                item for item in self.prospect_classificacao_iss_fallbacks
                if item != self.prospect_classificacao_iss
            ]
            all_logs.append(f"[PROSPECT_NEW] tentativas classificacao_iss={','.join(iss_candidates)}")

            last_error = None
            for iss_value in iss_candidates:
                payload_cliente['classificacao_iss'] = iss_value
                payload_cliente['classificacao_issqn'] = iss_value
                payload_cliente['id_classificacao_iss'] = iss_value
                payload_cliente['id_classificacao_issqn'] = iss_value
                payload_cliente['id_classificacao_tributaria_iss'] = iss_value
                all_logs.append(f"[PROSPECT_NEW] tentando classificacao_iss={iss_value}")

                for resource in self.CRM_PROSPECT_NEW_RESOURCES:
                    payload = payload_contato if resource == 'contato' else payload_cliente
                    endpoint = f"{self.url}/webservice/v1/{resource}"
                    result = self._post_ixc(endpoint, payload, 'PROSPECT_NEW')
                    all_logs.extend(result.get('logs', []))

                    if self._is_resource_unavailable(result):
                        all_logs.append(f"[PROSPECT_NEW] recurso indisponível, tentando fallback: {resource}")
                        last_error = result
                        continue

                    if result.get('status') != 'success':
                        result['logs'] = all_logs
                        return result

                    response_data = result.get('data')
                    response_type = ''
                    response_message = ''
                    if isinstance(response_data, dict):
                        response_type = str(response_data.get('type', '')).lower()
                        response_message = str(response_data.get('message', ''))
                    if response_type == 'error':
                        all_logs.append(f"[PROSPECT_NEW] erro_api: {response_message or 'erro sem mensagem'}")
                        # Se o erro for especificamente de Classificação de ISS, tenta próximo valor.
                        if 'classificação de iss' in (response_message or '').lower():
                            last_error = result
                            continue
                        result['status'] = 'error'
                        result['message'] = response_message or 'IXC retornou erro ao criar prospect.'
                        result['logs'] = all_logs
                        return result

                    prospect_id = self._extract_id(response_data)
                    result['prospect_id'] = prospect_id
                    if prospect_id in (None, '', 0, '0'):
                        all_logs.append("[PROSPECT_NEW] aviso: prospect criado sem ID explícito na resposta")
                    all_logs.append(f"[PROSPECT_NEW] recurso_ativo={resource}")
                    result['logs'] = all_logs
                    return result

            return {
                'status': 'error',
                'message': "Nenhum recurso de prospect (novo) disponível.",
                'logs': all_logs or (last_error.get('logs', []) if last_error else []),
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e), 'logs': [f"[PROSPECT_NEW] excecao: {str(e)}"]}

    def convert_lead_to_prospect(self, cadastro, crm_lead_id):
        if not self.url or not self.token:
            return {'status': 'error', 'message': 'API do IXC não configurada.'}
        if not crm_lead_id:
            return {'status': 'error', 'message': 'ID do lead ausente para conversão.'}

        # Alguns ambientes aceitam campos diferentes para converter lead em prospect.
        payload_variants = [
            {
                'id': str(crm_lead_id),
                'id_lead': str(crm_lead_id),
                'tipo_cliente': 'P',
                'converter_prospect': 'S',
            },
            {
                'id': str(crm_lead_id),
                'tipo_cliente': 'P',
                'converte_prospect': 'S',
            },
            {
                'id_lead': str(crm_lead_id),
                'tipo_cliente': 'P',
                'acao': 'converter_prospect',
            },
        ]

        all_logs = []
        last_error = None

        try:
            for idx, payload in enumerate(payload_variants, start=1):
                debug_path = self._save_debug_json(cadastro.pk, payload, f'PROSPECT_CONVERT_{idx}')
                if debug_path:
                    all_logs.append(f"[DEBUG] JSON gerado em: {debug_path}")

                for resource in self.CRM_PROSPECT_CONVERT_RESOURCES:
                    endpoint = f"{self.url}/webservice/v1/{resource}"
                    result = self._post_ixc(endpoint, payload, 'PROSPECT_CONVERT')
                    all_logs.extend(result.get('logs', []))

                    if self._is_resource_unavailable(result):
                        all_logs.append(f"[PROSPECT_CONVERT] recurso indisponível, tentando fallback: {resource}")
                        last_error = result
                        continue

                    if result.get('status') != 'success':
                        last_error = result
                        continue

                    response_data = result.get('data')
                    response_type = ''
                    if isinstance(response_data, dict):
                        response_type = str(response_data.get('type', '')).lower()
                        response_message = str(response_data.get('message', ''))
                        if response_type == 'error':
                            all_logs.append(f"[PROSPECT_CONVERT] erro_api: {response_message}")
                            last_error = {
                                'status': 'error',
                                'message': response_message or 'IXC retornou erro ao converter lead em prospect.',
                                'logs': all_logs,
                            }
                            continue

                    result['prospect_id'] = self._extract_id(response_data) or str(crm_lead_id)
                    all_logs.append(f"[PROSPECT_CONVERT] recurso_ativo={resource}")
                    result['logs'] = all_logs
                    return result

            return {
                'status': 'error',
                'message': (last_error or {}).get('message') or 'Não foi possível converter o lead em prospect.',
                'logs': all_logs or ((last_error or {}).get('logs', [])),
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e), 'logs': [f"[PROSPECT_CONVERT] excecao: {str(e)}"]}

    def create_os(self, cadastro, ixc_id):
        pass