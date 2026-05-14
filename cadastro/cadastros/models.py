from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from localflavor.br.validators import BRCPFValidator, BRCNPJValidator
from simple_history.models import HistoricalRecords
import os
import unicodedata
from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile


from .document_security import validate_cliente_document_upload


def _doc_storage():
    """Storage para os FileFields de documentos.

    Com Cloudinary, retorna `AutoMediaCloudinaryStorage` (resource_type='auto'),
    que classifica imagem (JPEG, PNG, WebP) vs PDF/raw.
    Sem Cloudinary, retorna `FileSystemStorage` (default do Django).
    """
    if getattr(settings, 'CLOUDINARY_CLOUD_NAME', None):
        try:
            from .storages import AutoMediaCloudinaryStorage
            return AutoMediaCloudinaryStorage()
        except Exception:
            pass
    from django.core.files.storage import FileSystemStorage
    return FileSystemStorage()

def only_digits_br(value):
    """Apenas dígitos (CPF/CNPJ/CEP/telefone vindos do formulário)."""
    return ''.join(c for c in str(value or '') if c.isdigit())


def format_cpf_display(digits):
    d = only_digits_br(digits)
    if len(d) != 11:
        return d
    return f'{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}'


def format_cnpj_display(digits):
    d = only_digits_br(digits)
    if len(d) != 14:
        return d
    return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}'


def format_cep_display(digits):
    d = only_digits_br(digits)
    if len(d) != 8:
        return d
    return f'{d[:5]}-{d[5:]}'


def format_telefone_display(digits):
    """Padrão BR: (DD) NNNNN-NNNN / (DD) NNNN-NNNN / 9999-9999 sem DDD."""
    d = only_digits_br(digits)
    if d.startswith('55') and len(d) > 11:
        d = d[2:]
    n = len(d)
    if n == 8:
        return f'{d[:4]}-{d[4:]}'
    if n == 9 and d[0] == '9':
        return f'{d[:5]}-{d[5:]}'
    if n == 10:
        return f'({d[:2]}) {d[2:6]}-{d[6:]}'
    if n == 11:
        if d[2] == '9':
            return f'({d[:2]}) {d[2:7]}-{d[7:]}'
        return f'({d[:2]}) {d[2:6]}-{d[6:]}'
    return d


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
    ext = (filename.rsplit('.', 1)[-1] if '.' in filename else 'bin').lower()
    # Normaliza extensões equivalentes (Windows costuma salvar JPEG como .jfif)
    if ext in ('jfif', 'jpe', 'jpeg'):
        ext = 'jpg'
    clean_doc = only_digits_br(instance.documento)
    filename = f"{clean_doc}_{field_name}.{ext}"
    return os.path.join('documentos_clientes', filename)

def path_contrato(instance, filename): return get_file_path(instance, filename, 'contrato_social')
def path_comprovante(instance, filename): return get_file_path(instance, filename, 'comprovante_residencia')
def path_doc_frente(instance, filename): return get_file_path(instance, filename, 'doc_frente')
def path_doc_verso(instance, filename): return get_file_path(instance, filename, 'doc_verso')
def path_selfie(instance, filename): return get_file_path(instance, filename, 'selfie')


# Formatos raster que passam por Pillow → JPEG antes do storage (PDF não entra aqui).
_DOC_COMPRESS_EXT = frozenset({'jpg', 'jpeg', 'jfif', 'jpe', 'png', 'webp'})


def _basename_upload(name):
    return os.path.basename(name or '') or 'upload.bin'


