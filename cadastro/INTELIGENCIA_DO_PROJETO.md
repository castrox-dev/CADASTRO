# Inteligência do projeto (CADASTRO / IXC)

Documento interno de referência para manter **consistência**, **reutilização** e **evitar endpoints duplicados**. Atualize quando a API ou o código mudarem.

---

## 1. Documentação externa (oficial / operação)

| Tema | Link |
|------|------|
| **Geração de token e URL** | https://drive.google.com/file/d/1IxyKupguftWyBU9De6-dblBAm2vlPAKT/view?usp=drive_link |
| **Liberação de IP** | https://drive.google.com/file/d/1t3E2sN7KukG74hyEXBdA7tKDIgwA-_s7/view?usp=drive_link |
| **Documentação da API (Postman)** | https://documenter.getpostman.com/view/40255984/2sAYBbe9Ma#ba9bdf84-5051-4a0b-b289-fea2fb9d0aa6 |

**Notas**

- O conteúdo dos PDFs no **Google Drive** não é incorporado aqui; consulte os arquivos ao implementar autenticação, base URL e whitelist de IP no ambiente do provedor.
- A coleção **Postman** é a fonte de verdade para **nomes de recursos**, **headers** (`ixcsoft: incluir` / `alterar` / etc.), **corpos** e **respostas** do webservice IXC. O código em `cadastros/integrations.py` deve **alinhar** com essa doc (não inventar recursos sem conferir).

**Link legado / placeholder** (se ainda aparecer em issues antigas): `documentacao_exemplo.com.br` — substituir sempre pelos links acima.

---

## 1.1 IDs IXC: teste (.env / defaults) vs produção (por cidade)

- Tudo que aparece como **ID fixo** no arquivo ``.env`` de exemplo, nos **defaults** de ``core/settings.py`` para variáveis ``IXC_*``, ou nos **dicts de fallback** em ``integrations.py`` (``FILIAIS_MAP``, ``CIDADES_MAP``, ``PLANOS_MAP``, ``ORIGENS_MAP``), serve **apenas para homologar** o fluxo (demo, Postman, máquina local).
- **Não** são os IDs finais de operação: na produção real, **cada cidade** terá a sua combinação de **filial**, **carteira de cobrança**, **planos (vd)**, **tipo de documento**, **tipo de cobrança**, **canais de venda / leads**, **recurso** ``cliente_contrato_<n>`` de assinatura, etc.
- Caminho previsto: preencher **Operação** no painel (``CidadeOperacao``, ``PlanoDefinicao`` com ``ixc_plano_venda_id``, ``OrigemCanalVenda``, …) e, onde ainda não houver modelo no Django, **substituir** os valores no ``.env`` por ambiente quando os IDs oficiais forem enviados.
- Regra mental: **.env de teste ≠ .env de produção**; qualquer número que «funcione no demo» pode ser inválido na base Fibramar.

---

## 2. Stack e estrutura da aplicação

- **Framework:** Django (projeto `core`, app `cadastros`).
- **URLs raiz:** `core/urls.py` — `login/`, `logout/`, demais rotas em `cadastros.urls`.
- **Config:** `core/settings.py` — `python-decouple` (`config`), `dj-database-url`, `crispy_forms` + `crispy_bootstrap5`, `simple_history`, `whitenoise`, `cloudinary` opcional.
- **Templates:** `cadastro/templates/` (base com modais, toasts, `fetchJson`).
- **JS compartilhado:** `static/js/app_helpers.js` — `fetchJson`, CSRF em POST, tratamento de erro HTTP vs `data.status`.

---

## 3. Middlewares (ordem)

Definidos em `settings.MIDDLEWARE`:

1. `SecurityMiddleware`
2. `WhiteNoiseMiddleware`
3. `SessionMiddleware`
4. `CommonMiddleware`
5. `CsrfViewMiddleware`
6. `AuthenticationMiddleware`
7. `MessageMiddleware`
8. `XFrameOptionsMiddleware`
9. `simple_history.middleware.HistoryRequestMiddleware`

**Implicação:** toda mutação via `fetch` em POST precisa de **CSRF** (header `X-CSRFToken` ou cookie; o helper já injeta a partir do input hidden do formulário).

