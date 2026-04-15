# Sistema de Gestão de Cadastros Fibramar 🚀

Sistema profissional desenvolvido em Django para provedores de internet (ISPs), focado na captação de clientes por consultores e gestão administrativa completa.

## ✨ Funcionalidades Principais

- **Painel do Consultor**:
  - Dashboard intuitivo com métricas de cadastros.
  - Link exclusivo de captação por consultor.
  - Gestão de status de instalação (Pendente, Aguardando, Realizado, Cancelado).
  - Geração automática de **Ordem de Serviço (OS)** formatada para copiar e colar.
  - Consulta rápida de CPF/CNPJ diretamente na Receita Federal.

- **Painel Administrativo (Full Access)**:
  - Visão geral de todos os consultores e cadastros.
  - Gestão de equipe: Criar, editar, excluir e resetar senhas de consultores sem sair do painel.
  - Relatórios avançados com gráficos interativos (Chart.js) de crescimento e status.

- **Formulário de Captação Inteligente**:
  - Multi-etapas com validação em tempo real.
  - **Mapa Interativo**: O cliente pode marcar o local exato da casa arrastando o pin (Leaflet.js).
  - Upload de documentos diretamente para a nuvem (**Cloudinary**).

- **Integração com ERP (IXCSoft)**:
  - Sincronização automática de leads e cadastros com o IXC.
  - Verificação de viabilidade e criação de Ordens de Serviço (OS) diretamente no ERP.
  - Evita o retrabalho de redigitação de dados.

- **Interface Moderna**:
  - Totalmente responsiva (Bootstrap 5).
  - **Modo Escuro (Dark Mode)** com persistência.
  - Sistema de notificações e modais customizados.

---

## 🛠️ Requisitos para Venda e Produção

Para colocar este sistema no ar para um cliente final, você precisará configurar os seguintes serviços:

### 1. Hospedagem (Cloud)
Recomendado usar serviços como **Heroku**, **Railway**, **Render** ou uma **VPS (DigitalOcean/Linode)**.
- O sistema usa SQLite por padrão, mas para produção recomenda-se **PostgreSQL**.

### 2. Integração IXCSoft (API)
Para que o sistema envie os dados automaticamente, o cliente deve fornecer:
- `IXC_API_URL` (URL do sistema IXC do provedor)
- `IXC_API_TOKEN` (Token de acesso gerado no IXC)

### 3. Armazenamento de Arquivos (Cloudinary)
O sistema já está configurado para o Cloudinary. Você precisará criar uma conta (gratuita ou paga) para o cliente e obter:
- `CLOUD_NAME`
- `API_KEY`
- `API_SECRET`
*Essas chaves devem ser colocadas no `settings.py`.*

### 4. Variáveis de Ambiente
Para segurança, nunca venda o sistema com as chaves "hardcoded". Utilize um arquivo `.env` para:
- `DEBUG=False`
- `SECRET_KEY` (Chave única do Django)
- `DATABASE_URL`
- `IXC_API_URL`
- `IXC_API_TOKEN`
- Credenciais do Cloudinary.

---

## 🚀 Como Instalar (Guia Rápido)

1. **Clonar o repositório**:
   ```bash
   git clone <url-do-repositório>
   cd cadastro
   ```

2. **Criar ambiente virtual**:
   ```bash
   python -m venv venv
   source venv/bin/scripts/activate  # Windows: venv\Scripts\activate
   ```

3. **Instalar dependências**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar o Banco**:
   ```bash
   python manage.py migrate
   ```

5. **Criar Superusuário**:
   ```bash
   python manage.py createsuperuser
   ```

6. **Rodar o servidor**:
   ```bash
   python manage.py runserver
   ```

---

## 📦 Dependências Principais
- Django 5.x
- Cloudinary & Django-Cloudinary-Storage (Upload de arquivos)
- Crispy Forms & Bootstrap 5 (UI/UX)
- Leaflet.js (Mapas)
- Chart.js (Gráficos)

---
**Desenvolvido com foco em alta performance e facilidade de uso para equipes de vendas.**
