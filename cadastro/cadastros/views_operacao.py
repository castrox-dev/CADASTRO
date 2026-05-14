"""
Telas internas do painel para configurar ficha / IXC (superusuários apenas).
"""
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms_operacao import (
    AppConfigOperacaoForm,
    CidadeOperacaoForm,
    FaixaVencimentoForm,
    OpcaoVencimentoFormSet,
    PlanoDefinicaoFormSet,
    PlanoGrupoForm,
    VagaInstalacaoForm,
    VendedorIXCForm,
)
from .operacao_models import (
    AppConfigOperacao,
    CidadeOperacao,
    FaixaVencimento,
    OpcaoVencimento,
    PlanoGrupo,
    VagaInstalacao,
    VendedorIXC,
)


def is_admin(user):
    return user.is_superuser


def _operacao_ctx():
    from .operacao_models import PlanoDefinicao

    return {
        'n_cidades': CidadeOperacao.objects.count(),
        'n_grupos': PlanoGrupo.objects.count(),
        'n_planos': PlanoDefinicao.objects.count(),
        'n_faixas': FaixaVencimento.objects.count(),
        'n_vagas': VagaInstalacao.objects.filter(ativo=True).count(),
        'n_vendedores': VendedorIXC.objects.filter(ativo=True).count(),
    }


@login_required
@user_passes_test(is_admin)
def operacao_config(request):
    obj = AppConfigOperacao.load()
    if request.method == 'POST':
        form = AppConfigOperacaoForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Configuração geral salva.')
            return redirect('operacao_config')
    else:
        form = AppConfigOperacaoForm(instance=obj)
    ctx = _operacao_ctx()
    ctx['form'] = form
    ctx['page_title'] = 'Configuração geral da ficha'
    return render(request, 'cadastros/operacao/config.html', ctx)


@login_required
@user_passes_test(is_admin)
def operacao_cidades_list(request):
    cidades = CidadeOperacao.objects.select_related('grupo_planos').order_by('ordem', 'nome_exibicao')
    ctx = _operacao_ctx()
    ctx['cidades'] = cidades
    ctx['page_title'] = 'Cidades e filiais'
    return render(request, 'cadastros/operacao/cidades_list.html', ctx)


@login_required
@user_passes_test(is_admin)
@require_http_methods(['GET', 'POST'])
def operacao_cidade_create(request):
    if request.method == 'POST':
        form = CidadeOperacaoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cidade criada.')
            return redirect('operacao_cidades_list')
    else:
        form = CidadeOperacaoForm()
    ctx = _operacao_ctx()
    ctx['form'] = form
    ctx['page_title'] = 'Nova cidade'
    return render(request, 'cadastros/operacao/cidade_form.html', ctx)


@login_required
@user_passes_test(is_admin)
@require_http_methods(['GET', 'POST'])
def operacao_cidade_edit(request, pk):
    cidade = get_object_or_404(CidadeOperacao, pk=pk)
    if request.method == 'POST':
        form = CidadeOperacaoForm(request.POST, instance=cidade)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cidade atualizada.')
            return redirect('operacao_cidades_list')
    else:
        form = CidadeOperacaoForm(instance=cidade)
    ctx = _operacao_ctx()
    ctx['form'] = form
    ctx['cidade'] = cidade
    ctx['page_title'] = f'Editar: {cidade.nome_exibicao}'
    return render(request, 'cadastros/operacao/cidade_form.html', ctx)


@login_required
@user_passes_test(is_admin)
@require_POST
def operacao_cidade_delete(request, pk):
    cidade = get_object_or_404(CidadeOperacao, pk=pk)
    nome = cidade.nome_exibicao
    cidade.delete()
    messages.success(request, f'«{nome}» removida.')
    return redirect('operacao_cidades_list')


@login_required
@user_passes_test(is_admin)
def operacao_cidade_vencimentos(request, pk):
    cidade = get_object_or_404(CidadeOperacao, pk=pk)
    faixas = cidade.faixas_vencimento.prefetch_related('opcoes').order_by('ordem', 'dia_inicio')
    add_form = FaixaVencimentoForm(initial={'ordem': faixas.count()})

    if request.method == 'POST':
        add_form = FaixaVencimentoForm(request.POST)
        if add_form.is_valid():
            fx = add_form.save(commit=False)
            fx.cidade = cidade
            try:
                fx.full_clean()
                fx.save()
                messages.success(request, 'Faixa adicionada.')
                return redirect('operacao_cidade_vencimentos', pk=cidade.pk)
            except ValidationError as e:
                msgs = getattr(e, 'messages', None) or [str(e)]
                messages.error(request, msgs[0] if msgs else str(e))
        else:
            messages.error(request, 'Corrija os dados da faixa.')

    ctx = _operacao_ctx()
    ctx['cidade'] = cidade
    ctx['faixas'] = faixas
    ctx['form'] = add_form
    ctx['page_title'] = f'Vencimentos — {cidade.nome_exibicao}'
    return render(request, 'cadastros/operacao/cidade_vencimentos.html', ctx)