---

## 4. Autenticação e autorização (Django)

- **Sessão:** `django.contrib.auth` — `@login_required` na maioria das views de cadastro.
- **Admin operacional:** `@user_passes_test(is_admin)` onde `is_admin = user.is_superuser` (dashboard admin, relatórios, gestão de consultores, hub operação).
- **Escopo de cadastro:** `_cadastro_for_user(request, pk)` — superuser vê todos; consultor só `Cadastro.objects.filter(consultor=request.user)`.

---

## 5. Endpoints HTTP **internos** (este repositório)

Prefixo: raiz do site (`''` em `core.urls` → rotas em `cadastros/urls.py`).

### 5.1 Autenticação (core)

| Método | Caminho | View | Resposta |
|--------|---------|------|----------|
| GET/POST | `/login/` | `LoginView` | HTML |
| GET/POST | `/logout/` | `LogoutView` | redirect |

### 5.2 Páginas HTML (cadastros)

| Método | Caminho | Decorators | Descrição |
|--------|---------|------------|-----------|
| GET | `/` | `@login_required` | Dashboard consultor / admin |
| GET | `/admin-dash/` | admin | Painel admin |
| GET | `/admin-dash/operacao/...` | admin | Hub e CRUD operação (cidades, grupos, vagas, vencimentos) — **forms Django**, sem JSON API dedicada em `views_operacao.py` |
| GET | `/reports/` | admin | Relatórios |
| GET/POST | `/admin-dash/manage/` e `.../<pk>/` | admin | Gestão de usuários consultores |
| GET/POST | `/ficha/` | — | Formulário público / ficha cliente |
| GET | `/cadastro/<pk>/` | `@login_required` | Detalhe do cadastro |
| GET | `/cadastro/<pk>/edit/` | `@login_required` | Edição |
| GET | `/scripts/` | — | Scripts padrão |
| GET | `/cadastro/<pk>/export-json/` | `@login_required` | Download JSON (payload IXC para debug) |

### 5.3 JSON (padrão do front: `status`: `success` | `error` | `warning`)

| Método | Caminho | Body / query | Resposta típica |
|--------|---------|--------------|------------------|
| POST | `/cadastro/<pk>/send-ixc/` | `ixc_etapa=lead` (padrão: lead + `crm_candidatos` encadeado), `candidatos` (só `crm_candidatos`) ou `prospect` | `{ status, message, logs?, lead_id?, candidato_id?, candidato_status?, prospect_id?, … }` |
| POST | `/cadastro/<pk>/update-status/` | `status` (POST field) | `{ status: success\|error, message? }` |
| POST | `/cadastro/<pk>/update-ficha/` | `ficha_texto` | `{ status }` |
| POST | `/cadastro/<pk>/edit/` | multipart form (arquivos + campos) | `{ status, message }` — erros 400 com mensagem amigável |
| POST | `/cadastro/<pk>/delete/` | — | JSON sucesso/erro |
| POST | `/cadastro/<pk>/anonimizar/` | — | JSON sucesso/erro |
| GET | `/api/form-config/` | — | JSON público da config da ficha (`get_form_config_dict`) ou `{ ok: false, error }` |

**Regra:** **não** criar novo endpoint para IXC se a ação couber em `send_to_ixc` (já bifurca `ixc_etapa` lead vs prospect).

---

## 6. Integração IXC (serviço reutilizável)

**Arquivo principal:** `cadastros/integrations.py` — classe `IXCIntegration`.

**Outbound (para o IXC):**

- Base: `{IXC_API_URL}/webservice/v1/{recurso}`
- Lead: `_post_ixc` com header `ixcsoft: incluir` (e opcionalmente `alterar` em fluxo pós-create).
- Auth: `Authorization` Bearer ou Basic (conforme token em `.env`) — ver doc token no Drive.

**Métodos relevantes (reutilizar):**

