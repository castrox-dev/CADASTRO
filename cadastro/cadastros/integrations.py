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

    def __init__(self):
        self.url = self._normalize_base_url(getattr(settings, 'IXC_API_URL', ''))
        self.token = getattr(settings, 'IXC_API_TOKEN', '')
        self.lead_resource_override = (getattr(settings, 'IXC_LEAD_RESOURCE', '') or '').strip()
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

        id_plano = self.PLANOS_MAP.get(cadastro.plano, '')
        id_origem = self.ORIGENS_MAP.get(cadastro.origem, '1')
        id_filial = self.FILIAIS_MAP.get(cadastro.cidade, '2')
        id_cidade = self.CIDADES_MAP.get(cadastro.cidade, '')

        # Obtém dados sanitizados para o IXC
        ixc_data = cadastro.get_ixc_data()
        
        # Payload com mapeamento reforçado de contatos e data brasileira
        payload = {
            'id_filial': id_filial,
            'contato': ixc_data['nome_razao'].upper(),
            'nome': ixc_data['nome_razao'].upper(),
            'razao': ixc_data['nome_razao'].upper(),
            'data_cadastro': cadastro.data_cadastro.strftime('%d/%m/%Y %H:%M:%S') if cadastro.data_cadastro else timezone.now().strftime('%d/%m/%Y %H:%M:%S'),
            'cnpj_cpf': cadastro.documento,
            
            # Telefones - Mapeamento idêntico para todos os campos de contato
            'fone_residencial': cadastro.telefone,
            'fone_comercial': cadastro.telefone,
            'fone_movel': cadastro.telefone,
            'telefone_celular': cadastro.telefone,
            'celular': cadastro.telefone,
            'whatsapp': cadastro.telefone,
            'fone_whatsapp': cadastro.telefone,
            'celular_whatsapp': cadastro.telefone,
            
            'email': cadastro.email.lower(),
            
            # Data de Nascimento - Formato Brasileiro DD/MM/YYYY
            'data_nascimento': cadastro.data_nascimento.strftime('%d/%m/%Y') if cadastro.data_nascimento else '',
            'nascimento': cadastro.data_nascimento.strftime('%d/%m/%Y') if cadastro.data_nascimento else '',
            
            'descricao': f"Interesse no plano: {cadastro.plano_velocidade}. Origem: {cadastro.origem}".upper() if cadastro.plano_velocidade and cadastro.origem else '',
            'id_origem': id_origem,
            'id_prospeccao': id_plano,
            'id_plano_venda': id_plano,
            
            # Endereço completo - Sanitizado para evitar erros no IXC
            'cep': cadastro.cep.upper(),
            'endereco': ixc_data['endereco'].upper(),
            'numero': ixc_data['numero'].upper(),
            'bairro': ixc_data['bairro'].upper(),
            'complemento': ixc_data['complemento'].upper(),
            'cidade': id_cidade or cadastro.cidade.upper(),
            'uf': cadastro.uf.upper(),
            'referencia': ixc_data['referencia'].upper(),
        }

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

        id_filial = self.FILIAIS_MAP.get(cadastro.cidade, '2')
        id_canal = self.ORIGENS_MAP.get(cadastro.origem, '1')
        id_cidade = self.CIDADES_MAP.get(cadastro.cidade, '')
        
        # Obtém dados sanitizados para o IXC
        ixc_data = cadastro.get_ixc_data()

        payload = {
            'id_filial': id_filial,
            'razao': ixc_data['nome_razao'],
            'fantasia': ixc_data['nome_razao'],
            'cnpj_cpf': cadastro.documento,
            'ie_rg': cadastro.rg or cadastro.inscricao_estadual,
            'endereco': ixc_data['endereco'],
            'numero': ixc_data['numero'],
            'bairro': ixc_data['bairro'],
            'cidade': id_cidade or cadastro.cidade,
            'cep': cadastro.cep,
            'telefone': cadastro.telefone,
            'email': cadastro.email,
            'tipo_pessoa': 'F' if cadastro.tipo_pessoa == 'pf' else 'J',
            'tipo_cliente': 'P',
            'id_vendedor': '1', 
            'id_canal_venda': id_canal,
            'ativo': 'S',
            'origem': 'Sistema de Cadastro Externo',
            'id_lead': crm_lead_id
        }

        self._save_debug_json(cadastro.pk, payload, 'PROSPECT')

        try:
            endpoint = f"{self.url}/webservice/v1/cliente"
            return self._post_ixc(endpoint, payload, 'PROSPECT')
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def create_os(self, cadastro, ixc_id):
        pass