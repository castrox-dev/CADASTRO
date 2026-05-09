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
        )
        widgets = {
            'dias_antecedencia_minima_instalacao': forms.NumberInput(attrs={**CONTROL, 'min': 1}),
            'texto_ajuda_documentos': TEXTAREA,
            'modelo_observacoes_ficha': TEXTAREA,
            'exigir_fotos_documentacao': forms.CheckboxInput(attrs=CHECK),
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
        fields = ('codigo', 'titulo', 'descricao_html', 'texto_opcional', 'ordem', 'ixc_plano_venda_id')
        widgets = {
            'codigo': forms.TextInput(attrs=CONTROL),
            'titulo': forms.TextInput(attrs=CONTROL),
            'descricao_html': forms.Textarea(attrs={**CONTROL, 'rows': 10}),
            'texto_opcional': forms.Textarea(attrs={**CONTROL, 'rows': 2}),
            'ordem': forms.NumberInput(attrs={**CONTROL, 'min': 0}),
            'ixc_plano_venda_id': forms.TextInput(attrs=CONTROL),
        }
        labels = {
            'descricao_html': 'Descrição na ficha',
        }
        help_texts = {
            'descricao_html': 'Use Enter para nova linha. Negrito: *preço* ou **destaque** (como WhatsApp). Não é necessário usar códigos HTML.',
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
            'ixc_filial_id': forms.TextInput(attrs=CONTROL),
            'ixc_cidade_id': forms.TextInput(attrs=CONTROL),
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
