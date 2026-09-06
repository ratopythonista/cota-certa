# 0002. Arquitetura de Autenticação, Sessão e Proteção de Rotas no Monolito Dash

- **Status:** accepted
- **Data:** 2026-09-05
- **Decisores:** @ratopythonista, Engenharia Cota Certa

## Contexto e Problema

O Cota Certa é estruturado como um monolito reativo em Python Dash construído sobre o microframework Flask, persistindo dados no PostgreSQL (Supabase) via SQLModel.
A plataforma necessita de um ciclo completo de autenticação e autorização:
1. Cadastro de novos usuários com validação de unicidade e integridade.
2. Autenticação resiliente contra ataques de força bruta com `bcrypt`.
3. Proteção de páginas privadas (como a Carteira) e rotas restritas de administração (como o painel do Oráculo).
4. Blindagem de callbacks que executam mutações financeiras (ordens no AMM, depósitos Pix e vinculação de Endereço Externo Cripto).
5. Sincronização em tempo real do saldo em Reais (BRL) exibido na interface do usuário (navbar), inclusive após liquidações assíncronas de Cotas pelo Oráculo ou confirmações de depósitos via webhook/blockchain.

A arquitetura do Dash introduz um desafio de design: rotas e mutações trafegam como requisições AJAX assíncronas para o endpoint único `POST /_dash-update-component`. Proteger rotas apenas na borda HTTP do Flask (`before_request`) é ineficaz para navegação client-side, enquanto o uso descuidado de stores no cliente (`dcc.Store`) pode gerar defasagem de saldo e inconsistências de segurança.

## Decisão

Adotamos uma arquitetura de autenticação idiomática e reativa integrando **Flask-Login**, layouts dinâmicos funcionais do **Dash Pages** e controle de sessão server-side sob as seguintes definições:

1. **Submissão de Credenciais e Ciclo Reativo de Formulários:**
   - Telas de Login e Cadastro são construídas com componentes Dash nativos (`dcc.Input`, `html.Button`).
   - Validações de formato (email, força de senha e unicidade) são executadas no callback com feedback visual imediato (alertas inline), sem recarregar a tela em caso de erro.
   - No sucesso das credenciais, o callback invoca `flask_login.login_user(user, remember=True)` e retorna `dcc.Location(href=next_url or "/", refresh=True)`. O recarregamento completo do navegador (`refresh=True`) reconstrói a árvore do DOM sob o novo cookie assinado, garantindo sincronização atômica do contexto de `current_user`.

2. **Proteção de Páginas no Frontend (Dash Pages):**
   - Adoção de layouts dinâmicos funcionais (`def layout(**kwargs)` ou função registrada no `dash.register_page`).
   - Para páginas privadas (ex: `/carteira`): a função avalia `current_user.is_authenticated`. Se anônimo, retorna imediatamente um componente `dcc.Location(href=f"/login?next={pathname}", id="redirect-login")`.
   - Para páginas de administração/oráculo (ex: `/oraculo`): se o usuário não possuir `is_admin=True`, a função renderiza um layout estático amigável de erro HTTP 403 (Acesso Negado), prevenindo redirecionamentos circulares.

3. **Blindagem de Callbacks de Mutação (Backend Security):**
   - Implementação dos decoradores utilitários `@authenticated_callback` e `@admin_required_callback` para envelopar callbacks de mutação financeira e administrativa.
   - Padrão defensivo híbrido: se a assinatura do callback incluir um container de notificação/status de ordem, o decorador emite a mensagem amigável ("Sessão expirada. Faça login novamente."); caso contrário, interrompe a execução com `raise dash.exceptions.PreventUpdate`.

