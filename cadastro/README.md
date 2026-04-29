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

Crie/edite o arquivo `.env` na raiz do projeto (`cadastro/.env`) com as variaveis necessarias.

Exemplo:

```env
DATABASE_URL=postgresql://seu_usuario:sua_senha@seu_host/seu_banco?sslmode=require
SECRET_KEY=sua_chave_django
DEBUG=True
ALLOWED_HOSTS=*

CLOUDINARY_CLOUD_NAME=seu_cloud_name
CLOUDINARY_API_KEY=sua_api_key
CLOUDINARY_API_SECRET=sua_api_secret

IXC_API_URL=https://seuixc.com.br/adm.php
IXC_API_TOKEN=ID:TOKEN
IXC_LEAD_RESOURCE=
IXC_PROSPECT_STRATEGY=auto
IXC_PROSPECT_TIPO_ASSINANTE=1
IXC_PROSPECT_CLASSIFICACAO_ISS=99
IXC_PROSPECT_CLASSIFICACAO_ISS_FALLBACKS=99,00,01
IXC_PROSPECT_CLASSIFICACAO_ISS_ID=
IXC_PROSPECT_CONTRIBUINTE_ICMS=N
IXC_PROSPECT_TIPO_LOCALIDADE=U
```

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

### 6) (Opcional) Criar usuario admin

```powershell
python manage.py createsuperuser
```

### 7) Rodar o servidor

```powershell
python manage.py runserver
```

Acesse no navegador:

- Sistema: `http://127.0.0.1:8000`
- Admin Django: `http://127.0.0.1:8000/admin`

## Como testar rapidamente

1. Faça login com usuario consultor ou admin.
2. Crie/abra um cadastro.
3. Na tela de detalhe, clique em **ENVIAR PARA IXC**.
4. Verifique o modal de logs de integracao:
   - Se sucesso, deve mostrar `id` do lead.
   - Se erro, o log mostra endpoint, status HTTP e mensagem da API IXC.

## Comandos uteis

Checar configuracao Django:

```powershell
python manage.py check
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
