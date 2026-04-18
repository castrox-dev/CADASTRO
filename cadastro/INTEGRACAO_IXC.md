# 🛠️ Guia de Integração IXCSoft - Fibramar

Este documento explica como configurar e como funciona o fluxo de integração entre o Sistema de Cadastros e o ERP IXCSoft.

## 🔄 Como Funciona o Fluxo

A integração foi desenvolvida seguindo o fluxo de vendas do CRM, dividida em duas etapas automáticas:

1.  **Etapa 1: CRM Lead**
    *   Assim que o consultor clica em "Enviar para o IXC", o sistema cria um registro no módulo **CRM > Leads** do IXC.
    *   Nesta etapa, enviamos o nome, documento, telefone, e-mail e uma descrição com o plano de interesse.
    *   O ID gerado por este Lead é capturado para o próximo passo.

2.  **Etapa 2: Conversão para Prospect**
    *   Com o Lead criado, o sistema cria automaticamente um **Cliente** com o status de **Prospect (P)**.
    *   Este Prospect já nasce vinculado ao Lead do CRM criado no passo anterior.
    *   Nesta etapa, enviamos todos os dados detalhados: Endereço completo, Bairro, CEP, Cidade, UF e se é Pessoa Física ou Jurídica.

---

## ⚙️ Configuração Técnica

Para que a integração funcione, você precisa configurar as variáveis de ambiente no seu arquivo `.env` ou no painel da sua hospedagem (Heroku, Vercel, etc).

### 1. Variáveis Obrigatórias
```env
IXC_API_URL=https://sua-url-ixc.com.br
IXC_API_TOKEN=seu_token_aqui
```
*   **URL**: Deve ser a URL base do seu IXC (ex: `https://provedor.ixcsoft.com.br`).
*   **Token**: Gerado dentro do IXC em *Configurações > Usuários > Usuários*, selecionando o usuário da API e gerando o Token de Acesso.

### 2. IDs de Referência (Customização)
No arquivo `cadastros/integrations.py`, existem alguns IDs que podem variar de acordo com a configuração do seu IXC:

*   **ID da Origem (`origem`)**: Atualmente definido como `'6'`. Você pode verificar o ID correto em *CRM > Configurações > Origens*.
*   **ID do Vendedor (`id_vendedor`)**: Atualmente definido como `'1'`. Você pode criar um usuário "Sistema de Cadastro" no IXC e usar o ID dele aqui.
*   **Status de Prospect**: O sistema define automaticamente como `'P'`, que é o padrão do IXC para clientes não ativos.

---

## 🖥️ Como usar no dia a dia

1.  **Captação**: O cliente ou consultor preenche o formulário normalmente.
2.  **Painel do Consultor**: O consultor acessa o Dashboard e verá o botão **"Enviar p/ IXC"** nos detalhes de cada cadastro.
3.  **Processamento**: Ao clicar, o sistema mostrará um aviso de "Enviando...".
4.  **Resultado**:
    *   ✅ **Sucesso**: O cadastro sumirá da lista de pendentes ou mostrará um aviso de sucesso.
    *   ⚠️ **Aviso**: Se o Lead for criado mas o Prospect falhar (ex: CEP inválido no IXC), o sistema avisará para você conferir manualmente.
    *   ❌ **Erro**: Se as chaves estiverem erradas ou o IXC estiver fora do ar, o sistema mostrará o erro retornado pela API.

---

## 📝 Notas Importantes
*   **Segurança**: O sistema utiliza o protocolo Bearer Token para autenticação segura.
*   **Evite Duplicidade**: O IXC costuma bloquear cadastros com o mesmo CPF/CNPJ. Se o cliente já existir no seu ERP, a API retornará um erro avisando da duplicidade.
*   **SSL**: A integração está configurada para ignorar erros de SSL (`verify=False`) para facilitar a conexão com servidores que não possuem certificados HTTPS válidos, mas recomenda-se o uso de HTTPS.

---
*Dúvidas sobre a API? Consulte a documentação oficial em: [https://wiki.ixcsoft.com.br/API_IXCSoft](https://wiki.ixcsoft.com.br/API_IXCSoft)*
