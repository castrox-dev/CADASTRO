# Roteiro de Melhorias — Sistema de Cadastros Fibramar

Este documento lista melhorias técnicas e de produto sugeridas após o estudo do projeto. Cada item traz: **prioridade** (Alta / Média / Baixa), **categoria**, **descrição**, **arquivos afetados** e **benefício esperado**. Use como backlog incremental — a maioria dos itens é independente.

Legenda de prioridade:
- **Alta**: impacta segurança, correção, perda de dados ou bloqueio funcional.
- **Média**: melhora UX, manutenibilidade ou reduz custo operacional.
- **Baixa**: refinamentos, qualidade de código, padronização.

---

## 1. Segurança

### 1.1 [Alta] Não desabilitar verificação SSL nas chamadas IXC
Hoje `IXCIntegration._post_ixc()` usa `requests.post(..., verify=False)`. Isso ignora certificados inválidos e gera `InsecureRequestWarning`. É vetor para man-in-the-middle.
- **Arquivo**: `cadastros/integrations.py` (linhas ~133, ~528, etc.)
- **Ação**: tornar configurável via `.env` (`IXC_VERIFY_SSL=True`), padrão `True` em produção. Manter `False` apenas como override explícito para ambientes IXC com certificado autoassinado.

### 1.2 [Alta] Remover token IXC dos JSONs de debug
`_save_debug_json()` grava payloads em `media/ixc_debug/` que podem incluir dados pessoais (CPF, RG, telefone, endereço). Isso fica acessível via URL pública `/media/...`.
- **Arquivo**: `cadastros/integrations.py` (`_save_debug_json`)
- **Ação**:
  - Mover para fora de `MEDIA_ROOT` (ex.: `BASE_DIR / 'logs/ixc_debug'`).
  - Desativar por padrão em produção (`IXC_DEBUG_PAYLOADS=False`).
  - Implementar rotação/limpeza automática (manter últimos 7 dias).

### 1.3 [Alta] LGPD — consentimento, retenção e auditoria ✅ FEITO

**Modelo (`cadastros/models.py`):**
- `Cadastro` ganhou `consentimento_lgpd` (bool), `consentimento_em` (datetime), `consentimento_ip` (IP) e `anonimizado_em` (datetime).
- Método `Cadastro.anonimizar(executado_por, motivo)` substitui PII (nome, documento, RG, e-mail, telefone, endereço, fotos) por placeholders, apaga arquivos físicos e mantém estatísticas (status, plano, cidade, datas). É idempotente (`is_anonimizado` evita reprocessamento) e gera entrada de audit log automaticamente.
- Novo modelo `AcessoDadoSensivel(user, cadastro, acao, criado_em, motivo, ip)` registra ações: `visualizou`, `exportou`, `editou`, `anonimizado`. Read-only no Django admin.
- Migration `0025_cadastro_anonimizado_em_cadastro_consentimento_em_and_more.py` aplicada localmente.

**Consentimento explícito no `client_form`:**
- Adicionada caixa "Li e aceito a Política de Privacidade" no Step 6 (revisão final) do `templates/cadastros/form.html`, com link externo para `https://www.fibramarinternet.com.br/site/politicas` (target=`_blank`, rel=`noopener noreferrer`).
- Validação dupla: JS (`script.js`) bloqueia o submit com toast de aviso se não marcado; backend (`views.client_form`) responde 400 se o POST chegar sem `consentimento_lgpd`.
- Em caso de aceite, a view grava `consentimento_em = now()` e `consentimento_ip = X-Forwarded-For` (helper `_client_ip()` respeita proxies).

**Audit log de acesso cross-consultor:**
- Helper `_audit_pii(request, cadastro, acao)` em `views.py` cria `AcessoDadoSensivel` somente quando `cadastro.consultor_id != request.user.id` (consultor abrindo o próprio cadastro NÃO gera log — atende finalidade legítima sem ruído).
- Hook em `cadastro_detail` (visualização), `edit_cadastro` (POST = edição) e `export_cadastro_json` (exportação).
- Falhas no log são engolidas com `logger.exception` para nunca bloquear a request.