def _maybe_compress_cadastro_document(instance, field_name):
    """Normaliza imagens para JPEG em memória (qualidade fixa). PDF só reposiciona o stream.

    `Image.open(upload)` pode avançar o cursor do arquivo: se a compressão falhar e o
    storage ler o mesmo handle, o Cloudinary pode responder «Invalid image file».
    """
    file = getattr(instance, field_name)
    if not file or getattr(file, '_committed', False):
        return

    base_fname = _basename_upload(getattr(file, 'name', '') or '')
    ext = base_fname.rsplit('.', 1)[-1].lower() if '.' in base_fname else ''

    if ext == 'pdf':
        try:
            file.seek(0)
        except Exception:
            pass
        return

    if ext and ext not in _DOC_COMPRESS_EXT:
        try:
            file.seek(0)
        except Exception:
            pass
        return

    try:
        file.seek(0)
        raw = file.read()
    except Exception:
        return

    if not raw:
        return

    stem = os.path.splitext(base_fname)[0] if '.' in base_fname else base_fname

    try:
        bio = BytesIO(raw)
        img = Image.open(bio)
        img.load()

        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        output = BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        new_filename = f'{stem}.jpg'

        output.seek(0)
        setattr(instance, field_name, ContentFile(output.read(), name=new_filename))
    except Exception:
        setattr(instance, field_name, ContentFile(raw, name=base_fname))


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
    documento = models.CharField(max_length=20, db_index=True, unique=True)  # CPF ou CNPJ
    nome_razao = models.CharField(max_length=255) # Nome ou Razão Social
    nome_fantasia = models.CharField(max_length=255, blank=True, null=True)
    rg = models.CharField(max_length=20, blank=True, null=True)
    inscricao_estadual = models.CharField(max_length=50, blank=True, null=True)
    data_nascimento = models.DateField(blank=True, null=True)
    contrato_social = models.FileField(upload_to=path_contrato, storage=_doc_storage, blank=True, null=True)

    # Documentos Adicionais
    comprovante_residencia = models.FileField(upload_to=path_comprovante, storage=_doc_storage, blank=True, null=True)
    foto_documento_frente = models.FileField(upload_to=path_doc_frente, storage=_doc_storage, blank=True, null=True)
    foto_documento_verso = models.FileField(upload_to=path_doc_verso, storage=_doc_storage, blank=True, null=True)
    selfie_documento = models.FileField(upload_to=path_selfie, storage=_doc_storage, blank=True, null=True)
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
    aluguel_roteador_wifi = models.BooleanField(default=False)
    aluguel_repetidor_mesh = models.BooleanField(default=False)
    
    # Instalação
    pagamento_instalacao = models.CharField(max_length=50)
    data_instalacao = models.DateField()
    periodo_instalacao = models.CharField(max_length=10, choices=PERIODO_CHOICES)
    origem = models.CharField(max_length=100)
    
    # Controle
    consultor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    vendedor_responsavel = models.ForeignKey(
        'cadastros.VendedorIXC',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cadastros',
        help_text=(
            'Vendedor / responsável vinculado a este cadastro. '
            'O `ixc_id` do vendedor é enviado ao IXC como id_vendedor / id_responsavel / id_vendedor_ativ.'
        ),
    )
    data_cadastro = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    ixc_lead_id = models.CharField(max_length=50, blank=True, null=True)
    ixc_lead_enviado_em = models.DateTimeField(blank=True, null=True)
    ixc_prospect_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text=(
            'ID retornado pelo IXC na etapa 2 (prospecção CRM: em geral `crm_canditados` / `crm_candidatos`; '
            'fallback legado `crm_prospect`). Usado também em fluxos de contrato quando o IXC espera esse vínculo.'
        ),
    )
    ixc_candidato_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text='ID do registro crm_canditados/crm_candidatos no IXC, quando criado encadeado após o lead.',
    )
    ixc_contrato_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text='ID do contrato (cliente_contrato) no IXC, quando criado pelo teste ou integração.',
    )
    ixc_envio_status = models.CharField(
        max_length=20,
        default='pendente',
        db_index=True,
        help_text='Último estado do envio ao IXC (histórico simple_history exige valor).',
    )
    ixc_envio_mensagem = models.TextField(
        blank=True,
        default='',
        help_text='Última mensagem da API IXC ou resumo do envio (auditoria).',
    )
    ixc_envio_logs = models.JSONField(
        default=dict,
        blank=True,
        help_text='Auditoria do envio IXC; ex.: {"text": "…linhas de log…"}. No PG pode vir como jsonb legado.',
    )

    # Campo para edição manual da ficha
    ficha_manual = models.TextField(blank=True, null=True)

    # LGPD — consentimento e anonimização
    consentimento_lgpd = models.BooleanField(
        default=False,
        help_text='Cliente declarou ter lido e concordado com a Política de Privacidade.',
    )
    consentimento_em = models.DateTimeField(blank=True, null=True)
    consentimento_ip = models.GenericIPAddressField(
        blank=True,
        null=True,
        help_text='IP de onde o consentimento foi registrado.',
    )
    anonimizado_em = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Preenchido quando o cadastro foi anonimizado por exigência LGPD.',
    )

    history = HistoricalRecords()

    def clean(self):
        # Normaliza para dígitos, valida e grava no padrão brasileiro de exibição.
        doc_digits = only_digits_br(self.documento)
        cep_digits = only_digits_br(self.cep)
        tel_digits = only_digits_br(self.telefone)

        if self.numero is not None:
            n = str(self.numero).strip()
            self.numero = n if n else None

        if self.tipo_pessoa == 'pf':
            BRCPFValidator()(doc_digits)
        else:
            BRCNPJValidator()(doc_digits)

        if len(cep_digits) != 8:
            raise ValidationError({'cep': 'CEP deve ter 8 dígitos.'})

        if tel_digits.startswith('55') and len(tel_digits) >= 12:
            tel_digits = tel_digits[2:]
        if len(tel_digits) < 8 or len(tel_digits) > 11:
            raise ValidationError(
                {'telefone': 'Informe um telefone válido (com DDD: 10 ou 11 dígitos, ou 8/9 dígitos sem DDD).'}
            )

        # Maioridade (18+) — apenas pessoa física com data informada
        if self.tipo_pessoa == 'pf' and self.data_nascimento:
            today = timezone.localdate()
            born = self.data_nascimento
            age = today.year - born.year - (
                (today.month, today.day) < (born.month, born.day)
            )
            if age < 18:
                raise ValidationError(
                    'É necessário ter pelo menos 18 anos para realizar o cadastro.'
                )

        for fname in (
            'contrato_social',
            'comprovante_residencia',
            'foto_documento_frente',
            'foto_documento_verso',
            'selfie_documento',
        ):
            field_file = getattr(self, fname)
            if not field_file:
                continue
            if getattr(field_file, '_committed', False):
                continue
            validate_cliente_document_upload(field_file, fname)

        # Duplicidade: compara pelo valor numérico (registros antigos podem estar só com dígitos).
        for other in Cadastro.objects.exclude(pk=self.pk).only('documento', 'status'):
            if only_digits_br(other.documento) == doc_digits:
                raise ValidationError(
                    f'Já existe um cadastro com este CPF/CNPJ. Status: {other.get_status_display()}'
                )

        if self.tipo_pessoa == 'pf':
            self.documento = format_cpf_display(doc_digits)
        else:
            self.documento = format_cnpj_display(doc_digits)
        self.cep = format_cep_display(cep_digits)
        self.telefone = format_telefone_display(tel_digits)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')

        # Saves parciais (update_fields) NÃO disparam full_clean: evita revalidar
        # CPF/duplicidade/imagens em ações leves (update_status, update_ficha, etc.)
        # e evita falsos positivos quando a constraint unique já está no banco.
        if not update_fields:
            self.full_clean()

            # Imagens → JPEG (cópia em RAM); PDF não passa pelo Pillow.
            for field in ['comprovante_residencia', 'foto_documento_frente', 'foto_documento_verso', 'selfie_documento']:
                _maybe_compress_cadastro_document(self, field)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nome_razao} - {self.documento}"

    # Fallbacks para quando PlanoDefinicao ainda não tem dados (legado).
    # Idealmente vazio: gerencie tudo em /admin-dash/operacao/.
    _PLANOS_VELOCIDADE_FALLBACK = {
        'essencial': '240 MEGA',
        'rapido': '400 MEGA',
        'turbo': '500 MEGA',
        'ultra': '600 MEGA',
        'prime': '700 MEGA',
        '1giga': '1 GIGA',
        'plano_300': '300 MEGA',
        'plano_700': '700 MEGA',
    }
    _PLANOS_PRECO_FALLBACK = {
        'essencial': '59,99',
        'rapido': '79,99',
        'turbo': '99,99',
        'ultra': '119,99',
        'prime': '99,99',
        '1giga': '149,99',
        'plano_300': '69,99',
        'plano_700': '89,99',
    }

    def _get_plano_definicao(self):
        """Resolve o PlanoDefinicao para esta combinação cidade+plano."""
        if not self.plano:
            return None
        try:
            cidade = CidadeOperacao.objects.select_related('grupo_planos').get(slug=self.cidade)
        except CidadeOperacao.DoesNotExist:
            return None
        return PlanoDefinicao.objects.filter(grupo=cidade.grupo_planos, codigo=self.plano).first()

    @property
    def plano_velocidade(self):
        definicao = self._get_plano_definicao()
        if definicao:
            label = definicao.velocidade_label()
            if label:
                return label
        return self._PLANOS_VELOCIDADE_FALLBACK.get(self.plano, self.plano)

    @property
    def plano_preco_brl(self):
        """Mensalidade formatada estilo BR ('59,99')."""
        definicao = self._get_plano_definicao()
        if definicao and (definicao.preco_mensal_reais or 0) > 0:
            return definicao.preco_formatado()
        return self._PLANOS_PRECO_FALLBACK.get(self.plano, '0,00')

    @property
    def nome_consultor_display(self):
        """Nome para OS/ficha: nome completo do usuário; senão primeiro nome; senão login."""
        if not self.consultor_id:
            return 'N/A'
        user = self.consultor
        nome = (user.get_full_name() or '').strip()
        if nome:
            return nome
        primeiro = (user.first_name or '').strip()
        if primeiro:
            return primeiro
        login = (user.username or '').strip()
        return login if login else 'N/A'

    @property
    def os_formatada(self):
        instalacao_valor = "100,00" if self.fidelidade else "460,00" if self.cidade == 'marica' else "A combinar"

        plano_label = self.plano_velocidade
        plano_valor = self.plano_preco_brl
        
        extras = []
        if self.aluguel_repetidor_mesh:
            extras.append('REPETIDOR MESH EM ALUGUEL')
        if self.aluguel_roteador_wifi:
            extras.append('ROTEADOR WI-FI EM ALUGUEL')
        if extras:
            router_info = 'COM ' + ' E '.join(extras)
        elif self.plano == 'essencial':
            router_info = 'COM ROTEADOR DO CLIENTE'
        else:
            router_info = 'COM ROTEADOR EM COMODATO'
            
        os_text = f"INSTALAÇÃO SERÁ PAGA NO VALOR DE R$ {instalacao_valor}\n\n"
        os_text += f"PLANO DE {plano_label} / R$ {plano_valor} {router_info}\n\n"
        os_text += f"DATA DE VENCIMENTO: {self.vencimento}\n\n"
        os_text += f"CONSULTOR(A): {self.nome_consultor_display}\n\n"
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

        plano_display = self.plano_velocidade

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
            ficha += f"Localização (mapa): {self.google_maps_link}\n"
        ficha += f"Referência visual: {self.referencia}\n"
        ficha += f"Plano desejado: {plano_display}\n"
        
        if self.plano == 'essencial':
            ficha += f"Roteador Wi-Fi em aluguel (R$ 10/mês): {'Sim' if self.aluguel_roteador_wifi else 'Não'}\n"
            ficha += f"Repetidor Mesh em aluguel (R$ 29,99/mês): {'Sim' if self.aluguel_repetidor_mesh else 'Não'}\n"
        else:
            if self.aluguel_repetidor_mesh:
                ficha += 'Repetidor Mesh em aluguel: Sim\n'
            else:
                ficha += 'Roteador: Comodato\n'
            
        ficha += f"Gostaria da fidelidade de 12 meses? {'Sim' if self.fidelidade else 'Não'}\n"
        ficha += f"Modo de pagamento da instalação: {self.pagamento_instalacao}\n"
        ficha += f"Data e período para a instalação: {self.data_instalacao.strftime('%d/%m/%Y')} - {self.get_periodo_instalacao_display()}\n"
        ficha += f"Por onde conheceu a empresa? {self.origem}\n"
        ficha += f"Consultor(a): {self.nome_consultor_display}\n"

        return _append_modelo_ficha_global(ficha)

    class Meta:
        verbose_name = "Cadastro"
        verbose_name_plural = "Cadastros"

    # ----------- LGPD -----------
    @property
    def is_anonimizado(self):
        return self.anonimizado_em is not None

    def anonimizar(self, executado_por=None, motivo: str = ''):
        """
        Substitui PII (nome, CPF/CNPJ, RG, e-mail, telefone, endereço, fotos)
        por placeholders e remove arquivos físicos. Mantém estatísticas (status,
        plano, cidade, datas) intactas.

        Idempotente: se já foi anonimizado, não faz nada.
        """
        if self.is_anonimizado:
            return False

        for field in [
            'contrato_social',
            'comprovante_residencia',
            'foto_documento_frente',
            'foto_documento_verso',
            'selfie_documento',
        ]:
            file = getattr(self, field)
            if file:
                try:
                    file.delete(save=False)
                except Exception:
                    pass
                setattr(self, field, None)

        suffix = f"ANON-{self.pk}"
        self.nome_razao = f"[Cadastro anonimizado #{self.pk}]"
        self.nome_fantasia = None
        self.documento = suffix[:20]  # mantém único; respeita unique=True
        self.rg = None
        self.inscricao_estadual = None
        self.data_nascimento = None
        self.email = f"anon+{self.pk}@example.invalid"
        self.telefone = '0' * 10
        self.endereco = '[anonimizado]'
        self.numero = None
        self.complemento = None
        self.referencia = '[anonimizado]'
        self.google_maps_link = None
        self.ficha_manual = None
        self.ixc_lead_id = None
        self.ixc_lead_enviado_em = None
        self.ixc_prospect_id = None
        self.ixc_candidato_id = None
        self.ixc_contrato_id = None
        self.ixc_envio_status = 'pendente'
        self.ixc_envio_mensagem = ''
        self.ixc_envio_logs = {}
        self.consentimento_ip = None
        self.anonimizado_em = timezone.now()

        # save() bypassa full_clean() porque o documento agora é placeholder
        # (não-CPF/CNPJ) e essas validações falhariam.
        super(Cadastro, self).save()

        AcessoDadoSensivel.objects.create(
            user=executado_por,
            cadastro=self,
            acao='anonimizado',
            motivo=motivo or 'Anonimização LGPD',
        )
        return True