- `build_crm_lead_payload(cadastro)`
- `build_crm_candidatos_payload(cadastro, link_contato_id=..., ixc_lead_resource=...)`
- `build_crm_prospect_payload(cadastro, link_contato_id=..., ixc_lead_resource=...)`
- `create_crm_lead(cadastro)`
- `create_crm_candidatos(..., link_contato_id=..., ixc_lead_resource=..., force=True)` — encadeado após lead na etapa 1 (config: `IXC_CHAIN_CRM_CANDIDATOS_AFTER_LEAD`).
- `create_crm_prospect(..., link_contato_id=..., ixc_lead_resource=..., force=True)` — etapa 2: `link_contato_id` = `ixc_lead_id` local; vínculo IXC: `id_contato` (etapa 1 `contato`/`local`) ou `id_lead` (`crm_lead` / `crm_leads` / `crm_sp_leads`).
- `check_duplicate_before_create(cadastro)`
- `_post_ixc`, `_merge_crm_venda_fks`, resolvers de filial/cidade/plano/canal

**Variáveis de ambiente (trecho IXC):** ver `env.example` / `settings` — `IXC_API_URL`, `IXC_API_TOKEN`, `IXC_LEAD_RESOURCE`, `IXC_*_PLANO/CANAL`, `IXC_CHAIN_CRM_CANDIDATOS_AFTER_LEAD`, `IXC_CRM_CANDIDATOS_RESOURCE`, `IXC_CRM_CANDIDATOS_FALLBACK_RESOURCES`, `IXC_CRM_PROSPECT_RESOURCE`, `IXC_CRM_PROSPECT_FALLBACK_RESOURCES` (CSV, só nomes da doc Postman do provedor), `IXC_LEAD_POST_ALTERAR`, `IXC_REUSE_LOCAL_LEAD_ID`, etc.

**Auditoria local:** `logs/ixc_debug/debug_id_*_CRM_LEAD|CRM_PROSPECT_*.json`

**Tela IXC «Contrato do cliente» ↔ JSON `cliente_contrato` (incluir):**

| Rótulo na tela | Campo típico no POST | Notas |
|----------------|----------------------|--------|
| Plano de venda | `id_vd_contrato` | Input `#id_vd_contrato` (busca F2/F3 no IXC). |
| Tipo | `tipo` | Deve ser **o mesmo** «tipo» do registro do plano de venda (vd) escolhido; o IXC valida contrato vs vd. |
| Cliente | `id_cliente` | |
| Tipo de cobrança | `tipo_cobranca` | |
| Modelo para impressão | `id_modelo` | |

---

## 7. Modelos e regras de negócio (resumo)

- **`Cadastro`:** ficha completa; campos IXC `ixc_lead_id`, `ixc_candidato_id`, `ixc_prospect_id`, `ixc_envio_status`, `ixc_envio_mensagem`, `ixc_envio_logs` (JSON com `text` e opcionalmente `ixc_lead_resource`, `ixc_candidato_id`).
- **`get_ixc_data()` / `clean()`:** normalização BR (CPF/CNPJ, CEP, telefone), unicidade documento.
- **Operação:** `operacao_models` — `CidadeOperacao`, `PlanoDefinicao`, `OrigemCanalVenda`, faixas de vencimento — alimentam IDs IXC e textos da ficha.
- **LGPD:** anonimização zera vínculos IXC locais conforme implementação em `models.py`.

---

## 8. Convenções de implementação (obrigatórias)

1. **Antes** de nova rota: verificar seção 5 deste arquivo.
2. **Antes** de novo payload IXC: Postman + PDFs (token/IP).
3. Preferir **estender** `IXCIntegration` e **reutilizar** `send_to_ixc` com parâmetros POST existentes.
4. Front: **`fetchJson`** + mesmo padrão de `status` / `message` / `logs`.
5. Não duplicar lógica de truncagem de log/mensagem — usar `_truncate_ixc_msg` e constantes em `views.py` onde já existem.

---

## 9. Manutenção deste arquivo

- Quando o Postman mudar nomes de recursos ou exemplos, atualizar seção 1 e 6.
- Quando novas rotas Django forem **estritamente necessárias**, adicionar à tabela da seção 5 com método e contrato JSON.

*Última atualização: referências oficiais (Drive token/IP + Postman) incorporadas conforme solicitado pelo time.*