**Anonimização sob demanda (LGPD art. 18):**
- View `anonimizar_cadastro(request, pk)` (POST, superuser-only) chama `cadastro.anonimizar(...)`.
- URL: `cadastro/<int:pk>/anonimizar/`.
- Botão "ANONIMIZAR (LGPD)" no `_detail_inner.html` aparece para superusers em cadastros não-anonimizados, atrás de `showConfirm` com texto explicando que é irreversível. Quando já anonimizado, mostra um banner com a data.

**Anonimização automática por retenção (LGPD art. 16):**
- Management command `cadastros/management/commands/anonimizar_cadastros.py`.
- Padrões de retenção: `realizado` ≥ 730 dias (2 anos), `cancelado` ≥ 365 dias (1 ano), `pendente`/`aguardando` nunca (em operação).
- Flags: `--status` (repetível), `--days` (sobrescreve), `--dry-run`, `--limit N`.
- Uso típico: `python manage.py anonimizar_cadastros --dry-run` (revisa) → `python manage.py anonimizar_cadastros` (executa).
- Sugestão: agendar via cron mensal em produção. **Não** está agendado automaticamente.

**Política de privacidade:**
- Hospedada em `https://www.fibramarinternet.com.br/site/politicas` (já existente). Linkada diretamente no checkbox do client_form. Sem necessidade de criar template local.

### 1.4 [Alta] Permissões mais granulares
Hoje o sistema separa apenas `is_superuser` vs consultor comum. Não há grupo intermediário (gerente, financeiro, suporte).
- **Arquivos**: `cadastros/views.py`, `cadastros/views_operacao.py`
- **Ação**: trocar `@user_passes_test(is_admin)` por permissions Django (`@permission_required('cadastros.view_dashboard_admin')`) e usar Groups. Permite delegar relatórios sem dar acesso ao painel de operação.

### 1.5 [Média] Rate limiting na ficha pública
`/ficha/` é exposta sem autenticação. Vulnerável a flood/automação.
- **Ação**: usar `django-ratelimit` (5 submissões / IP / hora) ou Cloudflare Turnstile / hCaptcha.

### 1.6 [Média] CSP (Content Security Policy)
Não há header CSP. Carregamos JS de CDNs (jsdelivr, cdnjs, jquery.com).
- **Ação**: adicionar `django-csp` definindo `script-src` whitelist com os CDNs usados.

---

## 2. Arquitetura e Modelagem

### 2.1 [Alta] [x] Centralizar tabela de preços (parar de hardcodar)
**Concluído.** Adicionados `preco_mensal_reais` (DecimalField) e `nome_velocidade` (CharField) em `PlanoDefinicao` (migration `0022`). Criadas as properties `Cadastro.plano_velocidade` e `Cadastro.plano_preco_brl` que resolvem via `_get_plano_definicao()` (lookup por `cidade.grupo_planos + plano.codigo`), com fallback nos dicts antigos só para defesa em profundidade. `os_formatada` e `ficha_formatada` deixaram de duplicar dicionários inline. Migration de dados `0023` populou os planos existentes com os valores legados — preços/velocidades agora editáveis em `/admin-dash/operacao/grupos/<id>/`.

### 2.2 [Alta] [x] Eliminar mapas legados em `integrations.py`
**Parcialmente concluído.** Criado modelo `OrigemCanalVenda(label, ixc_id, ordem, ativo)` (migration `0022`); seed em `0023` carrega as 8 origens atuais. Adicionado `IXCIntegration.resolve_origem_ixc_id()` que faz lookup por `label` no banco e cai no `ORIGENS_MAP` legado se não houver registro. `build_crm_lead_payload` e `build_prospect_payloads` agora usam o resolver. Registrado em `admin.py` para edição via Django Admin (`/admin/`). **Pendente**: criar UI para gerenciar origens no painel customizado `/admin-dash/operacao/origens/` (mesmo padrão das cidades).

