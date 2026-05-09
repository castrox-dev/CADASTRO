"""
ModelForm único para criação/edição do Cadastro.

Substitui o acesso direto a `request.POST.get(...)` campo a campo nas views
`client_form` e `edit_cadastro`, eliminando ~40 atribuições duplicadas e
unificando regras (limpeza de máscaras, defaults).

A validação «pesada» (CPF/CNPJ, maioridade, duplicidade) continua em
`Cadastro.clean()` — o ModelForm já invoca essa validação automaticamente.
"""
from django import forms

from .models import Cadastro


class CadastroForm(forms.ModelForm):
    """Form do `Cadastro` reutilizado nas views de criação e edição.

    Compatibilidade com o front atual:
    - aceita `tipoPessoa` (camelCase) como alias para `tipo_pessoa`;
    - converte os checkboxes que vêm como `'1'` / `'sim'` / `'on'` em booleano;
    - permite que arquivos venham apenas no POST de edição (todos blank).
    """

    # Aliases / campos auxiliares que o template multi-step envia
    tipoPessoa = forms.CharField(required=False)
    fidelidade_str = forms.CharField(required=False)
    aluguel_roteador_wifi_str = forms.CharField(required=False)
    aluguel_repetidor_mesh_str = forms.CharField(required=False)
    levar_termo_str = forms.CharField(required=False)

    class Meta:
        model = Cadastro
        fields = [
            'tipo_pessoa',
            'documento',
            'nome_razao',
            'nome_fantasia',
            'rg',
            'inscricao_estadual',
            'data_nascimento',
            'contrato_social',
            'comprovante_residencia',
            'foto_documento_frente',
            'foto_documento_verso',
            'selfie_documento',
            'levar_termo',
            'email',
            'telefone',
            'cep',
            'cidade',
            'uf',
            'bairro',
            'endereco',
            'numero',
            'complemento',
            'referencia',
            'google_maps_link',
            'plano',
            'fidelidade',
            'vencimento',
            'vencimento_id',
            'aluguel_roteador_wifi',
            'aluguel_repetidor_mesh',
            'pagamento_instalacao',
            'data_instalacao',
            'periodo_instalacao',
            'origem',
        ]

    def __init__(self, *args, partial=False, **kwargs):
        """`partial=True` torna todos os campos opcionais (uso em edição parcial)."""
        super().__init__(*args, **kwargs)
        if partial:
            for f in self.fields.values():
                f.required = False

    # --- Pré-processamento (compatibilidade com o front legado) -------------
    def clean(self):
        cleaned = super().clean()
        data = self.data

        # tipoPessoa (camelCase) → tipo_pessoa
        tipo_alias = (data.get('tipoPessoa') or '').strip()
        if tipo_alias and not cleaned.get('tipo_pessoa'):
            cleaned['tipo_pessoa'] = tipo_alias

        # Checkboxes que chegam como '1' / 'sim' / 'on'
        cleaned['fidelidade'] = self._to_bool(data.get('fidelidade'), {'sim', '1', 'on', 'true'})
        cleaned['aluguel_roteador_wifi'] = self._to_bool(data.get('aluguel_roteador_wifi'))
        cleaned['aluguel_repetidor_mesh'] = self._to_bool(data.get('aluguel_repetidor_mesh'))
        cleaned['levar_termo'] = self._to_bool(data.get('levar_termo'))
        return cleaned

    @staticmethod
    def _to_bool(value, truthy=None):
        truthy = truthy or {'1', 'on', 'true', 'sim'}
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in truthy

    # --- API utilitária -----------------------------------------------------
    def apply_to(self, instance, files=None):
        """Atualiza `instance` com os dados validados, sem salvar.

        Convenção: o template submete o formulário completo. Logo:
        - Campos não enviados no POST (key ausente em `self.data`) NÃO são
          alterados — preserva-se o valor já existente no instance.
        - BooleanField segue a semântica de checkbox HTML: se o `name` está
          ausente, considera-se desmarcado (False); se está presente, True.
        - Uploads só substituem o anterior quando vierem em `files`.
        """
        cleaned = self.cleaned_data
        submitted = set(self.data.keys())
        if 'tipoPessoa' in submitted:
            submitted.add('tipo_pessoa')

        for name in self.Meta.fields:
            field_obj = self.fields.get(name)
            if isinstance(field_obj, forms.BooleanField):
                setattr(instance, name, bool(cleaned.get(name)))
            elif name in submitted and name in cleaned:
                setattr(instance, name, cleaned[name])

        if files:
            for upload_field in (
                'contrato_social',
                'comprovante_residencia',
                'foto_documento_frente',
                'foto_documento_verso',
                'selfie_documento',
            ):
                if files.get(upload_field):
                    setattr(instance, upload_field, files.get(upload_field))
        return instance
