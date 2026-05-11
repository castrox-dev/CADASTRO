from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, Http404
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from .models import Cadastro, AcessoDadoSensivel
from .forms_cadastro import CadastroForm
from .form_config import get_form_config_dict
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.utils.dateparse import parse_date
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import logging
import json

def is_admin(user):
    return user.is_superuser

def _cadastro_for_user(request, pk):
    """Cadastro acessível ao usuário: superuser vê todos, consultor só o próprio."""
    qs = Cadastro.objects.all() if request.user.is_superuser else Cadastro.objects.filter(consultor=request.user)
    return get_object_or_404(qs, pk=pk)


def _client_ip(request):
    """Extrai o IP de origem respeitando proxies (X-Forwarded-For). Para LGPD."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _format_form_error(form):
    """Devolve a 1ª mensagem de erro do form prefixada pelo *label* do campo.

    Sem isso o cliente recebe genérico "Este campo é obrigatório.", sem saber
    qual campo. Mantemos o label original (em maiúsculas como aparece no UI).
    """
    if not form.errors:
        return 'Dados inválidos.'
    field_name, errors = next(iter(form.errors.items()))
    msg = errors[0] if errors else 'Dados inválidos.'
    if field_name == '__all__':
        return msg
    field_obj = form.fields.get(field_name)
    label = field_obj.label if field_obj and field_obj.label else field_name.replace('_', ' ').upper()
    return f'{label}: {msg}'


def _audit_pii(request, cadastro, acao):
    """
    Registra um acesso a dado pessoal (PII) quando o usuário NÃO é o consultor
    dono do cadastro. Consultor abrindo o próprio cadastro NÃO gera log.
    Falhas no log nunca bloqueiam a request.
    """
    try:
        if cadastro.consultor_id == request.user.id:
            return
        AcessoDadoSensivel.objects.create(
            user=request.user if request.user.is_authenticated else None,
            cadastro=cadastro,
            acao=acao,
            ip=_client_ip(request),
        )
    except Exception:
        logger.exception('Falha ao registrar acesso PII')

from .integrations import IXCIntegration
logger = logging.getLogger(__name__)

_IXC_MSG_MAX = 8000
_IXC_LOGS_MAX = 30000


def _truncate_ixc_msg(text, limit=_IXC_MSG_MAX):
    if not text:
        return ''
    return str(text)[:limit]


def _infer_ixc_lead_resource_for_prospect(cadastro, ixc):
    """Recupera o recurso IXC usado na etapa 1 (contato, crm_leads, …) para montar id_contato vs id_lead."""
    d = cadastro.ixc_envio_logs if isinstance(cadastro.ixc_envio_logs, dict) else {}
    r = (d.get('ixc_lead_resource') or '').strip()
    if r:
        return r
    msg = cadastro.ixc_envio_mensagem or ''
    for part in msg.split('|'):
        part = part.strip()
        if part.lower().startswith('recurso='):
            val = part.split('=', 1)[1].strip()
            if val:
                return val
    if ixc._is_demo_ixc_host():
        return 'contato'
    return ''

@login_required
def send_to_ixc(request, pk):
    """
    Integração IXC em etapas (POST):
    - ixc_etapa=lead (padrão): cria lead/contato.
    - ixc_etapa=prospect: cria crm_prospect (requer lead já enviado neste cadastro).
    """
    if request.method != 'POST':
        return JsonResponse(
            {'status': 'error', 'message': 'Use POST.', 'logs': []},
            status=405,
        )
    try:
        cadastro = _cadastro_for_user(request, pk)
    except Http404:
        return JsonResponse(
            {
                'status': 'error',
                'message': 'Cadastro não encontrado ou você não tem permissão para este envio.',
                'logs': ['[ERRO] cadastro inexistente ou fora do seu escopo (evita 404 HTML sem JSON).'],
            },
            status=404,
        )
    logs = [f"[INICIO] envio cadastro_id={cadastro.pk}"]
    etapa = (request.POST.get('ixc_etapa') or 'lead').strip().lower()
    try:
        if etapa == 'prospect':
            return _send_ixc_prospect_body(request, cadastro, logs)
        if etapa != 'lead':
            return JsonResponse(
                {
                    'status': 'error',
                    'message': 'Parâmetro ixc_etapa inválido. Use lead ou prospect.',
                    'logs': logs + [f'[ERRO] ixc_etapa={etapa!r}'],
                },
                status=400,
            )
        return _send_ixc_lead_body(request, cadastro, logs)
    except Exception as e:
        logger.exception("IXC send_to_ixc falhou cadastro=%s", cadastro.pk)
        logs.append(f"[ERRO_INTERNO] {e}")
        return JsonResponse({
            'status': 'error',
            'message': f'Erro interno ao integrar com o IXC: {e}',
            'logs': logs,
        })


def _send_ixc_lead_body(request, cadastro, logs):
    """Etapa 1: apenas lead/contato no IXC (sem criar crm_prospect automaticamente)."""
    ixc = IXCIntegration()
    if cadastro.ixc_lead_id:
        logs.append(f"[DUPLICIDADE] ixc_lead_id local existente={cadastro.ixc_lead_id} (validando no IXC antes de bloquear)")

    duplicate_check = ixc.check_duplicate_before_create(cadastro)
    logs.extend(duplicate_check.get('logs', []))
    if duplicate_check.get('status') == 'duplicate':
        resource = duplicate_check.get('resource')
        found_id = duplicate_check.get('found_id')
        logger.warning("IXC duplicate cadastro=%s logs=%s", cadastro.pk, " | ".join(logs))
        return JsonResponse({
            'status': 'warning',
            'message': f"Duplicidade no IXC: documento já existe em {resource} (ID: {found_id or 'N/A'}).",
            'duplicate': True,
            'logs': logs,
            'ixc_etapa': 'lead',
            'prospect_pendente': False,
        })

    lead_id_local = (cadastro.ixc_lead_id or '').strip()
    if lead_id_local and getattr(settings, 'IXC_REUSE_LOCAL_LEAD_ID', False):
        logs.append(
            f"[CRM_LEAD] reutilizando lead já vinculado id={lead_id_local} "
            "(não cria novo POST no IXC)"
        )
        lead_result = {
            'status': 'success',
            'lead_id': lead_id_local,
            'lead_resource': 'local',
            'message': '',
            'logs': [],
        }
    else:
        lead_result = ixc.create_crm_lead(cadastro)
    logs.extend(lead_result.get('logs', []))

    if lead_result['status'] == 'success':
        crm_lead_id = lead_result.get('lead_id')
        logs.append(f"[CRM_LEAD] id={crm_lead_id}")
        ja_tinha_prospect = bool((cadastro.ixc_prospect_id or '').strip())
        cadastro.ixc_lead_id = str(crm_lead_id) if crm_lead_id else None
        cadastro.ixc_lead_enviado_em = timezone.now()
        cadastro.ixc_envio_status = 'integrado'

        lead_res_name = (lead_result.get('lead_resource') or '').strip()
        log_dict = {'text': _truncate_ixc_msg('\n'.join(logs), _IXC_LOGS_MAX)}
        # Sempre gravar chave (etapa 2 lê para id_contato / id_lead). Cadastros antigos só tinham texto em ixc_envio_mensagem.
        log_dict['ixc_lead_resource'] = lead_res_name or ''

        cadastro.ixc_envio_mensagem = _truncate_ixc_msg(
            ' | '.join(
                p
                for p in (
                    f"recurso={lead_res_name}",
                    f"lead_id={crm_lead_id}",
                    (lead_result.get('message') or '').strip(),
                )
                if p
            )
        )
        cadastro.ixc_envio_logs = log_dict
        cadastro.save(
            update_fields=[
                'ixc_lead_id',
                'ixc_lead_enviado_em',
                'ixc_envio_status',
                'ixc_envio_mensagem',
                'ixc_envio_logs',
            ]
        )
        logs.append(f"[FIM] lead enviado id={crm_lead_id}")
        logger.info("IXC lead success cadastro=%s logs=%s", cadastro.pk, " | ".join(logs))
        prospect_pendente = not ja_tinha_prospect
        return JsonResponse({
            'status': 'success',
            'message': f"Lead criado/enviado ao IXC (ID: {crm_lead_id}). Etapa 1 concluída.",
            'lead_id': crm_lead_id,
            'ixc_etapa': 'lead',
            'prospect_pendente': prospect_pendente,
            'logs': logs,
        })

    logs.append("[FIM] falha no lead")
    logger.error("IXC error cadastro=%s logs=%s", cadastro.pk, " | ".join(logs))
    cadastro.ixc_envio_status = 'erro_ixc'
    cadastro.ixc_envio_mensagem = _truncate_ixc_msg(lead_result.get('message') or '')
    cadastro.ixc_envio_logs = {
        'text': _truncate_ixc_msg('\n'.join(logs), _IXC_LOGS_MAX),
    }
    cadastro.save(update_fields=['ixc_envio_status', 'ixc_envio_mensagem', 'ixc_envio_logs'])
    return JsonResponse({
        'status': 'error',
        'message': lead_result.get('message') or 'Falha ao criar lead no IXC.',
        'logs': logs,
        'ixc_etapa': 'lead',
    })


def _send_ixc_prospect_body(request, cadastro, logs):
    """Etapa 2: apenas crm_prospect (após lead). Exige ixc_lead_id no cadastro."""
    ixc = IXCIntegration()
    logs.append('[IXC] etapa=prospect')

    if (cadastro.ixc_prospect_id or '').strip():
        pid = cadastro.ixc_prospect_id.strip()
        logs.append(f"[CRM_PROSPECT] já existe ixc_prospect_id={pid}")
        return JsonResponse({
            'status': 'warning',
            'message': f'Prospecção já vinculada (ID IXC: {pid}).',
            'prospect_id': pid,
            'ixc_etapa': 'prospect',
            'logs': logs,
        })

    lead_key = (cadastro.ixc_lead_id or '').strip()
    if not lead_key:
        logs.append('[CRM_PROSPECT] ixc_lead_id ausente — faça a etapa 1 (lead) antes.')
        return JsonResponse(
            {
                'status': 'error',
                'message': 'Envie o lead primeiro (etapa 1). Depois use «Criar prospecção IXC».',
                'logs': logs,
                'ixc_etapa': 'prospect',
            },
            status=400,
        )

    lr = _infer_ixc_lead_resource_for_prospect(cadastro, ixc)
    had_res_in_logs = isinstance(cadastro.ixc_envio_logs, dict) and (
        cadastro.ixc_envio_logs.get('ixc_lead_resource') or ''
    ).strip()
    if not had_res_in_logs:
        logs.append(
            f'[CRM_PROSPECT] recurso_etapa1={lr!r} (inferido: mensagem/env ou padrão demo=contato; '
            'reenvie a etapa 1 para gravar ixc_lead_resource no JSON se usar lead fora de contato).'
        )

    prospect_result = ixc.create_crm_prospect(
        cadastro,
        link_contato_id=lead_key,
        ixc_lead_resource=lr,
        force=True,
    )
    logs.extend(prospect_result.get('logs', []))

    if prospect_result.get('status') == 'success':
        pr_id = prospect_result.get('prospect_id')
        cadastro.ixc_prospect_id = str(pr_id) if pr_id is not None else None
        prev = (cadastro.ixc_envio_mensagem or '').strip()
        tail = f"prospect_id={cadastro.ixc_prospect_id}"
        cadastro.ixc_envio_mensagem = _truncate_ixc_msg(' | '.join(p for p in (prev, tail) if p))
        log_block = cadastro.ixc_envio_logs if isinstance(cadastro.ixc_envio_logs, dict) else {}
        log_block = {**log_block, 'text': _truncate_ixc_msg('\n'.join(logs), _IXC_LOGS_MAX)}
        cadastro.ixc_envio_logs = log_block
        cadastro.save(update_fields=['ixc_prospect_id', 'ixc_envio_mensagem', 'ixc_envio_logs'])
        logs.append(f'[FIM] prospecção id={pr_id}')
        logger.info("IXC prospect success cadastro=%s logs=%s", cadastro.pk, " | ".join(logs))
        return JsonResponse({
            'status': 'success',
            'message': f'Prospecção criada no IXC (ID: {pr_id}). Etapa 2 concluída.',
            'prospect_id': pr_id,
            'ixc_etapa': 'prospect',
            'logs': logs,
        })

    if prospect_result.get('status') == 'warning':
        log_block = cadastro.ixc_envio_logs if isinstance(cadastro.ixc_envio_logs, dict) else {}
        log_block = {**log_block, 'text': _truncate_ixc_msg('\n'.join(logs), _IXC_LOGS_MAX)}
        cadastro.ixc_envio_logs = log_block
        cadastro.save(update_fields=['ixc_envio_logs'])
        logger.warning("IXC prospect skipped/warning cadastro=%s logs=%s", cadastro.pk, " | ".join(logs))
        return JsonResponse({
            'status': 'warning',
            'message': prospect_result.get('message') or 'Prospecção não disponível neste ambiente IXC.',
            'ixc_etapa': 'prospect',
            'logs': logs,
        })

    logger.error("IXC prospect error cadastro=%s logs=%s", cadastro.pk, " | ".join(logs))
    prev = (cadastro.ixc_envio_mensagem or '').strip()
    err_msg = prospect_result.get('message') or 'Falha ao criar prospecção no IXC.'
    tail = f"prospect_erro: {err_msg}"
    cadastro.ixc_envio_mensagem = _truncate_ixc_msg(' | '.join(p for p in (prev, tail) if p))
    log_block = cadastro.ixc_envio_logs if isinstance(cadastro.ixc_envio_logs, dict) else {}
    log_block = {**log_block, 'text': _truncate_ixc_msg('\n'.join(logs), _IXC_LOGS_MAX)}
    cadastro.ixc_envio_logs = log_block
    cadastro.save(update_fields=['ixc_envio_mensagem', 'ixc_envio_logs'])
    return JsonResponse({
        'status': 'error',
        'message': err_msg,
        'ixc_etapa': 'prospect',
        'logs': logs,
    })


@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    today = timezone.now().date()
    consultores = User.objects.filter(is_superuser=False).annotate(
        total_cadastros=Count('cadastro'),
        pendentes=Count('cadastro', filter=Q(cadastro__status='pendente')),
        realizados=Count('cadastro', filter=Q(cadastro__status='realizado'))
    )

    # Agrega total_geral + total_hoje numa única query (3.2)
    totais = Cadastro.objects.aggregate(
        total_geral=Count('id'),
        total_hoje=Count('id', filter=Q(data_cadastro__date=today)),
    )

    recent_users = User.objects.order_by('-last_login')[:25]

    return render(request, 'cadastros/admin_dashboard.html', {
        'consultores': consultores,
        'total_geral': totais['total_geral'],
        'total_hoje': totais['total_hoje'],
        'recent_users': recent_users,
    })

@login_required
@user_passes_test(is_admin)
def reports_page(request):
    today = timezone.now().date()
    start_date = today - timedelta(days=6)

    status_data = Cadastro.objects.values('status').annotate(total=Count('status'))

    # 3.2 — agrega os 7 dias numa única query com TruncDate em vez de 7 chamadas.
    daily_counts = (
        Cadastro.objects
        .filter(data_cadastro__date__gte=start_date)
        .annotate(day=TruncDate('data_cadastro'))
        .values('day')
        .annotate(total=Count('id'))
    )
    counts_by_day = {item['day']: item['total'] for item in daily_counts}
    last_7_days = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        last_7_days.append({
            'date': date.strftime('%d/%m'),
            'count': counts_by_day.get(date, 0),
        })

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
    # Preferir consultor vindo do POST (campo oculto); senão ?consultor= na URL (link único)
    consultor = None
    raw_consultor_id = request.POST.get('consultor_id') if request.method == 'POST' else None
    if not raw_consultor_id:
        raw_consultor_id = request.GET.get('consultor')
    if raw_consultor_id:
        try:
            consultor = User.objects.get(pk=int(raw_consultor_id))
        except (User.DoesNotExist, ValueError, TypeError):
            pass

    if request.method == 'POST':
        # LGPD — exige aceite explícito da Política de Privacidade
        consentiu = request.POST.get('consentimento_lgpd') in ('1', 'true', 'on', 'yes')
        if not consentiu:
            return JsonResponse({
                'status': 'error',
                'message': 'É necessário ler e aceitar a Política de Privacidade para concluir o cadastro.'
            }, status=400)

        form = CadastroForm(request.POST, request.FILES)
        if not form.is_valid():
            return JsonResponse(
                {'status': 'error', 'message': _format_form_error(form)},
                status=400,
            )

        cadastro = form.save(commit=False)
        cadastro.consultor = consultor
        cadastro.consentimento_lgpd = True
        cadastro.consentimento_em = timezone.now()
        cadastro.consentimento_ip = _client_ip(request)
        try:
            cadastro.save()
        except ValidationError as e:
            msg = e.messages[0] if hasattr(e, 'messages') else str(e)
            return JsonResponse({'status': 'error', 'message': msg}, status=400)
        except IntegrityError:
            return JsonResponse({
                'status': 'error',
                'message': 'Já existe um cadastro com este CPF/CNPJ.'
            }, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f"Erro inesperado: {str(e)}"}, status=400)

        return JsonResponse({'status': 'success', 'id': cadastro.id})

    try:
        form_config = get_form_config_dict()
    except Exception:
        form_config = None
    return render(request, 'cadastros/form.html', {'consultor': consultor, 'form_config': form_config})

@login_required
def dashboard(request):
    cadastros = (
        Cadastro.objects
        .filter(consultor=request.user)
        .select_related('consultor')
        .order_by('-data_cadastro')
    )
    template = 'cadastros/dashboard_admin.html' if request.user.is_superuser else 'cadastros/dashboard.html'
    return render(request, template, {
        'cadastros': cadastros,
        'status_choices': Cadastro.STATUS_CHOICES,
    })

@login_required
def update_status(request, pk):
    if request.method == 'POST':
        cadastro = _cadastro_for_user(request, pk)
        novo_status = request.POST.get('status')
        valid_statuses = {choice for choice, _ in Cadastro.STATUS_CHOICES}
        if novo_status not in valid_statuses:
            return JsonResponse({'status': 'error', 'message': 'Status inválido.'}, status=400)
        cadastro.status = novo_status
        cadastro.save(update_fields=['status'])
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def update_ficha(request, pk):
    if request.method == 'POST':
        cadastro = _cadastro_for_user(request, pk)
        cadastro.ficha_manual = request.POST.get('ficha_texto')
        cadastro.save(update_fields=['ficha_manual'])
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def cadastro_detail(request, pk):
    cadastro = _cadastro_for_user(request, pk)
    _audit_pii(request, cadastro, 'visualizou')
    template = 'cadastros/detail_admin.html' if request.user.is_superuser else 'cadastros/detail.html'
    return render(request, template, {
        'cadastro': cadastro,
        'status_choices': Cadastro.STATUS_CHOICES,
    })

@login_required
def export_cadastro_json(request, pk):
    cadastro = _cadastro_for_user(request, pk)
    _audit_pii(request, cadastro, 'exportou')
    ixc = IXCIntegration()
    payload = {
        'cadastro_id': cadastro.pk,
        'lead_resources': [ixc.lead_resource_override] if ixc.lead_resource_override else ixc.CRM_LEAD_RESOURCES,
        'lead_payload': ixc.build_crm_lead_payload(cadastro),
        'crm_prospect_resource': getattr(settings, 'IXC_CRM_PROSPECT_RESOURCE', '').strip()
        or 'crm_prospect (+ IXC_CRM_PROSPECT_FALLBACK_RESOURCES se configurado)',
        'crm_prospect_payload': ixc.build_crm_prospect_payload(cadastro, link_contato_id=None),
    }

    response = HttpResponse(
        json.dumps(payload, ensure_ascii=False, indent=2),
        content_type='application/json; charset=utf-8'
    )
    response['Content-Disposition'] = f'attachment; filename="cadastro_{cadastro.pk}.json"'
    return response

@login_required
def edit_cadastro(request, pk):
    cadastro = _cadastro_for_user(request, pk)
    if request.method == 'POST':
        _audit_pii(request, cadastro, 'editou')
        form = CadastroForm(request.POST, request.FILES, instance=cadastro, partial=True)
        if not form.is_valid():
            return JsonResponse(
                {'status': 'error', 'message': _format_form_error(form)},
                status=400,
            )

        form.apply_to(cadastro, files=request.FILES)
        try:
            cadastro.save()
        except ValidationError as e:
            msg = e.messages[0] if hasattr(e, 'messages') else str(e)
            return JsonResponse({'status': 'error', 'message': msg}, status=400)
        except IntegrityError:
            return JsonResponse({
                'status': 'error',
                'message': 'Já existe um cadastro com este CPF/CNPJ.'
            }, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

        return JsonResponse({'status': 'success', 'message': 'Cadastro atualizado com sucesso!'})

    template = 'cadastros/edit_admin.html' if request.user.is_superuser else 'cadastros/edit.html'
    return render(request, template, {'cadastro': cadastro})

@login_required
def delete_cadastro(request, pk):
    if request.method == 'POST':
        cadastro = _cadastro_for_user(request, pk)
        cadastro.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)


@login_required
@user_passes_test(is_admin)
def anonimizar_cadastro(request, pk):
    """
    Anonimização sob demanda (LGPD art. 18). Apenas superusers — pensado para
    atender a pedido formal de exclusão do titular dos dados sem perder os
    indicadores operacionais (status, plano, cidade) já agregados.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método inválido.'}, status=400)

    cadastro = get_object_or_404(Cadastro, pk=pk)
    if cadastro.is_anonimizado:
        return JsonResponse({
            'status': 'warning',
            'message': 'Este cadastro já estava anonimizado.'
        })

    motivo = (request.POST.get('motivo') or '').strip()[:255] or 'Pedido do titular (LGPD art. 18)'
    try:
        cadastro.anonimizar(executado_por=request.user, motivo=motivo)
    except Exception as exc:
        logger.exception('Falha ao anonimizar cadastro %s', pk)
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=500)

    return JsonResponse({
        'status': 'success',
        'message': 'Cadastro anonimizado com sucesso. Os dados pessoais foram removidos.'
    })

@login_required
def standard_scripts(request):
    return render(request, 'cadastros/scripts.html')


@login_required
@user_passes_test(is_admin)
def admin_operacao_hub(request):
    from .operacao_models import CidadeOperacao, FaixaVencimento, PlanoDefinicao, PlanoGrupo, VagaInstalacao

    return render(
        request,
        'cadastros/admin_operacao_hub.html',
        {
            'n_cidades': CidadeOperacao.objects.count(),
            'n_grupos': PlanoGrupo.objects.count(),
            'n_planos': PlanoDefinicao.objects.count(),
            'n_faixas': FaixaVencimento.objects.count(),
            'n_vagas': VagaInstalacao.objects.filter(ativo=True).count(),
        },
    )


def api_form_config(request):
    """JSON público da ficha (planos, vencimentos, cidades). GET apenas."""
    if request.method != 'GET':
        return JsonResponse({'ok': False}, status=405)
    try:
        return JsonResponse(get_form_config_dict())
    except Exception as e:
        logger.exception('api_form_config')
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)