### 2.3 [Alta] [x] Implementar a estratégia `IXC_PROSPECT_STRATEGY=convert`
**Concluído.** `views.send_to_ixc` agora ramifica:
- `IXC_PROSPECT_STRATEGY=convert` → usa `convert_lead_to_prospect()`.
- `IXC_PROSPECT_STRATEGY=new` → usa `create_prospect()` (comportamento antigo).
- `IXC_PROSPECT_STRATEGY=auto` (padrão) → tenta convert; se falhar, faz fallback para `create_prospect()` automaticamente, registrando logs de cada tentativa.

### 2.4 [Média] [x] Substituir `client_form`/`edit_cadastro` por Django Forms
**Concluído.** Criado `cadastros/forms_cadastro.py` com `CadastroForm(forms.ModelForm)` cobrindo todos os campos do `Cadastro`. Aceita o alias `tipoPessoa` (camelCase), normaliza checkboxes (`'1'`/`'sim'`/`'on'` → bool) e expõe `apply_to(instance, files)` com semântica de checkbox HTML para edição segura. As views `client_form` e `edit_cadastro` reduziram ~40 linhas duplicadas cada e agora têm tratamento explícito de `IntegrityError`.

### 2.5 [Média] [x] Forçar `update_fields` nos saves de status
**Concluído.** `update_status` e `update_ficha` agora chamam `save(update_fields=[...])`. `Cadastro.save()` foi alterado para **pular `full_clean()` e a compressão de imagens** quando `update_fields` é passado — assim a ação rápida de mudar status não revalida CPF, duplicidade nem reabre PIL para nada. `update_status` também valida que o status novo está em `STATUS_CHOICES`.

### 2.6 [Baixa] [x] `unique=True` no banco para `Cadastro.documento`
**Concluído.** Migration `0024` é defensiva: primeiro consulta o banco em busca de duplicatas; se houver, aborta com `ValidationError` listando até 10 documentos em conflito (e instruindo como resolver). Só então aplica o `ALTER TABLE`. As views `client_form` e `edit_cadastro` capturam `IntegrityError` retornando 400 amigável.

### 2.7 [Baixa] [x] Tirar `ixc_debug/` do `MEDIA_ROOT`
**Concluído.** `_save_debug_json()` agora grava em `BASE_DIR/logs/ixc_debug/` (fora do `media/` e fora do storage do Cloudinary). `.gitignore` atualizado para ignorar `logs/`.

---

## 3. Performance

### 3.1 [Alta] Tornar a integração IXC assíncrona ⏳ PENDENTE (precisa de decisão de infra)
`send_to_ixc` faz até 4 requisições HTTP síncronas para o IXC (duplicidade + lead + prospect + retentativas). Bloqueia o request por até 2 min (timeout 30s × 4).
- **Por que não foi implementado nesta iteração**: exige um worker de fila persistente (Celery+Redis ou `django-q2` com cluster cmd). O deploy atual em Vercel é serverless, então `threading.Thread` "fire-and-forget" não funciona (a função morre quando a request termina). Precisamos primeiro decidir entre:
  1. mover deploy para um host com worker persistente (Render/Railway/Fly.io/VPS) e adicionar Celery+Redis;
  2. adotar um broker hospedado (Upstash QStash, Inngest, Trigger.dev) que dispara webhooks após X segundos — funciona em serverless;
  3. continuar síncrono mas com timeout maior no proxy/CDN da Vercel.
- **Mitigação já em produção**: `setButtonBusy()` (item 4.5) garante que o usuário recebe feedback imediato, e o `fetchJson` exibe toast ao final mesmo em erro de rede.
- **Próximo passo**: discutir caminho 1/2/3 com o time antes de mexer no código.

