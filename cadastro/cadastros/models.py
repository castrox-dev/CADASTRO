from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from localflavor.br.validators import BRCPFValidator, BRCNPJValidator
from simple_history.models import HistoricalRecords
import os
import unicodedata
from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile

def remove_special_chars(text):
    """
    Remove caracteres especiais e acentos de um texto.
    Converte para ASCII, removendo diacríticos.
    """
    if not text:
        return text
    nfd_form = unicodedata.normalize('NFD', str(text))
    clean_text = ''.join(char for char in nfd_form if unicodedata.category(char) != 'Mn')
    return clean_text

def get_file_path(instance, filename, field_name):
    ext = filename.split('.')[-1]
    # Limpa o documento para o nome do arquivo
    clean_doc = instance.documento.replace('.', '').replace('-', '').replace('/', '')
    filename = f"{clean_doc}_{field_name}.{ext}"
    return os.path.join('documentos_clientes', filename)

def path_contrato(instance, filename): return get_file_path(instance, filename, 'contrato_social')
def path_comprovante(instance, filename): return get_file_path(instance, filename, 'comprovante_residencia')
def path_doc_frente(instance, filename): return get_file_path(instance, filename, 'doc_frente')
def path_doc_verso(instance, filename): return get_file_path(instance, filename, 'doc_verso')
def path_selfie(instance, filename): return get_file_path(instance, filename, 'selfie')

