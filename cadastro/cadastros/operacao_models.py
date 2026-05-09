"""
Configuração operacional da ficha pública: cidades, planos, vencimentos, IXC e políticas.
Editável pelo painel em /admin-dash/operacao/.
"""
from django.core.exceptions import ValidationError
from django.db import models


class PlanoGrupo(models.Model):
    """Agrupa textos de planos (ex.: padrão Maricá, Muqui/Piúma, Mimoso)."""

    slug = models.SlugField(max_length=50, unique=True)
    nome = models.CharField(max_length=120, help_text='Nome interno para o admin')

    class Meta:
        verbose_name = 'Grupo de planos'
        verbose_name_plural = 'Grupos de planos'
        ordering = ['slug']

    def __str__(self):
        return f'{self.nome} ({self.slug})'


class PlanoDefinicao(models.Model):
    """Um plano dentro de um grupo (essencial, rapido, …) com texto exibido na ficha."""

    grupo = models.ForeignKey(PlanoGrupo, on_delete=models.CASCADE, related_name='planos')
    codigo = models.SlugField(
        max_length=50,
        help_text='Valor enviado no campo plano (ex.: essencial, 1giga, plano_300)',
    )
    titulo = models.CharField(max_length=200)
    descricao_html = models.TextField(help_text='HTML permitido (quebras &lt;br&gt;)')
    texto_opcional = models.TextField(
        blank=True,
        help_text='Texto do opcional «repetidor Mesh em aluguel». Se vazio, usa o padrão global da ficha.',
    )
    ordem = models.PositiveSmallIntegerField(default=0)
    ixc_plano_venda_id = models.CharField(
        max_length=32,
        blank=True,
        help_text='ID do plano de venda no IXC (sobrescreve o mapa padrão se preenchido)',
    )
    nome_velocidade = models.CharField(
        max_length=40,
        blank=True,
        help_text='Texto curto exibido em listagens / OS (ex.: «240 MEGA», «1 GIGA»). Vazio = usar o "titulo".',
    )
    preco_mensal_reais = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text='Mensalidade em R$ usada na geração da OS / ficha automática.',
    )

    class Meta:
        verbose_name = 'Definição de plano'
        verbose_name_plural = 'Definições de planos'
        ordering = ['grupo', 'ordem', 'codigo']
        unique_together = [['grupo', 'codigo']]

    def __str__(self):
        return f'{self.grupo.slug}:{self.codigo}'

    def preco_formatado(self):
        """Mensalidade formatada para BR ('59,99'). Retorna '0,00' se não definida."""
        valor = self.preco_mensal_reais or 0
        return f'{valor:.2f}'.replace('.', ',')

    def velocidade_label(self):
        """Texto da velocidade (nome_velocidade, com fallback no titulo)."""
        if self.nome_velocidade:
            return self.nome_velocidade
        return self.titulo or self.codigo


class CidadeOperacao(models.Model):
    slug = models.SlugField(max_length=50, unique=True)
    nome_exibicao = models.CharField(max_length=120)
    uf_padrao = models.CharField(max_length=2)
    grupo_planos = models.ForeignKey(PlanoGrupo, on_delete=models.PROTECT, related_name='cidades')
    ordem = models.PositiveSmallIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    skip_etapa_documentacao = models.BooleanField(
        default=False,
        help_text='Se verdadeiro, o passo de upload de documentos é pulado.',
    )
    permite_opcao_termo = models.BooleanField(
        default=False,
        help_text='Exibe “levar termo” em vez de comprovante (Unamar/Cabo Frio/SP).',
    )
    sempre_exibir_pagamento_instalacao = models.BooleanField(
        default=False,
        help_text='Maricá: sempre mostrar forma de pagamento da instalação.',
    )
    instalacao_com_fidelidade_gratis = models.BooleanField(
        default=True,
        help_text='Se falso, usa valores abaixo mesmo com fidelidade.',
    )
    instalacao_valor_com_fidel_reais = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    instalacao_valor_sem_fidel_reais = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=360,
    )

    ixc_filial_id = models.CharField(max_length=32, blank=True)
    ixc_cidade_id = models.CharField(max_length=32, blank=True)

    exigir_fotos_documentacao = models.BooleanField(
        null=True,
        blank=True,
        help_text='Vazio = usar configuração global da ficha.',
    )

    class Meta:
        verbose_name = 'Cidade / filial (ficha)'
        verbose_name_plural = 'Cidades / filiais (ficha)'
        ordering = ['ordem', 'nome_exibicao']

    def __str__(self):
        return self.nome_exibicao