### 3.2 [Média] Otimizar dashboard / relatórios ✅ FEITO
- `dashboard()` agora usa `select_related('consultor')` para a tabela.
- `admin_dashboard()` agrega `total_geral` e `total_hoje` numa única query (`aggregate` + `Count` com `filter=Q(...)`), reduzindo de 4 para 3 queries no view.
- `reports_page()` agora calcula os 7 dias com **uma só query** usando `TruncDate('data_cadastro')`. Antes eram 7 queries em loop, agora é 1 (10 → 4 queries totais no view).
- **Cache**: `cache_page(60)` ainda não foi adicionado. Pode ser feito em seguida se precisar; a invalidação requer signal `post_save` no `Cadastro` para limpar a chave.

### 3.3 [Média] `scripts.html` (192 KB) — code-splitting / lazy load ⏳ PENDENTE
- **Por que não foi implementado nesta iteração**: o template é uma página HTML standalone com seu próprio `<head>`/`<body>` e ~4400 linhas misturando markup, CSS e scripts inline. Refatorar para SPA/componentes é um projeto à parte (estimativa: 2-3 dias) e justifica uma issue separada.
- **Próximo passo sugerido**: extrair os textos/scripts para um JSON e renderizar dinamicamente; ou pelo menos quebrar por categorias e carregar via `<details>`/`<dialog>` lazy.

### 3.4 [Média] Compressão de imagens — usar WebP ✅ FEITO
- `Cadastro.save()` agora tenta `format='WEBP', quality=80, method=6` antes de cair para JPEG.
- Mantém fallback automático: se a build do Pillow no host não tiver libwebp, salva como `.jpg` (mesma lógica anterior). Sem regressão possível.
- Resultado esperado: ~25–35% menos espaço em Cloudinary/disco para os 4 campos de imagem (`comprovante_residencia`, `foto_documento_frente/_verso`, `selfie_documento`).

### 3.5 [Baixa] Substituir jQuery / jquery.mask ⏳ PENDENTE
- **Por que não foi implementado nesta iteração**: `static/js/script.js` (multi-step do client_form), `_edit_scripts.html` e vários blocos inline dependem de `$()`, `$.mask` e `$.ready`. Trocar para vanilla / `imask.js` pede revisão linha-a-linha de `script.js` (~2k linhas) e testes manuais de cada formulário. Risco alto vs ganho médio.
- **Próximo passo sugerido**: começar pelos templates novos que ainda não usam `$` (mantendo jQuery temporariamente nos legados), e migrar `script.js` em um sprint dedicado.

---

## 4. UX e Frontend

### 4.1 [Alta] Padronizar todas as notificações como toasts ✅ FEITO
- `_messages.html` virou toast flutuante.
- Adicionado helper `fetchJson()` em `static/js/app_helpers.js` que centraliza:
  - parsing de JSON da resposta;
  - chamada automática de `showNotify(message, type)`;
  - injeção de CSRF token;
  - `setButtonBusy()` para spinner em botões durante a requisição.
- `showNotify` foi ajustado em `base.html` para usar texto escuro nos toasts `warning` (legibilidade). Adicionado `showInfo(title, html)` global (modal genérico).
- `detail.html`/`edit.html` migrados: `updateStatus`, `saveFicha`, `confirmDelete`, `sendToIXC`, submit da edição agora consomem `fetchJson` — sem `console.error` + alert genérico.

### 4.2 [Alta] Componente único de "shell admin" ✅ FEITO
- Criado `templates/cadastros/admin_shell.html` que estende `base.html`, monta sidebar + topbar mobile + área principal e expõe `block admin_content` + `block admin_page_title`.
- `base_admin.html` virou um simples `{% extends "cadastros/admin_shell.html" %}` (compat).
- JS do toggle extraído para `static/js/admin_shell.js` (carregado via `defer` pelo shell).
- `dashboard.html` agora é apenas o wrapper consultor; criado `dashboard_admin.html` que estende o shell. Conteúdo comum em `_dashboard_inner.html` para não duplicar.

