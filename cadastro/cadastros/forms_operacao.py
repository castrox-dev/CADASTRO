import re

from django import forms
from django.forms import inlineformset_factory

from .operacao_models import (
    AppConfigOperacao,
    CidadeOperacao,
    FaixaVencimento,
    OpcaoVencimento,
    PlanoDefinicao,
    PlanoGrupo,
    VagaInstalacao,
    VendedorIXC,
)

TEXTAREA = forms.Textarea(attrs={'class': 'form-control form-control-premium', 'rows': 4})
CONTROL = {'class': 'form-control form-control-premium'}
CHECK = {'class': 'form-check-input'}

# Descrição do plano: Enter vira <br>; negrito no admin com *texto* ou **texto** (como WhatsApp).
_RE_BR = re.compile(r'<br\s*/?>', re.IGNORECASE)
_RE_STRONG = re.compile(r'<strong>([^<]*)</strong>', re.IGNORECASE)


def descricao_html_para_editor(valor):
    """HTML salvo → texto no textarea: <br> vira Enter; <strong> vira *…*."""
    if not valor or not str(valor).strip():
        return ''
    t = _RE_BR.sub('\n', str(valor).strip())
    t = _RE_STRONG.sub(r'*\1*', t)
    return t


def editor_para_descricao_html(texto):
    """Textarea → HTML da ficha: *negrito* / **negrito** e quebras de linha."""
    if texto is None:
        return ''
    s = str(texto).replace('\r\n', '\n').replace('\r', '\n')
    linhas = s.split('\n')
    while linhas and linhas[-1] == '':
        linhas.pop()
    joined = '<br>'.join(linhas)
    joined = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', joined)
    joined = re.sub(r'\*([^*\n<]+)\*', r'<strong>\1</strong>', joined)
    return joined


class AppConfigOperacaoForm(forms.ModelForm):
    class Meta:
        model = AppConfigOperacao
        fields = (
            'dias_antecedencia_minima_instalacao',
            'exigir_fotos_documentacao',
            'texto_ajuda_documentos',
            'modelo_observacoes_ficha',
            'ixc_tipo_documento_fatura_id',
            'ixc_produto_instalacao_id',
            'ixc_fidelidade_meses',
        )
        widgets = {
            'dias_antecedencia_minima_instalacao': forms.NumberInput(attrs={**CONTROL, 'min': 1}),
            'texto_ajuda_documentos': TEXTAREA,
            'modelo_observacoes_ficha': TEXTAREA,
            'exigir_fotos_documentacao': forms.CheckboxInput(attrs=CHECK),
            'ixc_tipo_documento_fatura_id': forms.TextInput(attrs={**CONTROL, 'placeholder': '501', 'inputmode': 'numeric'}),
            'ixc_produto_instalacao_id': forms.TextInput(attrs={**CONTROL, 'placeholder': '146', 'inputmode': 'numeric'}),
            'ixc_fidelidade_meses': forms.NumberInput(attrs={**CONTROL, 'min': 0, 'max': 60, 'placeholder': '12'}),
        }
        labels = {
            'ixc_tipo_documento_fatura_id': 'IXC — Tipo de documento da fatura',
            'ixc_produto_instalacao_id': 'IXC — Produto da taxa de ativação',
            'ixc_fidelidade_meses': 'IXC — Fidelidade (meses)',
        }
        help_texts = {
            'ixc_tipo_documento_fatura_id': 'id_tipo_documento da fatura (na Fibramar = 501).',
            'ixc_produto_instalacao_id': 'id_produto_ativ enviado quando o cliente paga taxa de instalação (na Fibramar = 146).',
            'ixc_fidelidade_meses': 'Valor do campo `fidelidade` quando o cliente aceita fidelidade. Sem fidelidade vai vazio para o IXC.',
        }


class PlanoGrupoForm(forms.ModelForm):
    class Meta:
        model = PlanoGrupo
        fields = ('slug', 'nome')
        widgets = {
            'slug': forms.TextInput(attrs=CONTROL),
            'nome': forms.TextInput(attrs=CONTROL),
        }