class AcessoDadoSensivel(models.Model):
    """
    Audit log para acesso a dados pessoais (PII).
    Registramos apenas acessos cross-consultor (admin abrindo cadastro de
    outro consultor) e ações sensíveis (export, anonimização).
    """
    ACAO_CHOICES = [
        ('visualizou', 'Visualizou cadastro'),
        ('exportou', 'Exportou JSON'),
        ('editou', 'Editou cadastro'),
        ('anonimizado', 'Anonimizou cadastro'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='acessos_pii')
    cadastro = models.ForeignKey('Cadastro', on_delete=models.CASCADE, related_name='acessos')
    acao = models.CharField(max_length=20, choices=ACAO_CHOICES, default='visualizou')
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    motivo = models.CharField(max_length=255, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = 'Acesso a dado sensível'
        verbose_name_plural = 'Acessos a dados sensíveis'
        ordering = ['-criado_em']

    def __str__(self):
        who = self.user.get_username() if self.user else '(removido)'
        return f"{who} {self.get_acao_display().lower()} cadastro #{self.cadastro_id} em {self.criado_em:%d/%m/%Y %H:%M}"


from .operacao_models import (  # noqa: E402
    AppConfigOperacao,
    CidadeOperacao,
    FaixaVencimento,
    OpcaoVencimento,
    OrigemCanalVenda,
    PlanoDefinicao,
    PlanoGrupo,
    VagaInstalacao,
)


def _append_modelo_ficha_global(ficha_text):
    try:
        extra = AppConfigOperacao.load().modelo_observacoes_ficha
        if extra and str(extra).strip():
            return ficha_text + '\n' + str(extra).strip() + '\n'
    except Exception:
        pass
    return ficha_text