### 4.3 [Média] Replicar sidebar admin nas demais páginas do consultor ✅ FEITO (parcial)
- Mesmo padrão aplicado em `detail.html` (+ `detail_admin.html` + `_detail_inner.html`) e `edit.html` (+ `edit_admin.html` + `_edit_inner.html`).
- Helper `_cadastro_for_user(request, pk)` em `views.py` permite que superuser veja/edite cadastros de outros consultores (necessário para a navegação admin fazer sentido) — consultor mantém escopo restrito.
- `standard_scripts` (template `scripts.html`) é uma página HTML standalone (não estende `base.html`); fica fora desta iteração e exige reescrita maior se quisermos colocá-lo no shell.

### 4.4 [Média] Dark mode — auditar contrastes restantes ✅ FEITO
Adicionadas regras em `static/css/style.css` (seção 16):
- caret SVG do `.form-select` substituído por versão clara no dark;
- `<option>` e `<select>` puro com `background-color: #1c1c2c`;
- `.alert-info / -warning / -success / -danger` repaginados para fundos translúcidos com cor de texto adequada; `.btn-close` interno invertido;
- `[data-theme="dark"] .badge[class*="badge-status-"]` ganhou borda translúcida para destacar sobre cards quase pretos;
- adicionado `:focus-visible` global em botões (a11y).

### 4.5 [Média] Indicador de carregamento durante envio IXC ✅ FEITO
- `setButtonBusy()` (em `app_helpers.js`) coloca spinner + `disabled` + `aria-busy="true"` enquanto a chamada está em andamento e restaura o conteúdo original ao fim.
- `sendToIXC`, `saveFicha`, submit do `edit_cadastro` e `confirmDelete` passam `busyButton` para o helper.

### 4.6 [Baixa] Acessibilidade (a11y) ✅ FEITO
- `aria-hidden="true"` em ícones decorativos e `aria-label` nos botões/links que só carregam ícone (`bi-eye`, `bi-gear-fill`, etc.) em `_dashboard_inner.html` e `_detail_inner.html`.
- Tabela do dashboard ganhou `<caption class="visually-hidden">`.
- Sidebar admin ganhou `aria-label` na `<nav>` e `aria-current="page"` nos itens ativos.
- Toast warning agora usa texto escuro (contraste suficiente sobre amarelo).

### 4.7 [Baixa] Mobile — sidebar admin com swipe ✅ FEITO
- `static/js/admin_shell.js` agora escuta `touchstart`/`touchmove`/`touchend` na sidebar.
- Threshold de 60 px e direction-lock 1.4× (cancela quando o gesto vira vertical/scroll).
- Swipe da direita para a esquerda fecha a sidebar; abrir continua sendo via botão hambúrguer.

---

## 5. Integração IXC

### 5.1 [Alta] Logs estruturados (não só `print/logger.info` com strings)
Hoje os logs são strings concatenadas (`"[CRM_LEAD] endpoint: ..."`). Difícil filtrar/observar.
- **Ação**: usar `structlog` ou `logging.LoggerAdapter` com `extra={'cadastro_id': pk, 'etapa': 'CRM_LEAD'}`. Facilita ingestão em Datadog/Sentry/Grafana.

### 5.2 [Alta] Retry exponencial e tratamento de timeout específico
Hoje, em caso de falha de rede, falha imediatamente. Algumas APIs IXC ficam lentas em horário de pico.
- **Arquivo**: `cadastros/integrations.py` (`_post_ixc`)
- **Ação**: usar `urllib3.util.Retry` ou `tenacity` (3 tentativas, backoff de 2s/4s/8s).

### 5.3 [Média] Cache de resultados de duplicidade
`check_duplicate_before_create()` faz 5 chamadas (qtypes × resources) em série. Se o usuário clicar 2× rápido, refaz tudo.
- **Ação**: cache curto (2 min) por `(documento, settings.IXC_API_URL)` em `django.core.cache`.