4. **Gestão de Estado da UI e Sincronização de Saldo da Carteira:**
   - **Zero `dcc.Store` de Sessão (Server-Side Exclusivo):** Nenhum dado de sessão ou saldo é duplicado no cliente. A navbar e componentes locais leem `current_user` diretamente do contexto da requisição.
   - **Atualização Reativa:** A seção do usuário na navbar escuta alterações em `dcc.Location.pathname` e eventos de sucesso de trades no AMM.
   - **Heartbeat Passivo de Sincronização:** Um componente `dcc.Interval(id="balance-heartbeat", interval=45000)` (45 segundos) é alocado no shell principal (`app.layout`). Quando o usuário está autenticado, dispara suavemente o callback da navbar para reconsultar o saldo atual, refletindo liquidações de Cotas pelo Oráculo e depósitos externos (Pix/Cripto) mesmo com o usuário ocioso.

5. **Fluxo de Logout ("Sair"):**
   - Disparado via callback reativo no botão "Sair", invocando `flask_login.logout_user()` e retornando `dcc.Location(href="/", refresh=True)`, que expira o cookie no navegador e restaura o layout público inicial.

6. **Segurança de Cookies e Custo de Hashing:**
   - **Cookies Assinados do Flask:** `SESSION_COOKIE_HTTPONLY=True` (bloqueio a scripts/XSS), `SESSION_COOKIE_SAMESITE='Lax'` (proteção contra CSRF), `PERMANENT_SESSION_LIFETIME = timedelta(days=30)`.
   - **Ambiente:** `SESSION_COOKIE_SECURE=True` estrito em produção (HTTPS no Render.com) e desligado em ambiente de desenvolvimento local.
   - **Bcrypt:** Custo de 12 rounds (`bcrypt.gensalt(rounds=12)`), persistindo a hash decodificada como string UTF-8 na coluna `hashed_password` da tabela `users`.

7. **Acoplamento do Modelo de Dados:**
   - Herança direta `class User(SQLModel, UserMixin, table=True)` para prover os contratos de identidade (`get_id`, `is_authenticated`, `is_active`) diretamente na entidade mapeada pelo ORM.

## Opções Consideradas

- **Callbacks 100% SPA sem Reload (`refresh=False`):** Rejeitado porque componentes pré-renderizados e layouts da aplicação dependeriam de múltiplos hooks reativos manuais para sincronizar o novo contexto de usuário, gerando código frágil e risco de renderização mista de dados.
- **Endpoints HTTP Tradicionais do Flask (`POST /login`):** Rejeitado para evitar quebra do padrão de desenvolvimento no ecossistema Dash e perda de validações visuais dinâmicas inline.
- **Middleware HTTP no Flask (`@server.before_request`) para Rotas:** Rejeitado porque na navegação SPA do Dash a URL HTTP da requisição permanece como `/_dash-update-component`, impossibilitando a detecção e proteção confiável de rotas apenas pelo path HTTP.
- **Persistência de Sessão no `localStorage` / `sessionStorage` (`dcc.Store`):** Rejeitado por risco de inconsistência contábil com o saldo do banco de dados e exposição de dados a ataques XSS.
- **Sessões Server-Side no PostgreSQL (`Flask-Session`) ou Tokens JWT Manuais:** Rejeitado para a POC por adicionar complexidade e I/O de banco desnecessário em cada callback AJAX, dado que os cookies assinados nativos do Flask atendem com excelência à escala e requisitos do monolito.

## Consequências e Plano de Desacoplamento Futuro

- **Positivas:** Modelo mental simples, sem duplicação de estado, segurança em duas camadas (frontend Dash Pages + decoradores de callbacks), proteção contra ataques web comuns e conformidade total com o `pyspecific`.
- **Acoplamento e Migração:** A herança direta de `UserMixin` na classe `User(SQLModel, ...)` acopla o modelo ao Flask-Login. No entanto, os métodos e propriedades providos pelo mixin operam puramente em memória e não geram nenhuma coluna ou artefato de schema no PostgreSQL. Caso a arquitetura evolua para uma API desacoplada (ex.: FastAPI com frontend React/Next.js) ou microsserviços, a remoção do `UserMixin` é imediata e indolor, sem necessidade de migrações (`ALTER TABLE`) na base de dados.
