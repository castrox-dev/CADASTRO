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


def _ixc_url_is_demo_public():
    """True se IXC_API_URL aponta para o demo público (webservices crm_* costumam não existir)."""
    return 'demo.ixcsoft.com.br' in (getattr(settings, 'IXC_API_URL', '') or '').lower()


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
    if getattr(settings, 'IXC_LEAD_CONTATO_ONLY', True):
        return 'contato'
    return ''


def _chain_ixc_candidatos_after_lead(ixc, cadastro, logs, crm_lead_id, lead_res_name):
    """Após lead com sucesso: POST ``crm_candidatos``. Retorna (id ou None, status: success|error|skipped)."""
    if not getattr(settings, 'IXC_CHAIN_CRM_CANDIDATOS_AFTER_LEAD', True):
        logs.append('[CRM_CANDIDATOS] encadeamento desativado (IXC_CHAIN_CRM_CANDIDATOS_AFTER_LEAD=False).')
        return None, 'skipped'
    if (cadastro.ixc_candidato_id or '').strip():
        cid = cadastro.ixc_candidato_id.strip()
        logs.append(f'[CRM_CANDIDATOS] já existe ixc_candidato_id={cid}')
        return cid, 'skipped'
    cr = (lead_res_name or '').strip() or None
    r = ixc.create_crm_candidatos(
        cadastro,
        link_contato_id=crm_lead_id,
        ixc_lead_resource=cr,
        force=True,
    )
    logs.extend(r.get('logs', []))
    if r.get('status') == 'success':
        cid = r.get('candidato_id')
        logs.append(f'[FIM] crm_candidatos id={cid}')
        return cid, 'success'
    logs.append('[FIM] crm_candidatos falhou (lead já integrado — ver log acima).')
    return None, 'error'