### 5.4 [Média] Tela de auditoria das tentativas IXC
Os logs por cadastro só aparecem no modal do envio. Não há histórico persistido.
- **Ação**: criar model `IXCEnvioLog(cadastro, etapa, payload_json, response_json, status, criado_em)` salvando cada tentativa. Tela de listagem em `/admin-dash/ixc-logs/`.

### 5.5 [Média] Webhooks IXC (recebimento)
Hoje só enviamos. O IXC suporta webhook quando o cliente é convertido (Lead → Cliente real, contrato assinado etc.).
- **Ação**: endpoint `POST /webhooks/ixc/` (com HMAC) que atualiza `cadastro.status` para `realizado` quando o IXC confirmar instalação.

### 5.6 [Baixa] Documentar mapeamento de campos
Criar tabela em `INTEGRACAO_IXC.md` mapeando cada campo do `Cadastro` → endpoint/parâmetro IXC. Acelera onboarding e debug.

---

## 6. Deploy e DevOps

### 6.1 [Alta] Migrar do Vercel para Render/Railway/Fly
Vercel não tem disco persistente, executa Django como função serverless e tem limite de payload. Os `FileField` (RG/selfie) só funcionam com Cloudinary configurado, e mesmo assim as funções "fluxo único" (criar lead → prospect) podem estourar 10s no Vercel free.
- **Ação**: o `Procfile` já existe na raiz. Conectar repositório no Render → Web Service Python → executar `migrate` automaticamente. Custo similar e suporte nativo a Postgres + cron.

### 6.2 [Alta] Versionar com Git
Hoje a pasta local **não é repositório Git** (`.git` ausente). Sem histórico, sem branch de produção, sem rollback.
- **Ação**:
  ```powershell
  cd C:\Users\FIBRAMAR\Desktop\CADASTRO
  git init
  git add .
  git commit -m "snapshot inicial"
  git remote add origin <github-url>
  git push -u origin main
  ```
- Conectar Vercel/Render via Git para deploy automático.

### 6.3 [Alta] CI mínimo (GitHub Actions)
Sem testes nem CI, qualquer regressão (CSS, migrations) só aparece em produção.
- **Arquivos**: novo `.github/workflows/ci.yml`
- **Ação**: rodar `python manage.py check`, `python manage.py makemigrations --check --dry-run`, `pip-audit`, e (futuro) `pytest`.

### 6.4 [Média] Backup automatizado do Postgres
Não há documentação de backup.
- **Ação**: cronjob do provedor (Render Postgres → backups diários inclusos) + comando management `dump_clientes_csv` para export periódico.

### 6.5 [Média] Pinning de dependências
`requirements.txt` usa `Django>=4.2` (sem teto). Abrange até Django 5.2 hoje. Atualização involuntária pode quebrar.
- **Ação**: usar `pip-tools` (`requirements.in` → `requirements.txt` pinned) ou `uv pip compile`.

### 6.6 [Média] Sentry / Datadog para erros em produção
Hoje só `logger.error` no console (que no Vercel some entre invocações).
- **Ação**: instalar `sentry-sdk` (free tier suficiente) e configurar DSN via `.env`.

### 6.7 [Baixa] Eliminar arquivos órfãos da raiz
- `cadastro/index copy.html` (192 KB) — snapshot antigo, não usado.
- `cadastro/index.html` (12 KB) — confirmar uso.
- Pastas `venv/` duplicadas (raiz e `cadastro/`).
- `db.sqlite3` versionado (já está no `.gitignore`, mas o arquivo precisa ser removido do tracking).

---

## 7. Manutenibilidade e Qualidade de Código

### 7.1 [Alta] Suite de testes (pytest)
Hoje só existe `cadastros/tests.py` vazio (0 bytes). Mudanças em `integrations.py` ou `models.py` quebram silenciosamente.
- **Ação**:
  - `pytest-django` + `responses` (mock HTTP) para testar `IXCIntegration` sem chamar API real.
  - Cobertura mínima nos models (`clean()`, `save()`, properties).
  - Smoke test do `client_form` com `Client.post()`.

