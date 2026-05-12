# Inteligência do projeto (CADASTRO / IXC)

Documento interno de referência para manter **consistência**, **reutilização** e **evitar endpoints duplicados**. Atualize quando a API ou o código mudarem.

---

## 1. Documentação externa (fonte de verdade)

### 1.1 Documentação completa da API (prioridade)

| Tema | Link |
|------|------|
| **Doc API Provedor — API IXC Provedor (coleção pública)** | **https://docs.doc-api-provedor.com/** |

**Uso esperado**

- Navegue pela coleção **“API - IXC Provedor”** no portal (ambiente, layout e idioma configuráveis no topo da página).
- Cada endpoint lista **método HTTP**, **URL** (`https://{seu-dominio}/webservice/v1/{recurso}`), **Authorization (Basic)**, **headers** (ex.: `ixcsoft: incluir`, `alterar`, `listar`, … conforme o caso), **corpo JSON** de exemplo e **respostas**.
- **Sempre** conferir aqui antes de alterar `cadastros/integrations.py` (nome do recurso, campos obrigatórios, grafias oficiais — ex.: prospecções em **`crm_canditados`**).

**Nota técnica:** o site é carregado como aplicação no navegador (“Loading Collection…” em requisições automatizadas). Para desenvolvimento, abra o link no **browser** e use busca interna da doc (Ctrl+F) pelo recurso desejado.

### 1.2 Material complementar (operação / provedor)

| Tema | Link |
|------|------|
| **Geração de token e URL** | https://drive.google.com/file/d/1IxyKupguftWyBU9De6-dblBAm2vlPAKT/view?usp=drive_link |
| **Liberação de IP** | https://drive.google.com/file/d/1t3E2sN7KukG74hyEXBdA7tKDIgwA-_s7/view?usp=drive_link |

O conteúdo dos PDFs no **Google Drive** não é incorporado aqui; use-os para política de **usuário com webservice/API**, **token** e **whitelist de IP** no grupo de usuários do IXC.

### 1.3 Referência adicional (Postman legado / espelho)

| Tema | Link |
|------|------|
| **Documentação da API (Postman — view pública)** | https://documenter.getpostman.com/view/40255984/2sAYBbe9Ma#ba9bdf84-5051-4a0b-b289-fea2fb9d0aa6 |

Útil para comparação ou histórico; em caso de divergência com **docs.doc-api-provedor.com**, **prevalece a doc do provedor** (seção 1.1).

**Substituir links antigos:** qualquer referência a `documentacao_exemplo.com.br` ou “só Postman” sem o portal **Doc API Provedor** está desatualizada.

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
|--------|---------|------------|------------|
| GET | `/` | `@login_required` | Dashboard consultor / admin |
| GET | `/admin-dash/` | admin | Painel admin |
| GET | `/admin-dash/operacao/...` | admin | Hub e CRUD operação (cidades, grupos, vagas, vencimentos) — **forms Django**, sem JSON API dedicada em `views_operacao.py` |
| GET | `/reports/` | admin | Relatórios |
| GET/POST | `/admin-dash/manage/` e `.../<pk>/` | admin | Gestão de usuários consultores |
| GET/POST | `/ficha/` | — | Formulário público / ficha cliente |
| GET | `/cadastro/<pk>/` | `@login_required` | Detalhe do cadastro |
| GET | `/cadastro/<pk>/edit/` | `@login_required` | Edição |
| GET | `/scripts/` | — | Scripts padrão |
| GET | `/cadastro/<pk>/export-json/` | `@login_required` (superuser) | Download JSON (payload IXC para debug) |

### 5.3 JSON (padrão do front: `status`: `success` | `error` | `warning`)

| Método | Caminho | Body / query | Resposta típica |
|--------|---------|--------------|------------------|
| POST | `/cadastro/<pk>/send-ixc/` | `application/x-www-form-urlencoded`: `ixc_etapa=lead` (padrão) ou `ixc_etapa=prospect` | `{ status, message, logs?, lead_id?, prospect_id?, duplicate?, prospect_pendente?, ixc_etapa? }` |
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

### 6.1 Contrato com o WebService (alinhado à doc Doc API Provedor)

- **Base URL:** `{IXC_API_URL normalizado}/webservice/v1/{recurso}`  
  - `IXC_API_URL` no `.env` pode terminar em `/adm.php`; o código remove esse sufixo para montar a base da API.
