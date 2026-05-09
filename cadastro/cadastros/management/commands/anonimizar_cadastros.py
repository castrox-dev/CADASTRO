"""
Management command — anonimização de cadastros para conformidade com a LGPD
(art. 16: dados podem ser mantidos para finalidades legítimas, mas devem ser
anonimizados após o término do tratamento; art. 18: titular pode pedir
anonimização/exclusão).

Uso típico (cron mensal):
    python manage.py anonimizar_cadastros --status realizado --days 730 --dry-run
    python manage.py anonimizar_cadastros --status realizado --days 730

Sem `--dry-run`, o comando substitui PII (nome, documento, RG, e-mail,
telefone, endereço, fotos) por placeholders. Mantém estatísticas operacionais
(plano, cidade, status, datas) intactas.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from cadastros.models import Cadastro


DEFAULT_DAYS = {
    'realizado': 730,    # 2 anos após instalado
    'cancelado': 365,    # 1 ano após cancelamento
    'pendente': None,    # nunca anonimizar pendentes (ainda em operação)
    'aguardando': None,
}


class Command(BaseCommand):
    help = 'Anonimiza cadastros antigos para conformidade com a LGPD.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--status',
            action='append',
            choices=['realizado', 'cancelado', 'pendente', 'aguardando'],
            help='Status alvo (pode ser repetido). Default: realizado e cancelado.',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Dias mínimos desde data_cadastro (sobrescreve defaults por status).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Lista o que seria anonimizado sem alterar o banco.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Limita o número de registros processados (0 = sem limite).',
        )

    def handle(self, *args, **opts):
        status_list = opts['status'] or ['realizado', 'cancelado']
        days_override = opts['days']
        dry_run = opts['dry_run']
        limit = opts['limit']

        now = timezone.now()
        total_processados = 0
        total_anonimizados = 0
        total_pulados = 0

        for status in status_list:
            days = days_override if days_override is not None else DEFAULT_DAYS.get(status)
            if days is None:
                self.stdout.write(self.style.WARNING(
                    f'Status "{status}" sem regra de retenção definida; pulando.'
                ))
                continue

            cutoff = now - timedelta(days=days)
            qs = Cadastro.objects.filter(
                status=status,
                data_cadastro__lt=cutoff,
                anonimizado_em__isnull=True,
            ).order_by('data_cadastro')

            if limit:
                remaining = limit - total_processados
                if remaining <= 0:
                    break
                qs = qs[:remaining]

            count = qs.count()
            self.stdout.write(self.style.NOTICE(
                f'\n=== {status.upper()} (>= {days} dias, antes de {cutoff:%d/%m/%Y}) — {count} candidato(s) ==='
            ))

            for cadastro in qs:
                total_processados += 1
                idade = (now - cadastro.data_cadastro).days
                linha = (
                    f'  #{cadastro.pk:>5}  {cadastro.data_cadastro:%d/%m/%Y}  '
                    f'({idade}d)  {cadastro.nome_razao[:40]:<40}  {cadastro.documento}'
                )

                if dry_run:
                    self.stdout.write('  [DRY] ' + linha)
                    total_pulados += 1
                    continue

                try:
                    with transaction.atomic():
                        anonimizou = cadastro.anonimizar(motivo=f'Retenção {status} ≥ {days} dias')
                    if anonimizou:
                        total_anonimizados += 1
                        self.stdout.write(self.style.SUCCESS('  [OK]  ' + linha))
                    else:
                        total_pulados += 1
                        self.stdout.write('  [JA-ANON] ' + linha)
                except Exception as exc:
                    total_pulados += 1
                    self.stderr.write(self.style.ERROR(
                        f'  [ERR] #{cadastro.pk}: {exc}'
                    ))

        self.stdout.write('\n' + self.style.MIGRATE_HEADING('Resumo'))
        self.stdout.write(f'  candidatos processados: {total_processados}')
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'  modo DRY-RUN — nenhum dado foi alterado.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f'  anonimizados: {total_anonimizados}'))
            if total_pulados:
                self.stdout.write(f'  pulados/erro: {total_pulados}')