@login_required
@user_passes_test(is_admin)
@require_POST
def operacao_faixa_delete(request, pk):
    faixa = get_object_or_404(FaixaVencimento, pk=pk)
    cid = faixa.cidade_id
    faixa.delete()
    messages.success(request, 'Faixa removida.')
    return redirect('operacao_cidade_vencimentos', pk=cid)


@login_required
@user_passes_test(is_admin)
@require_http_methods(['GET', 'POST'])
def operacao_faixa_opcoes(request, faixa_pk):
    faixa = get_object_or_404(FaixaVencimento.objects.select_related('cidade'), pk=faixa_pk)

    if request.method == 'POST':
        formset = OpcaoVencimentoFormSet(request.POST, instance=faixa)
        if formset.is_valid():
            formset.save()
            messages.success(request, 'Opções de vencimento salvas.')
            return redirect('operacao_faixa_opcoes', faixa_pk=faixa.pk)
    else:
        formset = OpcaoVencimentoFormSet(instance=faixa)

    ctx = _operacao_ctx()
    ctx['faixa'] = faixa
    ctx['cidade'] = faixa.cidade
    ctx['formset'] = formset
    ctx['page_title'] = f'Opções — dias {faixa.dia_inicio}–{faixa.dia_fim}'
    return render(request, 'cadastros/operacao/faixa_opcoes.html', ctx)


@login_required
@user_passes_test(is_admin)
def operacao_grupos_list(request):
    grupos = PlanoGrupo.objects.prefetch_related('planos').order_by('slug')
    ctx = _operacao_ctx()
    ctx['grupos'] = grupos
    ctx['page_title'] = 'Grupos de planos'
    return render(request, 'cadastros/operacao/grupos_list.html', ctx)


@login_required
@user_passes_test(is_admin)
@require_http_methods(['GET', 'POST'])
def operacao_grupo_create(request):
    if request.method == 'POST':
        form = PlanoGrupoForm(request.POST)
        if form.is_valid():
            g = form.save()
            messages.success(request, 'Grupo criado. Adicione os planos abaixo.')
            return redirect('operacao_grupo_edit', pk=g.pk)
    else:
        form = PlanoGrupoForm()
    ctx = _operacao_ctx()
    ctx['form'] = form
    ctx['page_title'] = 'Novo grupo de planos'
    return render(request, 'cadastros/operacao/grupo_create.html', ctx)


@login_required
@user_passes_test(is_admin)
@require_http_methods(['GET', 'POST'])
def operacao_grupo_edit(request, pk):
    grupo = get_object_or_404(PlanoGrupo, pk=pk)
    if request.method == 'POST':
        form = PlanoGrupoForm(request.POST, instance=grupo)
        formset = PlanoDefinicaoFormSet(request.POST, instance=grupo)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, 'Grupo e planos salvos.')
            return redirect('operacao_grupo_edit', pk=grupo.pk)
    else:
        form = PlanoGrupoForm(instance=grupo)
        formset = PlanoDefinicaoFormSet(instance=grupo)
    ctx = _operacao_ctx()
    ctx['grupo'] = grupo
    ctx['form'] = form
    ctx['formset'] = formset
    ctx['page_title'] = f'Planos — {grupo.nome}'
    return render(request, 'cadastros/operacao/grupo_edit.html', ctx)


@login_required
@user_passes_test(is_admin)
@require_POST
def operacao_grupo_delete(request, pk):
    grupo = get_object_or_404(PlanoGrupo, pk=pk)
    nome = grupo.nome
    try:
        grupo.delete()
        messages.success(request, f'Grupo «{nome}» removido.')
    except ProtectedError:
        messages.error(
            request,
            'Não é possível excluir: existem cidades usando este grupo. Altere as cidades primeiro.',
        )
    return redirect('operacao_grupos_list')


