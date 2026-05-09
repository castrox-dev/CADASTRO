# Sistema de Gestao de Cadastros Fibramar

Sistema Django para captacao de clientes, acompanhamento de cadastros e integracao com IXC.

## Passo a passo para rodar local (Windows)

### 1) Entrar na pasta do projeto

```powershell
cd C:\Users\FIBRAMAR\Desktop\CADASTRO\cadastro
```

### 2) Criar e ativar ambiente virtual

Se ainda nao existir:

```powershell
python -m venv venv
```

Ativar:

```powershell
.\venv\Scripts\Activate.ps1
```

### 3) Instalar dependencias

```powershell
pip install -r requirements.txt
```

### 4) Configurar arquivo `.env`

Copie `env.example` para `.env` na pasta `cadastro/` e ajuste os valores. Em desenvolvimento costuma-se usar `DEBUG=True` e `ALLOWED_HOSTS=localhost,127.0.0.1`.

Modelo completo das variáveis: veja `env.example` na pasta `cadastro`.

Observacoes:
- `IXC_API_URL` pode ser informada com `.../adm.php`; o sistema normaliza automaticamente.
- `IXC_API_TOKEN` deve estar no formato `id:token`.
- `IXC_LEAD_RESOURCE` e opcional. Se preencher (ex.: `crm_leads`), o sistema usa apenas esse recurso; se vazio, tenta fallback automatico (`crm_leads`, `crm_sp_leads`, `crm_lead`).
- `IXC_PROSPECT_STRATEGY`: `auto` (padrao), `new` ou `convert`.
- Campos obrigatorios de prospect no IXC (ajuste conforme seu ERP): `IXC_PROSPECT_TIPO_ASSINANTE`, `IXC_PROSPECT_CLASSIFICACAO_ISS`, `IXC_PROSPECT_CONTRIBUINTE_ICMS`, `IXC_PROSPECT_TIPO_LOCALIDADE`.
- `IXC_PROSPECT_CLASSIFICACAO_ISS` costuma aceitar `00`, `01`, `02`, `03` ou `99` (padrao). Se informar `1`, o sistema converte para `01`.
- `IXC_PROSPECT_CLASSIFICACAO_ISS_FALLBACKS`: lista de tentativas automaticas (separadas por virgula) quando a API retornar "Preencha Classificacao de ISS".
- `IXC_PROSPECT_CLASSIFICACAO_ISS_ID`: se seu IXC exigir ID interno da classificacao (comum no endpoint `cliente`), preencha aqui. Quando informado, ele tem prioridade sobre codigos `99/00/01`.

### 5) Aplicar migracoes

```powershell
python manage.py migrate
```

### 6) (Opcional) Criar um superusuário (painel administrativo)

Usado para `/admin-dash/` e para configurar a ficha em `/admin-dash/operacao/`. **Não há interface Django Admin exposta na URL.**

```powershell
python manage.py createsuperuser
```

### 7) Rodar o servidor

```powershell
python manage.py runserver
```

Acesse no navegador:

- Sistema: `http://127.0.0.1:8000`
- Painel admin do sistema (superusuário): `http://127.0.0.1:8000/admin-dash/`

## Como testar rapidamente

1. Faça login com usuario consultor ou superusuário (painel admin).
2. Crie/abra um cadastro.
3. Na tela de detalhe, clique em **ENVIAR PARA IXC**.
4. Verifique o modal de logs de integracao:
   - Se sucesso, deve mostrar `id` do lead.
   - Se erro, o log mostra endpoint, status HTTP e mensagem da API IXC.

## Producao (vender / go-live)

1. **Variaveis de ambiente**  
   Copie `env.example` para `cadastro/.env` e preencha. Em produção use `DEBUG=False`, `SECRET_KEY` forte (não commite) e `ALLOWED_HOSTS` com o domínio real.  
   Defina `CSRF_TRUSTED_ORIGINS` com as mesmas URLs HTTPS (ex.: `https://seusite.com.br`).

2. **Banco**  
   `DATABASE_URL` com PostgreSQL (recomendado). Rode `python manage.py migrate` e `python manage.py collectstatic --noinput`.

3. **Mídia (uploads)**  
   Preencha `CLOUDINARY_*` se o ambiente não tiver disco persistente. Sem Cloudinary, arquivos vão para a pasta `media/` no servidor.

4. **Checagem de deploy** (com as variáveis de produção carregadas):

```powershell
python manage.py check --deploy
```

5. **Servidor**  
   Use Gunicorn (há `Procfile` na raiz do repositório para plataformas que suportam). Ajuste o caminho se o deploy usar só a pasta `cadastro` como raiz.

6. **IXC**  
   Preencha `IXC_API_URL` e `IXC_API_TOKEN` no ambiente de produção; teste o envio a partir de um cadastro de teste.

## Comandos uteis

Checar configuracao Django:

```powershell
python manage.py check
```

Checagem reforcada (produção):

```powershell
python manage.py check --deploy
```

Gerar novas migracoes (quando alterar models):

```powershell
python manage.py makemigrations
python manage.py migrate
```

## Estrutura principal

- `core/`: configuracoes do projeto Django.
- `cadastros/`: app principal (models, views, urls, integracao IXC).
- `templates/`: telas do sistema.
- `static/`: arquivos estaticos.

## Integracao IXC

O fluxo atual esta em etapas. No momento:

- Envia **apenas Lead**.
- Salva no banco:
  - `ixc_lead_id`
  - `ixc_lead_enviado_em`

Se quiser detalhes tecnicos da integracao, veja `INTEGRACAO_IXC.md`.