### 7.2 [Média] Type hints e `mypy`
Nenhum arquivo Python tem anotações de tipo. Em `integrations.py` (~650 linhas) ajuda muito.
- **Ação**: adicionar `from __future__ import annotations`, anotar funções públicas, configurar `mypy --strict-optional`.

### 7.3 [Média] Lint (ruff) + format (black)
Sem ferramentas de qualidade configuradas.
- **Arquivos**: novo `pyproject.toml` ou `ruff.toml`
- **Ação**: `ruff check .` e `ruff format .`. Adicionar pre-commit hook.

### 7.4 [Média] Eliminar código duplicado em `views.py`
`client_form` (POST handler) e `edit_cadastro` (POST handler) repetem ~40 atribuições de campo. Resolvido junto com **2.4** (ModelForm).

### 7.5 [Baixa] Migrations de seed (0011–0021) — estratégia
Há 11 migrations de dados misturadas. Difícil rebobinar/replicar em ambiente novo.
- **Ação**: criar comando management `seed_operacao_defaults` idempotente; manter as migrations de dados só para o histórico.

### 7.6 [Baixa] Substituir `print` (se houver) por `logger`
Verificar e padronizar.

---

## 8. Funcionalidades Novas (produto)

### 8.1 [Média] Filtro/busca no dashboard do consultor
Hoje o consultor vê tudo cronologicamente. Adicionar busca por nome/CPF e filtro por status/cidade/data.

### 8.2 [Média] Exportar relatórios em CSV/Excel
A tela `/reports/` só mostra gráficos. Adicionar botão "Exportar" com `pandas` ou `csv` builtin.

### 8.3 [Média] Notificações por e-mail/WhatsApp
- E-mail automático ao cliente confirmando cadastro (Django + SMTP/SendGrid).
- Mensagem WhatsApp via Twilio/Meta API quando status muda para `aguardando` ou `realizado`.

### 8.4 [Média] Histórico visual no detalhe
`django-simple-history` já está instalado e o `Cadastro.history` está ativo. Falta UI para mostrar quem mudou o quê.
- **Arquivo**: `templates/cadastros/detail.html`
- **Ação**: aba "Histórico" listando alterações via `cadastro.history.all()`.

### 8.5 [Média] Múltiplos consultores por cadastro / transferência
Hoje `consultor` é FK simples. Adicionar campo `consultor_anterior` quando admin reatribuir.

### 8.6 [Baixa] Painel de KPIs em tempo real
Tempo médio entre cadastro → instalação, taxa de cancelamento por consultor, etc.

### 8.7 [Baixa] PWA para consultores
Adicionar `manifest.webmanifest` + service worker para instalar no celular como app.

---

## Roadmap sugerido (3 sprints)

**Sprint 1 — fundação (Alta prioridade)**
- 6.2 Versionar com Git + 6.3 CI básico
- 1.1 SSL configurável + 1.2 Tirar PII dos debug JSON
- 7.1 Suite de testes mínima
- 2.1 Centralizar tabela de preços
- 2.3 Implementar `prospect_strategy=convert`

**Sprint 2 — UX e robustez**
- 3.1 Integração IXC assíncrona (Celery)
- 5.1 Logs estruturados + 5.2 Retry exponencial
- 5.4 Tela de auditoria IXC
- 4.2 / 4.3 Padronizar shell admin nas demais páginas
- 6.1 Migrar deploy para Render

**Sprint 3 — produto**
- 8.4 UI de histórico
- 8.1 Filtros no dashboard + 8.2 Exportar relatórios
- 8.3 Notificações por e-mail
- 1.3 LGPD (consentimento + retenção)
- 1.4 Permissões granulares

---

_Documento vivo. Marque itens implementados com `[x]` e atualize prioridades conforme o backlog._