@login_required
@user_passes_test(is_admin)
def operacao_vagas_list(request):
    vagas = VagaInstalacao.objects.order_by('-data', 'periodo')
    ctx = _operacao_ctx()
    ctx['vagas'] = vagas
    ctx['page_title'] = 'Vagas de instalação'
    return render(request, 'cadastros/operacao/vagas_list.html', ctx)


@login_required
@user_passes_test(is_admin)
@require_http_methods(['GET', 'POST'])
def operacao_vaga_create(request):
    if request.method == 'POST':
        form = VagaInstalacaoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Registro de vagas criado.')
            return redirect('operacao_vagas_list')
    else:
        form = VagaInstalacaoForm()
    ctx = _operacao_ctx()
    ctx['form'] = form
    ctx['page_title'] = 'Nova vaga'
    return render(request, 'cadastros/operacao/vaga_form.html', ctx)


@login_required
@user_passes_test(is_admin)
@require_http_methods(['GET', 'POST'])
def operacao_vaga_edit(request, pk):
    vaga = get_object_or_404(VagaInstalacao, pk=pk)
    if request.method == 'POST':
        form = VagaInstalacaoForm(request.POST, instance=vaga)
        if form.is_valid():
            form.save()
            messages.success(request, 'Vagas atualizadas.')
            return redirect('operacao_vagas_list')
    else:
        form = VagaInstalacaoForm(instance=vaga)
    ctx = _operacao_ctx()
    ctx['form'] = form
    ctx['vaga'] = vaga
    ctx['page_title'] = 'Editar vagas'
    return render(request, 'cadastros/operacao/vaga_form.html', ctx)


@login_required
@user_passes_test(is_admin)
@require_POST
def operacao_vaga_delete(request, pk):
    vaga = get_object_or_404(VagaInstalacao, pk=pk)
    vaga.delete()
    messages.success(request, 'Registro removido.')
    return redirect('operacao_vagas_list')


# ----------------------------------------------------------------------------- #
# VendedorIXC — cadastro dos vendedores/responsáveis usados na integração IXC. #
# O `ixc_id` é enviado em id_vendedor / id_responsavel / id_vendedor_ativ.     #
# ----------------------------------------------------------------------------- #
@login_required
@user_passes_test(is_admin)
def operacao_vendedores_list(request):
    vendedores = VendedorIXC.objects.all().order_by('ordem', 'nome')
    ctx = _operacao_ctx()
    ctx['vendedores'] = vendedores
    ctx['page_title'] = 'Vendedores / responsáveis (IXC)'
    return render(request, 'cadastros/operacao/vendedores_list.html', ctx)


@login_required
@user_passes_test(is_admin)
@require_http_methods(['GET', 'POST'])
def operacao_vendedor_create(request):
    if request.method == 'POST':
        form = VendedorIXCForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Vendedor cadastrado.')
            return redirect('operacao_vendedores_list')
    else:
        form = VendedorIXCForm(initial={'ordem': VendedorIXC.objects.count()})
    ctx = _operacao_ctx()
    ctx['form'] = form
    ctx['page_title'] = 'Novo vendedor / responsável'
    return render(request, 'cadastros/operacao/vendedor_form.html', ctx)


@login_required
@user_passes_test(is_admin)
@require_http_methods(['GET', 'POST'])
def operacao_vendedor_edit(request, pk):
    vendedor = get_object_or_404(VendedorIXC, pk=pk)
    if request.method == 'POST':
        form = VendedorIXCForm(request.POST, instance=vendedor)
        if form.is_valid():
            form.save()
            messages.success(request, 'Vendedor atualizado.')
            return redirect('operacao_vendedores_list')
    else:
        form = VendedorIXCForm(instance=vendedor)
    ctx = _operacao_ctx()
    ctx['form'] = form
    ctx['vendedor'] = vendedor
    ctx['page_title'] = f'Editar: {vendedor.nome}'
    return render(request, 'cadastros/operacao/vendedor_form.html', ctx)


@login_required
@user_passes_test(is_admin)
@require_POST
def operacao_vendedor_delete(request, pk):
    vendedor = get_object_or_404(VendedorIXC, pk=pk)
    n_cadastros = vendedor.cadastros.count()
    nome = vendedor.nome
    if n_cadastros:
        # Mantém a referência «solta» nos cadastros (SET_NULL).
        messages.warning(
            request,
            f'«{nome}» removido. {n_cadastros} cadastro(s) ficou(ram) sem vendedor — '
            'edite cada um para escolher outro responsável.',
        )
    else:
        messages.success(request, f'«{nome}» removido.')
    vendedor.delete()
    return redirect('operacao_vendedores_list')
