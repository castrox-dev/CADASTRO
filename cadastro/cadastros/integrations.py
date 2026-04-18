import requests
from django.conf import settings

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

    def __init__(self):
        self.url = getattr(settings, 'IXC_API_URL', '')
        self.token = getattr(settings, 'IXC_API_TOKEN', '')
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }

    def create_crm_lead(self, cadastro):
        """
        Passo 1: Cria um Lead no CRM do IXC.
        """
        if not self.url or not self.token:
            return {'status': 'error', 'message': 'API do IXC não configurada.'}

        id_plano = self.PLANOS_MAP.get(cadastro.plano, '')
        id_origem = self.ORIGENS_MAP.get(cadastro.origem, '1') # Default 'Solicitado pelo cliente'
        id_filial = self.FILIAIS_MAP.get(cadastro.cidade, '2') # Default Maricá

        # Payload para CRM Lead
        payload = {
            'id_filial': id_filial,
            'contato': cadastro.nome_razao,
            'cnpj_cpf': cadastro.documento,
            'fone_residencial': cadastro.telefone,
            'fone_comercial': cadastro.telefone,
            'fone_movel': cadastro.telefone,
            'whatsapp': cadastro.telefone,
            'email': cadastro.email,
            'data_nascimento': cadastro.data_nascimento.strftime('%Y-%m-%d') if cadastro.data_nascimento else '',
            'descricao': f"Interesse no plano: {cadastro.plano_velocidade}. Origem: {cadastro.origem}",
            'id_origem': id_origem,
            'id_prospeccao': id_plano # Vincula o plano de interesse no CRM
        }

        try:
            endpoint = f"{self.url}/webservice/v1/crm_leads"
            response = requests.post(endpoint, json=payload, headers=self.headers, verify=False)
            
            if response.status_code in [200, 201]:
                return {'status': 'success', 'data': response.json()}
            else:
                return {'status': 'error', 'message': f"Erro ao criar CRM Lead: {response.text}"}
        except Exception as e:
            return {'status': 'error', 'message': f"Falha na conexão CRM: {str(e)}"}

    def create_prospect(self, cadastro, crm_lead_id=None):
        """
        Passo 2: Cria um Prospect (Cliente) no IXC.
        Pode opcionalmente vincular ao CRM Lead criado no Passo 1.
        """
        if not self.url or not self.token:
            return {'status': 'error', 'message': 'API do IXC não configurada.'}

        id_filial = self.FILIAIS_MAP.get(cadastro.cidade, '2') # Default Maricá
        id_canal = self.ORIGENS_MAP.get(cadastro.origem, '1')
        id_cidade = self.CIDADES_MAP.get(cadastro.cidade, '')

        # Payload para Prospect (Cliente)
        payload = {
            'id_filial': id_filial,
            'razao': cadastro.nome_razao,
            'fantasia': cadastro.nome_fantasia or cadastro.nome_razao,
            'cnpj_cpf': cadastro.documento,
            'ie_rg': cadastro.rg or cadastro.inscricao_estadual,
            'endereco': cadastro.endereco,
            'numero': getattr(cadastro, 'numero', 'S/N'),
            'bairro': cadastro.bairro,
            'cidade': id_cidade or cadastro.cidade, # Envia o ID se mapeado, senão o texto
            'cep': cadastro.cep,
            'telefone': cadastro.telefone,
            'telefone_comercial': cadastro.telefone,
            'telefone_celular': cadastro.telefone,
            'whatsapp': cadastro.telefone,
            'email': cadastro.email,
            'tipo_pessoa': 'F' if cadastro.tipo_pessoa == 'pf' else 'J',
            'tipo_cliente': 'P', # 'P' para Prospect no IXC
            'id_vendedor': '1', 
            'id_canal_venda': id_canal,
            'ativo': 'S',
            'origem': 'Sistema de Cadastro Externo',
            'id_lead': crm_lead_id
        }

        try:
            endpoint = f"{self.url}/webservice/v1/cliente"
            response = requests.post(endpoint, json=payload, headers=self.headers, verify=False)
            
            if response.status_code in [200, 201]:
                return {'status': 'success', 'data': response.json()}
            else:
                return {'status': 'error', 'message': f"Erro ao criar Prospect: {response.text}"}
        except Exception as e:
            return {'status': 'error', 'message': f"Falha na conexão Prospect: {str(e)}"}

    def create_os(self, cadastro, ixc_id):
        """
        Cria uma Ordem de Serviço no IXC para o cliente recém-criado.
        """
        # Exemplo de lógica para abrir OS de instalação
        pass