class PlanoDefinicaoForm(forms.ModelForm):
    class Meta:
        model = PlanoDefinicao
        fields = (
            'codigo',
            'titulo',
            'nome_velocidade',
            'preco_mensal_reais',
            'descricao_html',
            'texto_opcional',
            'ordem',
            'ixc_plano_venda_id',
        )
        widgets = {
            'codigo': forms.TextInput(attrs=CONTROL),
            'titulo': forms.TextInput(attrs=CONTROL),
            'nome_velocidade': forms.TextInput(attrs={**CONTROL, 'placeholder': 'Ex.: 240 MEGA, 1 GIGA'}),
            'preco_mensal_reais': forms.NumberInput(attrs={**CONTROL, 'step': '0.01', 'min': 0, 'placeholder': '0.00'}),
            'descricao_html': forms.Textarea(attrs={**CONTROL, 'rows': 10}),
            'texto_opcional': forms.Textarea(attrs={**CONTROL, 'rows': 2}),
            'ordem': forms.NumberInput(attrs={**CONTROL, 'min': 0}),
            'ixc_plano_venda_id': forms.TextInput(attrs=CONTROL),
        }
        labels = {
            'descricao_html': 'Descrição na ficha',
            'nome_velocidade': 'Velocidade (texto curto)',
            'preco_mensal_reais': 'Mensalidade (R$)',
        }
        help_texts = {
            'descricao_html': 'Use Enter para nova linha. Negrito: *preço* ou **destaque** (como WhatsApp). Não é necessário usar códigos HTML.',
            'nome_velocidade': 'Aparece em listagens e na OS automática (ex.: «240 MEGA»). Vazio = usar o "Título".',
            'preco_mensal_reais': 'Mensalidade em reais usada na geração da OS / ficha automática.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and self.instance.pk and self.instance.descricao_html:
            self.initial['descricao_html'] = descricao_html_para_editor(self.instance.descricao_html)

    def clean_descricao_html(self):
        return editor_para_descricao_html(self.cleaned_data.get('descricao_html', ''))


PlanoDefinicaoFormSet = inlineformset_factory(
    PlanoGrupo,
    PlanoDefinicao,
    form=PlanoDefinicaoForm,
    extra=1,
    can_delete=True,
)


class CidadeOperacaoForm(forms.ModelForm):
    class Meta:
        model = CidadeOperacao
        fields = (
            'slug',
            'nome_exibicao',
            'uf_padrao',
            'grupo_planos',
            'ordem',
            'ativo',
            'skip_etapa_documentacao',
            'permite_opcao_termo',
            'sempre_exibir_pagamento_instalacao',
            'instalacao_com_fidelidade_gratis',
            'instalacao_valor_com_fidel_reais',
            'instalacao_valor_sem_fidel_reais',
            'ixc_filial_id',
            'ixc_cidade_id',
            'ixc_setor_id',
            'ixc_carteira_cobranca_id',
            'ixc_tipo_doc_ativ_id',
            'exigir_fotos_documentacao',
        )
        widgets = {
            'slug': forms.TextInput(attrs=CONTROL),
            'nome_exibicao': forms.TextInput(attrs=CONTROL),
            'uf_padrao': forms.TextInput(attrs={**CONTROL, 'maxlength': 2}),
            'grupo_planos': forms.Select(attrs=CONTROL),
            'ordem': forms.NumberInput(attrs={**CONTROL, 'min': 0}),
            'ativo': forms.CheckboxInput(attrs=CHECK),
            'skip_etapa_documentacao': forms.CheckboxInput(attrs=CHECK),
            'permite_opcao_termo': forms.CheckboxInput(attrs=CHECK),
            'sempre_exibir_pagamento_instalacao': forms.CheckboxInput(attrs=CHECK),
            'instalacao_com_fidelidade_gratis': forms.CheckboxInput(attrs=CHECK),
            'instalacao_valor_com_fidel_reais': forms.NumberInput(attrs={**CONTROL, 'step': '0.01'}),
            'instalacao_valor_sem_fidel_reais': forms.NumberInput(attrs={**CONTROL, 'step': '0.01'}),
            'ixc_filial_id': forms.TextInput(attrs={**CONTROL, 'placeholder': 'Ex.: 2 (Maricá), 7 (Saquarema)', 'inputmode': 'numeric'}),
            'ixc_cidade_id': forms.TextInput(attrs={**CONTROL, 'placeholder': 'ID da cidade no IXC', 'inputmode': 'numeric'}),
            'ixc_setor_id': forms.TextInput(attrs={**CONTROL, 'placeholder': 'Ex.: 1 (Maricá), 23 (Saquarema)', 'inputmode': 'numeric'}),
            'ixc_carteira_cobranca_id': forms.TextInput(attrs={**CONTROL, 'placeholder': 'Ex.: 108 (Maricá c/ desconto)', 'inputmode': 'numeric'}),
            'ixc_tipo_doc_ativ_id': forms.TextInput(attrs={**CONTROL, 'placeholder': 'Ex.: 702 (F02), 703 (F07)', 'inputmode': 'numeric'}),
            'exigir_fotos_documentacao': forms.NullBooleanSelect(attrs=CONTROL),
        }


class FaixaVencimentoForm(forms.ModelForm):
    class Meta:
        model = FaixaVencimento
        fields = ('dia_inicio', 'dia_fim', 'ordem')
        widgets = {
            'dia_inicio': forms.NumberInput(attrs={**CONTROL, 'min': 1, 'max': 31}),
            'dia_fim': forms.NumberInput(attrs={**CONTROL, 'min': 1, 'max': 31}),
            'ordem': forms.NumberInput(attrs={**CONTROL, 'min': 0}),
        }


OpcaoVencimentoFormSet = inlineformset_factory(
    FaixaVencimento,
    OpcaoVencimento,
    fields=('dia_str', 'ixc_id', 'ordem'),
    extra=1,
    can_delete=True,
    widgets={
        'dia_str': forms.TextInput(attrs={**CONTROL, 'maxlength': 2, 'placeholder': '03'}),
        'ixc_id': forms.TextInput(attrs=CONTROL),
        'ordem': forms.NumberInput(attrs={**CONTROL, 'min': 0}),
    },
)


class VagaInstalacaoForm(forms.ModelForm):
    class Meta:
        model = VagaInstalacao
        fields = ('data', 'periodo', 'vagas_max', 'ativo')
        widgets = {
            'data': forms.DateInput(attrs={**CONTROL, 'type': 'date'}),
            'periodo': forms.Select(attrs=CONTROL),
            'vagas_max': forms.NumberInput(attrs={**CONTROL, 'min': 1}),
            'ativo': forms.CheckboxInput(attrs=CHECK),
        }


class VendedorIXCForm(forms.ModelForm):
    class Meta:
        model = VendedorIXC
        fields = (
            'nome',
            'usuario',
            'ixc_id',
            'ixc_id_responsavel',
            'email',
            'telefone',
            'ordem',
            'ativo',
            'padrao',
            'observacao',
        )
        widgets = {
            'nome': forms.TextInput(attrs={**CONTROL, 'placeholder': 'Ex.: Marcelo Castro'}),
            'usuario': forms.Select(attrs=CONTROL),
            'ixc_id': forms.TextInput(attrs={**CONTROL, 'placeholder': 'ID do vendedor IXC (ex.: 242)', 'inputmode': 'numeric'}),
            'ixc_id_responsavel': forms.TextInput(attrs={**CONTROL, 'placeholder': 'ID do responsável IXC — vazio usa o do vendedor', 'inputmode': 'numeric'}),
            'email': forms.EmailInput(attrs={**CONTROL, 'placeholder': 'opcional@fibramar.com.br'}),
            'telefone': forms.TextInput(attrs={**CONTROL, 'placeholder': 'Opcional'}),
            'ordem': forms.NumberInput(attrs={**CONTROL, 'min': 0}),
            'ativo': forms.CheckboxInput(attrs=CHECK),
            'padrao': forms.CheckboxInput(attrs=CHECK),
            'observacao': forms.TextInput(attrs={**CONTROL, 'placeholder': 'Anotação interna (opcional)'}),
        }
        labels = {
            'usuario': 'Consultor (usuário do sistema)',
            'ixc_id': 'ID do vendedor (IXC)',
            'ixc_id_responsavel': 'ID do responsável (IXC)',
        }
        help_texts = {
            'usuario': 'Quando preenchido, os cadastros criados por este consultor herdam automaticamente estes IDs.',
            'ixc_id_responsavel': 'Use só se o responsável for diferente do vendedor; se igual, deixe vazio.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limita o select de "usuário" a quem ainda não tem vendedor vinculado
        # (mostrando o atual quando estiver editando).
        from django.contrib.auth import get_user_model

        User = get_user_model()
        qs = User.objects.filter(vendedor_ixc__isnull=True)
        if self.instance and self.instance.pk and self.instance.usuario_id:
            qs = qs | User.objects.filter(pk=self.instance.usuario_id)
        self.fields['usuario'].queryset = qs.order_by('first_name', 'username')
        self.fields['usuario'].empty_label = '— Sem vínculo (vendedor avulso) —'
        self.fields['usuario'].required = False

    def clean_ixc_id(self):
        val = (self.cleaned_data.get('ixc_id') or '').strip()
        if not val:
            raise forms.ValidationError('Informe o ID do vendedor no IXC.')
        if not val.isdigit():
            raise forms.ValidationError('O ID do IXC deve conter apenas números (ex.: 242).')
        return val

    def clean_ixc_id_responsavel(self):
        val = (self.cleaned_data.get('ixc_id_responsavel') or '').strip()
        if val and not val.isdigit():
            raise forms.ValidationError('O ID do responsável deve conter apenas números.')
        return val
