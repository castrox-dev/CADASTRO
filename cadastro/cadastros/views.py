from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from .models import Cadastro
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.utils.dateparse import parse_date
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

def is_admin(user):
    return user.is_superuser

from .integrations import IXCIntegration

@login_required
def send_to_ixc(request, pk):
    """
    Aciona a integração para enviar os dados para o IXC.
    """
    if request.method == 'POST':
        cadastro = get_object_or_404(Cadastro, pk=pk)
        
        # Instancia a integração
        ixc = IXCIntegration()
        result = ixc.create_lead(cadastro)
        
        if result['status'] == 'success':
            # Se desejar, pode salvar o ID do IXC no modelo Cadastro para referência futura
            # cadastro.ixc_id = result['data'].get('id')
            # cadastro.save()
            return JsonResponse({'status': 'success', 'message': 'Cadastro enviado para o IXC com sucesso!'})
        else:
            return JsonResponse({'status': 'error', 'message': result['message']})
            
    return JsonResponse({'status': 'error'}, status=400)

@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    consultores = User.objects.filter(is_superuser=False).annotate(
        total_cadastros=Count('cadastro'),
        pendentes=Count('cadastro', filter=Q(cadastro__status='pendente')),
        realizados=Count('cadastro', filter=Q(cadastro__status='realizado'))
    )
    
    total_geral = Cadastro.objects.count()
    total_hoje = Cadastro.objects.filter(data_cadastro__date=timezone.now().date()).count()
    
    return render(request, 'cadastros/admin_dashboard.html', {
        'consultores': consultores,
        'total_geral': total_geral,
        'total_hoje': total_hoje
    })

@login_required
@user_passes_test(is_admin)
def reports_page(request):
    # ... (existing code)
    status_data = Cadastro.objects.values('status').annotate(total=Count('status'))
    
    # Dados para gráfico de linha (Últimos 7 dias)
    last_7_days = []
    for i in range(6, -1, -1):
        date = timezone.now().date() - timedelta(days=i)
        count = Cadastro.objects.filter(data_cadastro__date=date).count()
        last_7_days.append({
            'date': date.strftime('%d/%m'),
            'count': count
        })

    # Top Planos
    planos_data = Cadastro.objects.values('plano').annotate(total=Count('plano')).order_by('-total')
    
    total_geral = Cadastro.objects.count()
    
    return render(request, 'cadastros/reports.html', {
        'status_labels': [s['status'].upper() for s in status_data],
        'status_values': [s['total'] for s in status_data],
        'days_labels': [d['date'] for d in last_7_days],
        'days_values': [d['count'] for d in last_7_days],
        'planos_data': planos_data,
        'total_geral': total_geral
    })

@login_required
@user_passes_test(is_admin)
def manage_consultor(request, pk=None):
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create':
            username = request.POST.get('username')
            email = request.POST.get('email')
            password = request.POST.get('password')
            first_name = request.POST.get('first_name')
            
            if User.objects.filter(username=username).exists():
                return JsonResponse({'status': 'error', 'message': 'Usuário já existe.'}, status=400)
            
            user = User.objects.create_user(username=username, email=email, password=password, first_name=first_name)
            return JsonResponse({'status': 'success'})
            
        elif action == 'edit' and pk:
            user = get_object_or_404(User, pk=pk)
            user.first_name = request.POST.get('first_name')
            user.email = request.POST.get('email')
            user.save()
            return JsonResponse({'status': 'success'})
            
        elif action == 'delete' and pk:
            user = get_object_or_404(User, pk=pk)
            user.delete()
            return JsonResponse({'status': 'success'})
            
        elif action == 'password' and pk:
            user = get_object_or_404(User, pk=pk)
            user.set_password(request.POST.get('password'))
            user.save()
            return JsonResponse({'status': 'success'})
            
    return JsonResponse({'status': 'error'}, status=400)

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
            cadastro = Cadastro(
                tipo_pessoa=data.get('tipoPessoa'),
                documento=data.get('documento'),
                nome_razao=data.get('nome_razao'),
                nome_fantasia=data.get('nome_fantasia'),
                rg=data.get('rg'),
                inscricao_estadual=data.get('inscricao_estadual'),
                data_nascimento=parse_date(data.get('data_nascimento')) if data.get('data_nascimento') else None,
                contrato_social=files.get('contrato_social'),
                comprovante_residencia=files.get('comprovante_residencia'),
                foto_documento_frente=files.get('foto_documento_frente'),
                foto_documento_verso=files.get('foto_documento_verso'),
                selfie_documento=files.get('selfie_documento'),
                levar_termo=data.get('levar_termo') == 'on',
                email=data.get('email'),
                telefone=data.get('telefone'),
                cep=data.get('cep'),
                cidade=data.get('cidade'),
                bairro=data.get('bairro'),
                endereco=data.get('endereco'),
                referencia=data.get('referencia'),
                google_maps_link=data.get('google_maps_link'),
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
            # O save() agora chama full_clean() que valida CPF/CNPJ e Duplicidade
            cadastro.save()
            return JsonResponse({'status': 'success', 'id': cadastro.id})
        except ValidationError as e:
            # Pega a mensagem de erro amigável (do validador ou da duplicidade)
            msg = e.messages[0] if hasattr(e, 'messages') else str(e)
            return JsonResponse({'status': 'error', 'message': msg}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f"Erro inesperado: {str(e)}"}, status=400)

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
        cadastro.status = request.POST.get('status')
        cadastro.save()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def update_ficha(request, pk):
    if request.method == 'POST':
        cadastro = get_object_or_404(Cadastro, pk=pk, consultor=request.user)
        cadastro.ficha_manual = request.POST.get('ficha_texto')
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