class Cadastro(models.Model):
    TIPO_PESSOA_CHOICES = [
        ('pf', 'Pessoa Física'),
        ('pj', 'Pessoa Jurídica'),
    ]
    
    PERIODO_CHOICES = [
        ('manha', 'Manhã'),
        ('tarde', 'Tarde'),
    ]

    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('aguardando', 'Aguardando Confirmação'),
        ('realizado', 'Realizado'),
        ('cancelado', 'Cancelado'),
    ]

    # Identificação
    tipo_pessoa = models.CharField(max_length=2, choices=TIPO_PESSOA_CHOICES, default='pf')
    documento = models.CharField(max_length=20, db_index=True) # CPF ou CNPJ
    nome_razao = models.CharField(max_length=255) # Nome ou Razão Social
    nome_fantasia = models.CharField(max_length=255, blank=True, null=True)
    rg = models.CharField(max_length=20, blank=True, null=True)
    inscricao_estadual = models.CharField(max_length=50, blank=True, null=True)
    data_nascimento = models.DateField(blank=True, null=True)
    contrato_social = models.FileField(upload_to=path_contrato, blank=True, null=True)
    
    # Documentos Adicionais
    comprovante_residencia = models.FileField(upload_to=path_comprovante, blank=True, null=True)
    foto_documento_frente = models.FileField(upload_to=path_doc_frente, blank=True, null=True)
    foto_documento_verso = models.FileField(upload_to=path_doc_verso, blank=True, null=True)
    selfie_documento = models.FileField(upload_to=path_selfie, blank=True, null=True)
    levar_termo = models.BooleanField(default=False) # Opção para Unamar/Cabo Frio/SP
    
    # Contato
    email = models.EmailField()
    telefone = models.CharField(max_length=20)
    
    # Endereço
    cep = models.CharField(max_length=10)
    cidade = models.CharField(max_length=100)
    uf = models.CharField(max_length=2, blank=True, null=True)
    bairro = models.CharField(max_length=100)
    endereco = models.CharField(max_length=255)
    numero = models.CharField(max_length=20, blank=True, null=True)  # Número do endereço
    complemento = models.CharField(max_length=255, blank=True, null=True)  # Complemento (apto, bloco, etc)
    referencia = models.TextField()
    google_maps_link = models.URLField(max_length=500, blank=True, null=True)
    
    # Plano
    plano = models.CharField(max_length=100)
    fidelidade = models.BooleanField(default=True)
    vencimento = models.CharField(max_length=2)
    vencimento_id = models.CharField(max_length=10, blank=True, null=True)
    opcional = models.BooleanField(default=False)
    
    # Instalação
    pagamento_instalacao = models.CharField(max_length=50)
    data_instalacao = models.DateField()
    periodo_instalacao = models.CharField(max_length=10, choices=PERIODO_CHOICES)
    origem = models.CharField(max_length=100)
    
    # Controle
    consultor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    data_cadastro = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    ixc_lead_id = models.CharField(max_length=50, blank=True, null=True)
    ixc_lead_enviado_em = models.DateTimeField(blank=True, null=True)
    
    # Campo para edição manual da ficha
    ficha_manual = models.TextField(blank=True, null=True)

    history = HistoricalRecords()

    def clean(self):
        # Sanitização e Validação no clean
        self.documento = ''.join(filter(str.isdigit, self.documento))
        self.cep = ''.join(filter(str.isdigit, self.cep))
        self.telefone = ''.join(filter(str.isdigit, self.telefone))

        if self.tipo_pessoa == 'pf':
            BRCPFValidator()(self.documento)
        else:
            BRCNPJValidator()(self.documento)

        # Verificação de Duplicidade
        existing = Cadastro.objects.filter(documento=self.documento).exclude(pk=self.pk)
        if existing.exists():
            raise ValidationError(f"Já existe um cadastro com este CPF/CNPJ. Status: {existing.first().get_status_display()}")

    def save(self, *args, **kwargs):
        self.full_clean()
        
        # Compressão de Imagens
        for field in ['comprovante_residencia', 'foto_documento_frente', 'foto_documento_verso', 'selfie_documento']:
            file = getattr(self, field)
            if file and not file._committed: # Apenas se for um novo upload
                try:
                    img = Image.open(file)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    output = BytesIO()
                    img.save(output, format='JPEG', quality=70, optimize=True)
                    output.seek(0)
                    
                    # Substitui o arquivo original pelo comprimido
                    new_filename = f"{os.path.splitext(file.name)[0]}.jpg"
                    setattr(self, field, ContentFile(output.read(), name=new_filename))
                except Exception:
                    pass # Se não for imagem ou erro na compressão, segue original
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nome_razao} - {self.documento}"

    @property
    def plano_velocidade(self):
        planos_nomes = {
            'essencial': '240 MEGA',
            'rapido': '400 MEGA',
            'turbo': '500 MEGA',
            'ultra': '600 MEGA',
            '1giga': '1 GIGA',
            'plano_300': '300 MEGA',
            'plano_700': '700 MEGA'
        }
        return planos_nomes.get(self.plano, self.plano)

    @property
    def os_formatada(self):
        instalacao_valor = "100,00" if self.fidelidade else "460,00" if self.cidade == 'marica' else "A combinar"
        
        # Nomenclatura apenas com Megas para a OS
        planos_nomes = {
            'essencial': '240 MEGA',
            'rapido': '400 MEGA',
            'turbo': '500 MEGA',
            'ultra': '600 MEGA',
            '1giga': '1 GIGA',
            'plano_300': '300 MEGA',
            'plano_700': '700 MEGA'
        }
        plano_label = planos_nomes.get(self.plano, self.plano)
        
        precos = {
            'essencial': '59,99',
            'rapido': '79,99',
            'turbo': '99,99',
            'ultra': '119,99',
            '1giga': '149,99',
            'plano_300': '69,99',
            'plano_700': '89,99'
        }
        plano_valor = precos.get(self.plano, "0,00")
        
        # Lógica do Roteador (especialmente para 240 MEGA)
        if self.plano == 'essencial':
            router_info = "COM ROTEADOR EM ALUGUEL" if self.opcional else "COM ROTEADOR DO CLIENTE"
        elif self.plano == '1giga' and self.opcional:
            router_info = "COM ROTEADOR EM COMODATO + MESH"
        else:
            router_info = "COM ROTEADOR EM COMODATO"
            
        os_text = f"INSTALAÇÃO SERÁ PAGA NO VALOR DE R$ {instalacao_valor}\n\n"
        os_text += f"PLANO DE {plano_label} / R$ {plano_valor} {router_info}\n\n"
        os_text += f"DATA DE VENCIMENTO: {self.vencimento}\n\n"
        os_text += f"CONSULTORA(O): {self.consultor.get_full_name() if self.consultor else 'N/A'}\n\n"
        os_text += f"CONTATO FEITO COM A CLIENTE A MESMA AGUARDA INSTALAÇÃO PARA O DIA {self.data_instalacao.strftime('%d/%m/%Y')} {self.get_periodo_instalacao_display()}\n\n"
        if self.google_maps_link:
            os_text += f"LOCALIZAÇÃO: {self.google_maps_link}\n\n"
        os_text += "CLIENTE CIENTE QUE PRECISA REALIZAR A ASSINATURA DO CONTRATO NA CENTRAL DO ASSINANTE"
        
        return os_text

    def get_ixc_data(self):
        """
        Retorna um dicionario com os dados sanitizados para envio ao IXC.
        Remove caracteres especiais e acentos.
        """
        return {
            'endereco': remove_special_chars(self.endereco) if self.endereco else '',
            'numero': remove_special_chars(self.numero) if self.numero else 'S/N',
            'complemento': remove_special_chars(self.complemento) if self.complemento else '',
            'bairro': remove_special_chars(self.bairro) if self.bairro else '',
            'cidade': self.cidade,
            'nome_razao': remove_special_chars(self.nome_razao) if self.nome_razao else '',
            'referencia': remove_special_chars(self.referencia) if self.referencia else '',
        }

    @property
    def ficha_formatada(self):
        if self.ficha_manual:
            return self.ficha_manual
            
        planos_nomes = {
            'essencial': '240 MEGA',
            'rapido': '400 MEGA',
            'turbo': '500 MEGA',
            'ultra': '600 MEGA',
            '1giga': '1 GIGA',
            'plano_300': '300 MEGA',
            'plano_700': '700 MEGA'
        }
        plano_display = planos_nomes.get(self.plano, self.plano)

        ficha = f"#DADOS PARA CADASTRO\n\n"
        ficha += f"Nome completo: {self.nome_razao}\n"
        if self.tipo_pessoa == 'pj':
            ficha += f"Nome Fantasia: {self.nome_fantasia}\n"
            ficha += f"CNPJ: {self.documento}\n"
            ficha += f"Inscrição Estadual: {self.inscricao_estadual or 'Não informada'}\n"
        else:
            ficha += f"CPF: {self.documento}\n"
            ficha += f"RG: {self.rg}\n"
            ficha += f"Data de nascimento: {self.data_nascimento.strftime('%d/%m/%Y') if self.data_nascimento else 'N/A'}\n"
        
        ficha += f"E-mail: {self.email}\n"
        ficha += f"Telefone(s): {self.telefone}\n"
        ficha += f"CEP: {self.cep}\n"
        ficha += f"Cidade: {self.cidade}\n"
        ficha += f"Bairro: {self.bairro}\n"
        ficha += f"Endereço completo: {self.endereco}\n"
        if self.numero:
            ficha += f"Número: {self.numero}\n"
        if self.complemento:
            ficha += f"Complemento: {self.complemento}\n"
        if self.google_maps_link:
            ficha += f"Localização Google Maps: {self.google_maps_link}\n"
        ficha += f"Referência visual: {self.referencia}\n"
        ficha += f"Plano desejado: {plano_display}\n"
        
        # Detalhes específicos do plano
        if self.plano == 'essencial':
            ficha += f"Roteador: {'Alugado (R$ 10,00/mês)' if self.opcional else 'Do Cliente'}\n"
        elif self.plano == '1giga' and self.opcional:
            ficha += f"Roteador: Comodato + Repetidor Mesh\n"
        else:
            ficha += f"Roteador: Comodato\n"
            
        ficha += f"Gostaria da fidelidade de 12 meses? {'Sim' if self.fidelidade else 'Não'}\n"
        ficha += f"Modo de pagamento da instalação: {self.pagamento_instalacao}\n"
        ficha += f"Data e período para a instalação: {self.data_instalacao.strftime('%d/%m/%Y')} - {self.get_periodo_instalacao_display()}\n"
        ficha += f"Por onde conheceu a empresa? {self.origem}\n"
        
        return ficha

    class Meta:
        verbose_name = "Cadastro"
        verbose_name_plural = "Cadastros"