class FaixaVencimento(models.Model):
    cidade = models.ForeignKey(
        CidadeOperacao,
        on_delete=models.CASCADE,
        related_name='faixas_vencimento',
    )
    dia_inicio = models.PositiveSmallIntegerField()
    dia_fim = models.PositiveSmallIntegerField()
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Faixa de vencimento'
        verbose_name_plural = 'Faixas de vencimento'
        ordering = ['cidade', 'ordem']

    def clean(self):
        if self.dia_inicio > self.dia_fim:
            raise ValidationError('Dia inicial deve ser menor ou igual ao dia final.')
        for v in (self.dia_inicio, self.dia_fim):
            if not (1 <= v <= 31):
                raise ValidationError('Dias devem estar entre 1 e 31.')

    def __str__(self):
        return f'{self.cidade.slug} {self.dia_inicio}-{self.dia_fim}'


class OpcaoVencimento(models.Model):
    faixa = models.ForeignKey(
        FaixaVencimento,
        on_delete=models.CASCADE,
        related_name='opcoes',
    )
    dia_str = models.CharField(max_length=2, help_text="Dois dígitos, ex.: '03'")
    ixc_id = models.CharField(
        max_length=32,
        help_text='ID de vencimento no IXC (ou texto para referência)',
    )
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Opção de vencimento'
        verbose_name_plural = 'Opções de vencimento'
        ordering = ['faixa', 'ordem']

    def __str__(self):
        return f'Dia {self.dia_str} → {self.ixc_id}'


class AppConfigOperacao(models.Model):
    """Singleton (pk=1): parâmetros globais da ficha."""

    dias_antecedencia_minima_instalacao = models.PositiveSmallIntegerField(
        default=1,
        help_text='1 = mínimo amanhã; 2 = depois de amanhã, etc.',
    )
    texto_ajuda_documentos = models.TextField(
        blank=True,
        help_text='Texto opcional exibido no passo de documentos (futuro front).',
    )
    modelo_observacoes_ficha = models.TextField(
        blank=True,
        help_text='Bloco extra acrescentado ao final da ficha automática (consultores).',
    )
    exigir_fotos_documentacao = models.BooleanField(
        default=True,
        help_text='Padrão quando a cidade não define override.',
    )

    class Meta:
        verbose_name = 'Configuração geral da ficha'
        verbose_name_plural = 'Configuração geral da ficha'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Configuração geral'


class OrigemCanalVenda(models.Model):
    """Origem/canal de venda mapeado para o ID do IXC (substitui ORIGENS_MAP hardcoded)."""

    label = models.CharField(
        max_length=80,
        unique=True,
        help_text='Nome exibido na ficha (ex.: Instagram, Facebook, Indicação).',
    )
    ixc_id = models.CharField(
        max_length=32,
        help_text='ID correspondente em CRM > Configurações > Origens no IXC.',
    )
    ordem = models.PositiveSmallIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Origem / canal de venda'
        verbose_name_plural = 'Origens / canais de venda'
        ordering = ['ordem', 'label']

    def __str__(self):
        return f'{self.label} → {self.ixc_id}'


class VagaInstalacao(models.Model):
    """Capacidade por dia/período (opcional; pode ser expandida no JS depois)."""

    PERIODO_CHOICES = [
        ('manha', 'Manhã'),
        ('tarde', 'Tarde'),
    ]

    data = models.DateField()
    periodo = models.CharField(max_length=10, choices=PERIODO_CHOICES)
    vagas_max = models.PositiveIntegerField(default=10)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Vaga de instalação'
        verbose_name_plural = 'Vagas de instalação'
        unique_together = [['data', 'periodo']]
        ordering = ['data', 'periodo']

    def __str__(self):
        return f'{self.data} {self.get_periodo_display()} ({self.vagas_max})'