@login_required
def edit_cadastro(request, pk):
    cadastro = get_object_or_404(Cadastro, pk=pk, consultor=request.user)
    if request.method == 'POST':
        # Lógica de atualização simplificada para exemplo, pode-se usar um Form
        data = request.POST
        files = request.FILES
        
        try:
            cadastro.tipo_pessoa = data.get('tipoPessoa')
            cadastro.documento = data.get('documento')
            cadastro.nome_razao = data.get('nome_razao')
            cadastro.nome_fantasia = data.get('nome_fantasia')
            cadastro.rg = data.get('rg')
            cadastro.inscricao_estadual = data.get('inscricao_estadual')
            if data.get('data_nascimento'):
                cadastro.data_nascimento = parse_date(data.get('data_nascimento'))
            
            if files.get('contrato_social'): cadastro.contrato_social = files.get('contrato_social')
            if files.get('comprovante_residencia'): cadastro.comprovante_residencia = files.get('comprovante_residencia')
            if files.get('foto_documento_frente'): cadastro.foto_documento_frente = files.get('foto_documento_frente')
            if files.get('foto_documento_verso'): cadastro.foto_documento_verso = files.get('foto_documento_verso')
            if files.get('selfie_documento'): cadastro.selfie_documento = files.get('selfie_documento')
            
            cadastro.levar_termo = data.get('levar_termo') == 'on'
            cadastro.email = data.get('email')
            cadastro.telefone = data.get('telefone')
            cadastro.cep = data.get('cep')
            cadastro.cidade = data.get('cidade')
            cadastro.bairro = data.get('bairro')
            cadastro.endereco = data.get('endereco')
            cadastro.referencia = data.get('referencia')
            cadastro.google_maps_link = data.get('google_maps_link')
            cadastro.plano = data.get('plano')
            cadastro.fidelidade = data.get('fidelidade') == 'sim'
            cadastro.vencimento = data.get('vencimento')
            cadastro.vencimento_id = data.get('vencimento_id')
            cadastro.opcional = data.get('opcional') == 'sim'
            cadastro.pagamento_instalacao = data.get('pagamento_instalacao')
            if data.get('data_instalacao'):
                cadastro.data_instalacao = parse_date(data.get('data_instalacao'))
            cadastro.periodo_instalacao = data.get('periodo_instalacao')
            cadastro.origem = data.get('origem')
            
            cadastro.save()
            return JsonResponse({'status': 'success', 'message': 'Cadastro atualizado com sucesso!'})
        except ValidationError as e:
            msg = e.messages[0] if hasattr(e, 'messages') else str(e)
            return JsonResponse({'status': 'error', 'message': msg}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return render(request, 'cadastros/edit.html', {'cadastro': cadastro})

@login_required
def delete_cadastro(request, pk):
    if request.method == 'POST':
        cadastro = get_object_or_404(Cadastro, pk=pk, consultor=request.user)
        cadastro.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def standard_scripts(request):
    return render(request, 'cadastros/scripts.html')
