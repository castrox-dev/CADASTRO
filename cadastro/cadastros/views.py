from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from .models import Cadastro
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.utils.dateparse import parse_date

def client_form(request):
    consultor_id = request.GET.get('consultor')
    consultor = None
    if consultor_id:
        try:
            consultor = User.objects.get(id=consultor_id)
        except User.DoesNotExist:
            pass

    if request.method == 'POST':
        # Aqui capturamos os dados do POST manualmente para facilitar com o JS multi-step
        data = request.POST
        files = request.FILES
        
        try:
            cadastro = Cadastro.objects.create(
                tipo_pessoa=data.get('tipoPessoa'),
                documento=data.get('documento'),
                nome_razao=data.get('nome_razao'),
                nome_fantasia=data.get('nome_fantasia'),
                rg=data.get('rg'),
                inscricao_estadual=data.get('inscricao_estadual'),
                data_nascimento=parse_date(data.get('data_nascimento')) if data.get('data_nascimento') else None,
                contrato_social=files.get('contrato_social'),
                email=data.get('email'),
                telefone=data.get('telefone'),
                cep=data.get('cep'),
                cidade=data.get('cidade'),
                bairro=data.get('bairro'),
                endereco=data.get('endereco'),
                referencia=data.get('referencia'),
                plano=data.get('plano'),
                fidelidade=data.get('fidelidade') == 'sim',
                vencimento=data.get('vencimento'),
                vencimento_id=data.get('vencimento_id'),
                opcional=data.get('opcional') == 'sim',
                pagamento_instalacao=data.get('pagamento_instalacao'),
                data_instalacao=parse_date(data.get('data_instalacao')),
                periodo_instalacao=data.get('periodo_instalacao'),
                origem=data.get('origem'),
                consultor=consultor
            )
            return JsonResponse({'status': 'success', 'id': cadastro.id})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return render(request, 'cadastros/form.html', {'consultor': consultor})

@login_required
def dashboard(request):
    cadastros = Cadastro.objects.filter(consultor=request.user).order_by('-data_cadastro')
    return render(request, 'cadastros/dashboard.html', {
        'cadastros': cadastros,
        'status_choices': Cadastro.STATUS_CHOICES
    })

@login_required
def update_status(request, pk):
    if request.method == 'POST':
        cadastro = get_object_or_404(Cadastro, pk=pk, consultor=request.user)
        new_status = request.POST.get('status')
        if new_status in dict(Cadastro.STATUS_CHOICES):
            cadastro.status = new_status
            cadastro.save()
            return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def cadastro_detail(request, pk):
    cadastro = get_object_or_404(Cadastro, pk=pk, consultor=request.user)
    return render(request, 'cadastros/detail.html', {
        'cadastro': cadastro,
        'status_choices': Cadastro.STATUS_CHOICES
    })
