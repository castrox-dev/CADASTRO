import requests
from django.conf import settings

class IXCIntegration:
    """
    Classe para gerenciar a integração com o ERP IXCSoft.
    """
    def __init__(self):
        self.url = getattr(settings, 'IXC_API_URL', '')
        self.token = getattr(settings, 'IXC_API_TOKEN', '')
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }

    def create_lead(self, cadastro):
        """
        Cria um lead/prospect no IXC a partir de um cadastro do Django.
        """
        if not self.url or not self.token:
            return {'status': 'error', 'message': 'API do IXC não configurada.'}

        # Exemplo de payload simplificado (ajustar de acordo com a doc oficial do IXC)
        payload = {
            'razao': cadastro.nome_razao,
            'cnpj_cpf': cadastro.documento,
            'endereco': cadastro.endereco,
            'bairro': cadastro.bairro,
            'cidade': cadastro.cidade,
            'cep': cadastro.cep,
            'telefone_celular': cadastro.telefone,
            'email': cadastro.email,
            'origem': 'Sistema de Cadastro Externo',
            # Outros campos necessários no seu IXC
        }

        try:
            # No IXC, leads costumam ser criados no endpoint 'prospect' ou 'cliente' com status específico
            endpoint = f"{self.url}/webservice/v1/cliente"
            response = requests.post(endpoint, json=payload, headers=self.headers, verify=False)
            
            if response.status_code in [200, 201]:
                return {'status': 'success', 'data': response.json()}
            else:
                return {'status': 'error', 'message': f"Erro no IXC: {response.text}"}
        except Exception as e:
            return {'status': 'error', 'message': f"Falha na conexão: {str(e)}"}

    def create_os(self, cadastro, ixc_id):
        """
        Cria uma Ordem de Serviço no IXC para o cliente recém-criado.
        """
        # Exemplo de lógica para abrir OS de instalação
        pass