@login_required
def send_to_ixc(request, pk):
    """
    Integração IXC em etapas (POST):
    - ixc_etapa=lead (padrão): cria lead/contato e, por padrão, ``crm_candidatos`` encadeado.
    - ixc_etapa=candidatos: apenas ``crm_candidatos`` (exige lead já enviado).
    - ixc_etapa=prospect: cria crm_prospect (requer lead já enviado neste cadastro).
    - ixc_etapa=completo: cria lead se faltar; em seguida prospecção se ainda não houver ``ixc_prospect_id``.
    - ixc_etapa=limpar: apaga só no Django os IDs/auditoria IXC já gravados (não altera o IXC).
      Corpo: ``ixc_limpar_escopo=prospecto`` (só ``ixc_prospect_id``) ou ``tudo`` (lead, prospect,
      contrato, logs locais). Útil para rodar de novo «completo» / prospecção após vínculo antigo.
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
        if etapa == 'limpar':
            return _limpar_vinculo_ixc_local(request, cadastro, logs)
        if etapa == 'completo':
            return _send_ixc_completo(request, cadastro, logs)
        if etapa == 'prospect':
            return _send_ixc_prospect_body(request, cadastro, logs)
        if etapa == 'candidatos':
            return _send_ixc_candidatos_body(request, cadastro, logs)
        if etapa != 'lead':
            return JsonResponse(
                {
                    'status': 'error',
                    'message': (
                        'Parâmetro ixc_etapa inválido. Use lead, candidatos, prospect, completo ou limpar.'
                    ),
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


def _limpar_vinculo_ixc_local(request, cadastro, logs):
    """Remove IDs e auditoria IXC gravados só neste cadastro (não chama API IXC)."""
    escopo = (request.POST.get('ixc_limpar_escopo') or 'prospecto').strip().lower()
    if escopo not in ('prospecto', 'tudo'):
        return JsonResponse(
            {
                'status': 'error',
                'message': 'ixc_limpar_escopo inválido. Use prospecto ou tudo.',
                'logs': logs + [f'[ERRO] ixc_limpar_escopo={escopo!r}'],
                'ixc_etapa': 'limpar',
            },
            status=400,
        )
    logs.append(f'[LIMPAR] escopo={escopo} (apenas banco local; registros no IXC não são apagados)')
    cleared = []

    if escopo == 'prospecto':
        had = bool((cadastro.ixc_prospect_id or '').strip())
        if had:
            cleared.append('ixc_prospect_id')
        cadastro.ixc_prospect_id = None
        cadastro.save(update_fields=['ixc_prospect_id'])
        msg = (
            'Vínculo da prospecção removido neste sistema. Pode usar «Enviar para IXC» de novo para criar outra prospecção (o lead local permanece).'
            if had
            else 'Não havia prospecção vinculada localmente; nada foi alterado.'
        )
        logs.append(f'[LIMPAR] concluído cleared={cleared or ["(nada)"]}')
        logger.info("IXC limpar local cadastro=%s escopo=prospecto had=%s", cadastro.pk, had)
        return JsonResponse(
            {
                'status': 'success',
                'message': msg,
                'logs': logs,
                'ixc_etapa': 'limpar',
                'ixc_limpar_escopo': escopo,
                'cleared': cleared,
            }
        )

    # escopo == 'tudo'
    for attr in (
        'ixc_lead_id',
        'ixc_prospect_id',
        'ixc_contrato_id',
    ):
        if getattr(cadastro, attr):
            cleared.append(attr)
    cadastro.ixc_lead_id = None
    cadastro.ixc_lead_enviado_em = None
    cadastro.ixc_prospect_id = None
    cadastro.ixc_contrato_id = None
    cadastro.ixc_envio_status = 'pendente'
    cadastro.ixc_envio_mensagem = ''
    cadastro.ixc_envio_logs = {}
    cadastro.save(
        update_fields=[
            'ixc_lead_id',
            'ixc_lead_enviado_em',
            'ixc_prospect_id',
            'ixc_contrato_id',
            'ixc_envio_status',
            'ixc_envio_mensagem',
            'ixc_envio_logs',
        ]
    )
    logs.append(f'[LIMPAR] concluído escopo=tudo cleared={cleared or ["(ids já vazios)"]} + auditoria IXC')
    logger.info("IXC limpar local cadastro=%s escopo=tudo cleared=%s", cadastro.pk, cleared)
    return JsonResponse(
        {
            'status': 'success',
            'message': 'Todo vínculo IXC local foi removido (lead, prospecção, contrato e logs). O IXC não foi alterado; o próximo envio tentará criar registros novamente.',
            'logs': logs,
            'ixc_etapa': 'limpar',
            'ixc_limpar_escopo': escopo,
            'cleared': cleared + ['ixc_envio_*'],
        }
    )


def _send_ixc_completo(request, cadastro, logs):
    """Cria lead se necessário e, na mesma requisição, prospecção se ainda não houver ID local."""
    logs.append('[IXC] etapa=completo')
    if not (cadastro.ixc_lead_id or '').strip():
        lead_resp = _send_ixc_lead_body(request, cadastro, logs)
        if lead_resp.status_code != 200:
            return lead_resp
        try:
            data = json.loads(lead_resp.content.decode('utf-8'))
        except (ValueError, UnicodeDecodeError, AttributeError):
            return lead_resp
        if data.get('status') == 'error':
            return lead_resp
        cadastro.refresh_from_db()
    if not (cadastro.ixc_prospect_id or '').strip():
        logs.append('[IXC] completo: encadeando prospecção...')
        return _send_ixc_prospect_body(request, cadastro, logs)
    return JsonResponse(
        {
            'status': 'success',
            'message': 'Nada pendente: lead e prospecção já vinculados a esta ficha.',
            'ixc_etapa': 'completo',
            'logs': logs + ['[IXC] completo: sem etapas pendentes (prospecção já local).'],
        }
    )


def _send_ixc_lead_body(request, cadastro, logs):
    """Etapa 1: lead/contato no IXC e, se configurado, encadeia ``crm_candidatos`` (não cria crm_prospect aqui)."""
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
        cand_id, cand_status = _chain_ixc_candidatos_after_lead(ixc, cadastro, logs, crm_lead_id, lead_res_name)
        if cand_id and cand_status == 'success':
            cadastro.ixc_candidato_id = str(cand_id)

        log_dict = {'text': _truncate_ixc_msg('\n'.join(logs), _IXC_LOGS_MAX)}
        # Sempre gravar chave (etapa 2 lê para id_contato / id_lead). Cadastros antigos só tinham texto em ixc_envio_mensagem.
        log_dict['ixc_lead_resource'] = lead_res_name or ''
        if cand_id and cand_status == 'success':
            log_dict['ixc_candidato_id'] = str(cand_id)

        msg_tail_cand = ''
        if cand_status == 'success' and cand_id:
            msg_tail_cand = f"candidato_id={cand_id}"
        elif cand_status == 'error':
            msg_tail_cand = 'candidato=erro'

        cadastro.ixc_envio_mensagem = _truncate_ixc_msg(
            ' | '.join(
                p
                for p in (
                    f"recurso={lead_res_name}",
                    f"lead_id={crm_lead_id}",
                    msg_tail_cand,
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
                'ixc_candidato_id',
            ]
        )
        logs.append(f"[FIM] lead enviado id={crm_lead_id}")
        logger.info("IXC lead success cadastro=%s logs=%s", cadastro.pk, " | ".join(logs))
        prospect_pendente = not ja_tinha_prospect
        msg_parts = [f"Lead IXC (ID: {crm_lead_id})"]
        if cand_status == 'success' and cand_id:
            msg_parts.append(f"CRM candidatos (ID: {cand_id})")
        elif cand_status == 'error':
            msg_parts.append('CRM candidatos: falhou (ver log)')
        elif cand_status == 'skipped' and cand_id:
            msg_parts.append(f"CRM candidatos já vinculado (ID: {cand_id}).")
        return JsonResponse({
            'status': 'success',
            'message': '. '.join(msg_parts) + '.',
            'lead_id': crm_lead_id,
            'candidato_id': str(cand_id) if cand_id else None,
            'candidato_status': cand_status,
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


def _send_ixc_candidatos_body(request, cadastro, logs):
    """Apenas crm_candidatos no IXC. Exige ixc_lead_id (etapa 1) e que ainda não exista ixc_candidato_id local."""
    ixc = IXCIntegration()
    logs.append('[IXC] etapa=candidatos')

    if (cadastro.ixc_candidato_id or '').strip():
        cid = cadastro.ixc_candidato_id.strip()
        logs.append(f"[CRM_CANDIDATOS] já existe ixc_candidato_id={cid}")
        return JsonResponse({
            'status': 'warning',
            'message': f'CRM candidatos já vinculado (ID IXC: {cid}).',
            'candidato_id': cid,
            'ixc_etapa': 'candidatos',
            'logs': logs,
        })

    lead_key = (cadastro.ixc_lead_id or '').strip()
    if not lead_key:
        logs.append('[CRM_CANDIDATOS] ixc_lead_id ausente — faça a etapa 1 (lead) antes.')
        return JsonResponse(
            {
                'status': 'error',
                'message': 'Envie o lead primeiro (etapa 1). Depois use «CRM candidatos (somente IXC)».',
                'logs': logs,
                'ixc_etapa': 'candidatos',
            },
            status=400,
        )

    lr = _infer_ixc_lead_resource_for_prospect(cadastro, ixc)
    had_res_in_logs = isinstance(cadastro.ixc_envio_logs, dict) and (
        cadastro.ixc_envio_logs.get('ixc_lead_resource') or ''
    ).strip()
    if not had_res_in_logs:
        logs.append(
            f'[CRM_CANDIDATOS] recurso_etapa1={lr!r} (inferido; reenvie a etapa 1 para gravar '
            'ixc_lead_resource no JSON se o lead não for contato).'
        )

    cand_result = ixc.create_crm_candidatos(
        cadastro,
        link_contato_id=lead_key,
        ixc_lead_resource=lr,
        force=True,
    )
    logs.extend(cand_result.get('logs', []))

    if cand_result.get('status') == 'success':
        c_id = cand_result.get('candidato_id')
        cadastro.ixc_candidato_id = str(c_id) if c_id is not None else None
        prev = (cadastro.ixc_envio_mensagem or '').strip()
        tail = f"candidato_id={cadastro.ixc_candidato_id}"
        cadastro.ixc_envio_mensagem = _truncate_ixc_msg(' | '.join(p for p in (prev, tail) if p))
        log_block = cadastro.ixc_envio_logs if isinstance(cadastro.ixc_envio_logs, dict) else {}
        log_block = {**log_block, 'text': _truncate_ixc_msg('\n'.join(logs), _IXC_LOGS_MAX)}
        if cadastro.ixc_candidato_id:
            log_block['ixc_candidato_id'] = cadastro.ixc_candidato_id
        cadastro.ixc_envio_logs = log_block
        cadastro.save(update_fields=['ixc_candidato_id', 'ixc_envio_mensagem', 'ixc_envio_logs'])
        logs.append(f'[FIM] crm_candidatos id={c_id}')
        logger.info("IXC candidatos success cadastro=%s logs=%s", cadastro.pk, " | ".join(logs))
        return JsonResponse({
            'status': 'success',
            'message': f'CRM candidatos criado no IXC (ID: {c_id}).',
            'candidato_id': c_id,
            'candidato_status': 'success',
            'ixc_etapa': 'candidatos',
            'logs': logs,
        })

    if cand_result.get('status') == 'skipped':
        log_block = cadastro.ixc_envio_logs if isinstance(cadastro.ixc_envio_logs, dict) else {}
        log_block = {**log_block, 'text': _truncate_ixc_msg('\n'.join(logs), _IXC_LOGS_MAX)}
        cadastro.ixc_envio_logs = log_block
        cadastro.save(update_fields=['ixc_envio_logs'])
        logger.warning("IXC candidatos skipped cadastro=%s logs=%s", cadastro.pk, " | ".join(logs))
        return JsonResponse({
            'status': 'warning',
            'message': cand_result.get('message') or 'CRM candidatos não enviado (configuração).',
            'ixc_etapa': 'candidatos',
            'logs': logs,
        })

    if cand_result.get('status') == 'error':
        err_msg = cand_result.get('message') or ''
        em = err_msg.lower()
        if ixc._is_demo_ixc_host() and (
            'não está disponível' in em
            or 'nao esta disponivel' in em
            or ('recurso' in em and 'dispon' in em)
        ):
            log_block = cadastro.ixc_envio_logs if isinstance(cadastro.ixc_envio_logs, dict) else {}
            log_block = {**log_block, 'text': _truncate_ixc_msg('\n'.join(logs), _IXC_LOGS_MAX)}
            cadastro.ixc_envio_logs = log_block
            cadastro.save(update_fields=['ixc_envio_logs'])
            logger.info("IXC candidatos indisponível no demo cadastro=%s", cadastro.pk)
            return JsonResponse({
                'status': 'warning',
                'message': (
                    'IXC demo: os webservices ``crm_canditados`` / ``crm_candidatos`` não existem nesta base pública. '
                    'No IXC do seu provedor, configure IXC_API_URL / token e o nome do recurso no Postman '
                    '(IXC_CRM_CANDIDATOS_RESOURCE ou IXC_CRM_CANDIDATOS_FALLBACK_RESOURCES).'
                ),
                'ixc_etapa': 'candidatos',
                'logs': logs,
                'candidato_status': 'skipped_demo',
            })

    logger.error("IXC candidatos error cadastro=%s logs=%s", cadastro.pk, " | ".join(logs))
    prev = (cadastro.ixc_envio_mensagem or '').strip()
    err_msg = cand_result.get('message') or 'Falha ao criar CRM candidatos no IXC.'
    tail = f"candidato_erro: {err_msg}"
    cadastro.ixc_envio_mensagem = _truncate_ixc_msg(' | '.join(p for p in (prev, tail) if p))
    log_block = cadastro.ixc_envio_logs if isinstance(cadastro.ixc_envio_logs, dict) else {}
    log_block = {**log_block, 'text': _truncate_ixc_msg('\n'.join(logs), _IXC_LOGS_MAX)}
    cadastro.ixc_envio_logs = log_block
    cadastro.save(update_fields=['ixc_envio_mensagem', 'ixc_envio_logs'])
    return JsonResponse({
        'status': 'error',
        'message': err_msg,
        'ixc_etapa': 'candidatos',
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
        'ixc_demo_host': _ixc_url_is_demo_public(),
    })

@login_required
def export_cadastro_json(request, pk):
    cadastro = _cadastro_for_user(request, pk)
    _audit_pii(request, cadastro, 'exportou')
    ixc = IXCIntegration()
    lead_id = (cadastro.ixc_lead_id or '').strip()
    lr = _infer_ixc_lead_resource_for_prospect(cadastro, ixc) if lead_id else ''
    log_dict = cadastro.ixc_envio_logs if isinstance(cadastro.ixc_envio_logs, dict) else {}
    prospect_etapa2 = None
    if lead_id:
        prospect_etapa2 = ixc.build_crm_prospect_payload(
            cadastro,
            link_contato_id=lead_id,
            ixc_lead_resource=lr,
        )
    rad_pppoe = {'login': ixc.build_pppoe_login_for_cadastro(cadastro)}
    try:
        pl_rad, err_rad, logs_rad = ixc.build_radusuarios_pppoe_payload(cadastro)
        rad_pppoe['montagem_erro'] = err_rad
        if pl_rad is not None and not err_rad:
            prev = dict(pl_rad)
            sd = str(prev.get('senha', '') or '')
            if sd:
                prev['senha'] = f'*** ({len(sd)} dígitos — mesmo valor de documento_digits)'
            rad_pppoe['payload_radusuarios_montado'] = prev
        rad_pppoe['montagem_logs'] = list(logs_rad or [])[:150]
    except Exception as ex:
        rad_pppoe['montagem_excecao'] = str(ex)

    payload = {
        'cadastro_id': cadastro.pk,
        'documentacao_integracao': {
            'aba_vendas_ixc': (
                'No IXCSoft, a aba «Vendas» do cliente mostra o histórico de movimentos de venda/nota '
                'gerados dentro do próprio ERP (faturamento, contratos, NF etc.). Não é alimentada por '
                'este portal: o CADASTRO só envia os payloads abaixo (lead/contato, CRM candidatos, '
                'prospecção). Códigos como «Tipo doc.» 501 ou 633 são tabelas internas do IXC.'
            ),
            'debug_json_no_servidor': (
                'Cada POST ao IXC grava uma cópia do body em `cadastro/logs/ixc_debug/` '
                '(nome `debug_id_<cadastro_id>_CRM_LEAD|CRM_CANDIDATOS|CRM_PROSPECT>_*.json`). '
                'O log da tela de envio mostra `[DEBUG] JSON gerado em: …` com o caminho completo.'
            ),
        },
        'documento_digits': ''.join(c for c in str(cadastro.documento or '') if c.isdigit()),
        'radusuarios_pppoe': rad_pppoe,
        'ixc_vinculos_locais': {
            'ixc_lead_id': cadastro.ixc_lead_id or None,
            'ixc_lead_enviado_em': cadastro.ixc_lead_enviado_em.isoformat()
            if cadastro.ixc_lead_enviado_em
            else None,
            'ixc_candidato_id': cadastro.ixc_candidato_id or None,
            'ixc_prospect_id': cadastro.ixc_prospect_id or None,
            'ixc_contrato_id': getattr(cadastro, 'ixc_contrato_id', None),
            'ixc_envio_status': cadastro.ixc_envio_status,
            'ixc_lead_resource_gravado': (log_dict.get('ixc_lead_resource') or '').strip() or None,
            'ixc_lead_resource_inferido_etapa2': lr or None,
        },
        'lead_resources': [ixc.lead_resource_override]
        if ixc.lead_resource_override
        else ixc.crm_lead_resources_for_export(),
        'lead_payload': ixc.build_crm_lead_payload(cadastro),
        'crm_prospect_resource': getattr(settings, 'IXC_CRM_PROSPECT_RESOURCE', '').strip()
        or 'crm_prospect (+ IXC_CRM_PROSPECT_FALLBACK_RESOURCES se configurado)',
        'crm_prospect_payload': ixc.build_crm_prospect_payload(cadastro, link_contato_id=None),
        'crm_prospect_payload_etapa2_como_enviado': prospect_etapa2,
        'crm_candidatos_resource': getattr(settings, 'IXC_CRM_CANDIDATOS_RESOURCE', '').strip()
        or 'crm_candidatos (+ IXC_CRM_CANDIDATOS_FALLBACK_RESOURCES se configurado)',
        'crm_candidatos_payload': ixc.build_crm_candidatos_payload(cadastro, link_contato_id=None),
        'nota': (
            'crm_prospect_payload_etapa2_como_enviado reflete o POST de prospecção após lead local '
            '(id_contato / id_lead conforme recurso da etapa 1). Se ixc_lead_id estiver vazio, vem null. '
            'radusuarios_pppoe: login PPPoE gerado, montagem do POST de teste (senha mascarada) e logs de lookup IXC.'
        ),
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
def ixc_test_cliente_contrato(request, pk):
    """Teste (superusuário): POST ``cliente_contrato`` e, se configurado, ``radusuarios``."""
    if not request.user.is_superuser:
        return JsonResponse(
            {'status': 'error', 'message': 'Acesso restrito a superusuário.', 'logs': []},
            status=403,
        )
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
                'logs': [],
            },
            status=404,
        )
    head_logs = [f'[TESTE cliente_contrato] cadastro_id={cadastro.pk}']
    try:
        ixc = IXCIntegration()
        out = ixc.create_cliente_contrato_test(cadastro)
        merged_logs = head_logs + out.get('logs', [])
        if out.get('status') == 'success':
            logger.info('IXC cliente_contrato teste ok cadastro=%s', cadastro.pk)
        else:
            logger.warning('IXC cliente_contrato teste falhou cadastro=%s', cadastro.pk)
        resp = {
            'status': out.get('status', 'error'),
            'message': out.get('message', ''),
            'contrato_id': out.get('contrato_id'),
            'logs': merged_logs,
        }
        if 'radusuarios' in out:
            resp['radusuarios'] = out['radusuarios']
        return JsonResponse(resp)
    except Exception as e:
        logger.exception('IXC cliente_contrato teste excecao cadastro=%s', cadastro.pk)
        head_logs.append(str(e))
        return JsonResponse(
            {'status': 'error', 'message': str(e), 'logs': head_logs},
            status=500,
        )


@login_required
@user_passes_test(is_admin)
def clear_ixc_candidato_local(request, pk):
    """Remove só o vínculo local ``ixc_candidato_id`` (não apaga registro no IXC). Superuser — para reenviar crm_candidatos."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método inválido.', 'logs': []}, status=400)

    cadastro = get_object_or_404(Cadastro, pk=pk)
    old = (cadastro.ixc_candidato_id or '').strip()
    if not old:
        return JsonResponse({
            'status': 'warning',
            'message': 'Esta ficha não tem ixc_candidato_id gravado.',
            'logs': ['[IXC] nada a limpar.'],
        })

    cadastro.ixc_candidato_id = None
    logs_dict = cadastro.ixc_envio_logs if isinstance(cadastro.ixc_envio_logs, dict) else {}
    if logs_dict and 'ixc_candidato_id' in logs_dict:
        logs_dict = dict(logs_dict)
        logs_dict.pop('ixc_candidato_id', None)
        cadastro.ixc_envio_logs = logs_dict

    cadastro.save(update_fields=['ixc_candidato_id', 'ixc_envio_logs'])
    logger.info(
        'IXC candidato local cleared cadastro=%s old_id=%s user=%s',
        pk,
        old,
        request.user.pk,
    )
    return JsonResponse({
        'status': 'success',
        'message': (
            f'Vínculo local removido (candidato IXC era {old}). '
            'O registro no IXC não é excluído por aqui; na próxima integração um novo candidato pode ser criado se a API permitir.'
        ),
        'logs': [f'[IXC] removido ixc_candidato_id local={old}'],
    })


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