- **Autenticação:** header `Authorization` — **Basic** (credencial `usuario:token` ou `usuario:senha` em Base64, conforme painel IXC) ou **Bearer** se o token for JWT (três segmentos com `.`).
- **Ação no IXC:** header **`ixcsoft`** — valores usados no projeto incluem `incluir` e `alterar` (POST). Listagens/consultas na doc podem usar `listar`, `obter`, etc. — ver **exatamente** o exemplo do recurso em https://docs.doc-api-provedor.com/ .
- **Conteúdo:** `Content-Type: application/json`; corpo conforme tabela/recurso na documentação.

### 6.2 Fluxo implementado neste sistema (duas etapas)

| Etapa | `ixc_etapa` (POST) | IXC (resumo) | Código |
|-------|---------------------|--------------|--------|
| 1 | `lead` | Cria **lead/contato** no recurso configurado (ex.: `contato`, `crm_leads`, …) | `create_crm_lead`, `build_crm_lead_payload` |
| 2 | `prospect` | Cria **prospecção**; na doc IXC o recurso de inserção é **`crm_canditados`** (grafia com “i”); fallback `crm_prospect` se necessário | `create_crm_prospect`, `build_crm_prospect_payload` |

- **Vínculo etapa 2 → etapa 1:** `link_contato_id` = `ixc_lead_id` local; conforme recurso da etapa 1, o payload envia `id_contato_principal` / `id_contato` (contato/local) ou `id_lead` (recursos `crm_*`).
- **Resposta vazia:** alguns POST da doc não retornam corpo; o cliente HTTP trata 200 + corpo vazio e a camada de prospecção pode retornar `warning` — ver `integrations.py`.

### 6.3 Métodos relevantes (reutilizar)

- `build_crm_lead_payload(cadastro)`
- `build_crm_prospect_payload(cadastro, link_contato_id=..., ixc_lead_resource=...)`
- `create_crm_lead(cadastro)`
- `create_crm_prospect(..., link_contato_id=..., ixc_lead_resource=..., force=True)`
- `check_duplicate_before_create(cadastro)`
- `_post_ixc`, `_merge_crm_venda_fks`, resolvers de filial/cidade/plano/canal

### 6.4 Variáveis de ambiente (trecho IXC)

Ver **`env.example`** / **`core/settings.py`**: `IXC_API_URL`, `IXC_API_TOKEN`, `IXC_LEAD_RESOURCE`, `IXC_*_PLANO/CANAL/CAMPANHA`, `IXC_CRM_PROSPECT_RESOURCE`, `IXC_CRM_PROSPECT_FALLBACK_RESOURCES`, `IXC_LEAD_POST_ALTERAR`, `IXC_REUSE_LOCAL_LEAD_ID`, etc.

### 6.5 Auditoria local

`logs/ixc_debug/debug_id_*_CRM_LEAD|CRM_PROSPECT_*.json`

---

## 7. Modelos e regras de negócio (resumo)

- **`Cadastro`:** ficha completa; campos IXC `ixc_lead_id`, `ixc_prospect_id`, `ixc_envio_status`, `ixc_envio_mensagem`, `ixc_envio_logs` (JSON com `text` e opcionalmente `ixc_lead_resource`).
- **`get_ixc_data()` / `clean()`:** normalização BR (CPF/CNPJ, CEP, telefone), unicidade documento.
- **Operação:** `operacao_models` — `CidadeOperacao`, `PlanoDefinicao`, `OrigemCanalVenda`, faixas de vencimento — alimentam IDs IXC e textos da ficha.
- **LGPD:** anonimização zera vínculos IXC locais conforme implementação em `models.py`.

---

## 8. Convenções de implementação (obrigatórias)

1. **Antes** de nova rota: verificar seção 5 deste arquivo.
2. **Antes** de novo payload ou recurso IXC: **https://docs.doc-api-provedor.com/** (obrigatório) + PDFs Drive se for política de token/IP.
3. Preferir **estender** `IXCIntegration` e **reutilizar** `send_to_ixc` com parâmetros POST existentes.
4. Front: **`fetchJson`** + mesmo padrão de `status` / `message` / `logs`.
5. Não duplicar lógica de truncagem de log/mensagem — usar `_truncate_ixc_msg` e constantes em `views.py` onde já existem.

---

## 9. Manutenção deste arquivo

- Quando a **Doc API Provedor** publicar nova versão da coleção (novos recursos, campos ou headers), atualizar as seções **1** e **6** e revisar `integrations.py`.
- Quando novas rotas Django forem **estritamente necessárias**, adicionar à tabela da seção 5 com método e contrato JSON.

*Última atualização: fonte principal de documentação da API alterada para **https://docs.doc-api-provedor.com/**; Drive e Postman mantidos como complemento / legado.*
