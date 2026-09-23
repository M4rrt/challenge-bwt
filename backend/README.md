# Backend

Serviço FastAPI da aplicação de chat multiusuário. Veja `CONTEXT.md` na raiz do repositório e `docs/adr/` para o modelo de domínio e as decisões de arquitetura por trás deste código.

## Stack

- FastAPI, servido pelo Uvicorn
- SQLAlchemy 2.0 (async) + Alembic para migrations, PostgreSQL
- Redis para fan-out de WebSocket entre instâncias (ver `docs/adr/0003-redis-pubsub-for-horizontal-scaling.md`)
- `uv` para gerenciamento de dependências

## Estrutura do projeto

Por camada/papel (ver `docs/decisions.md` para o porquê):

```
app/
├── routers/    # endpoints da API
├── models/     # tabelas do SQLAlchemy
├── schemas/    # formatos de request/response do Pydantic
├── services/   # lógica de negócio
├── core/       # config, helpers de segurança, fronteira de Company
├── db.py       # engine async, session, declarative Base
└── main.py     # instância da aplicação FastAPI
alembic/        # ambiente de migrations (async)
tests/
```

## Rodando localmente

**Com Docker (recomendado):**

Na raiz do repositório: `docker compose up`

Isso builda e sobe Postgres, Redis, o backend (com hot-reload) e o frontend juntos. O backend roda as migrations automaticamente na subida e depois serve em `http://localhost:8000`. Health check: `curl http://localhost:8000/health`.

Editar qualquer arquivo em `app/` ou `alembic/` é refletido imediatamente (sem rebuild, sem restart) — o container faz bind-mount desses diretórios e o Uvicorn os observa com `--reload`.

Duas exceções:
- **Mudança de dependências** (`pyproject.toml`/`uv.lock`): rode `docker compose build backend` (ou `docker compose up --build`) para reinstalar.
- **Nova migration do Alembic**: rode `docker compose restart backend` para rodar `alembic upgrade head` de novo (migrations só rodam uma vez, na subida do container).

**Sem Docker:**

1. Instale o [`uv`](https://docs.astral.sh/uv/) se ainda não tiver: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Copie o arquivo de env e ajuste se precisar: `cp .env.example .env`
3. Suba Postgres + Redis: `docker compose -f ../docker-compose.yml up -d db redis`
4. Instale as dependências: `uv sync`
5. Aplique as migrations: `uv run alembic upgrade head`
6. Rode a API: `uv run uvicorn app.main:app --reload`
7. Health check: `curl http://localhost:8000/health`

## Tempo real (WebSocket + Redis)

Duas famílias de canais Redis pub/sub, uma por instância do backend (ver [ADR-0003](../docs/adr/0003-redis-pubsub-for-horizontal-scaling.md) e [`docs/architecture.md`](../docs/architecture.md) para o diagrama completo):

- `conversation:{id}` — corpo da mensagem, entregue a quem tem aquela conversa aberta no WebSocket. Cada instância faz um único `PSUBSCRIBE conversation:*` (não subscribe/unsubscribe por conversa), evitando race de reference-counting ao abrir/fechar várias abas.
- `user:{company_id}:{user_id}` — resumo leve ("essa conversa mudou"), entregue a todo participante independente de qual conversa está aberta; é o que mantém a prévia da última mensagem viva na lista de conversas sem cada cliente assinar todas as conversas de que participa. A Company entra na chave do canal porque o mesmo id de usuário pode existir em duas delas (ver "Isolamento por Company").

Endpoints: `WS /websocket/conversations/{id}` e `WS /websocket/users/me`, ambos autenticados via chat token como query param `token` (o handshake do WebSocket não carrega header `Authorization` customizado). Isso tem um custo: query strings tendem a ser gravadas em logs de acesso de proxies/ALB e no histórico do navegador, diferente de um header — trade-off não documentado em nenhum ADR até agora. A alternativa mais comum é conectar sem token e autenticar pela primeira mensagem do socket.

Se a conexão com o Redis cair, `run_subscriber` (`app/services/realtime.py`) simplesmente morre — sem log, sem retry, sem healthcheck que detecte isso. A entrega em tempo real para silenciosamente até o processo ser reiniciado.

## Autenticação

JWT de acesso de curta duração + refresh token opaco (ver [ADR-0004](../docs/adr/0004-jwt-in-localstorage.md) para o trade-off de guardar o JWT em `localStorage`). Duas decisões do refresh token, não cobertas na ADR:

- **Hash com SHA-256, não bcrypt.** O refresh token é um valor aleatório de alta entropia, não uma senha de baixo espaço de busca — o que ele precisa é um lookup indexado por igualdade exata, não uma comparação lenta e salgada pensada para resistir a brute-force de senha.
- **Sem rotação no uso.** Cada refresh token continua válido até expirar (7 dias) ou até logout explícito — não há esquema de rotate-and-detect-reuse. Um token vazado permanece utilizável nesse intervalo; simplificação deliberada dentro do escopo de "auth simplificada" do desafio, rotação seria o próximo passo de hardening.

## Webhook

`POST /webhook/messages` permite que um sistema externo entregue uma mensagem em uma conversa existente, autenticado por uma assinatura HMAC de segredo compartilhado em vez de um JWT.

**Request:**

- Body (JSON): `{ "company_id": "<uuid>", "conversation_id": "<uuid>", "body": "<texto>", "source_label": "<string, opcional>" }` — `company_id` é a Company em que a mensagem está sendo escrita, e a conversa é lida dentro dela: apontar para uma conversa de outra Company responde `404`, igual a uma conversa que não existe. `source_label` identifica o remetente externo na UI (ex.: `"Shipping Bot"`); omita ou envie `null` para um fallback genérico.
- Header `X-Signature`: `HMAC-SHA256(WEBHOOK_HMAC_SECRET, raw_request_body_bytes)` em hexadecimal.

A assinatura deve ser calculada sobre os **bytes exatos** enviados como corpo da requisição — reserializar o JSON (ordem de chaves diferente, espaços em branco) antes de assinar produz uma assinatura que falha na verificação, já que o servidor faz hash dos bytes brutos recebidos em vez de recodificar o payload já parseado.

Exemplo (Python):

```python
import hmac, hashlib, httpx

body = b'{"company_id": "0f1d6c21-9a1e-4f7a-9c2b-0f4b1a7e3d55", "conversation_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "body": "Your order shipped!", "source_label": "Shipping Bot"}'
signature = hmac.new(settings.webhook_hmac_secret.encode(), body, hashlib.sha256).hexdigest()

httpx.post(
    "http://localhost:8000/webhook/messages",
    content=body,
    headers={"X-Signature": signature, "Content-Type": "application/json"},
)
```

**Respostas:** `401` se a assinatura estiver ausente/inválida (checado antes de qualquer acesso ao banco), `404` se `conversation_id` não referenciar uma conversa existente **dentro de `company_id`**, `201` com a mensagem criada em caso de sucesso — entregue em tempo real aos participantes conectados da conversa pelo mesmo caminho Redis/WebSocket de uma mensagem normal.

**Lacunas conhecidas** (ver `docs/decisions.md`):

- Sem proteção contra replay — uma requisição válida capturada pode ser reenviada.
- Sem forma segura de o sistema externo descobrir qual `conversation_id` usar — ele precisa já saber o UUID de antemão.
- **O segredo HMAC é um só para todas as Companies.** O payload agora nomeia a `company_id` e uma conversa de outra Company é recusada, mas nada amarra a assinatura àquela Company: quem tem o segredo pode assinar um payload nomeando qualquer Company. Ticket 14 dá a cada Company um segredo próprio.
- Sem checagem de que o `conversation_id` pertence a um participante — dentro da Company certa, qualquer chamador com o segredo pode injetar mensagem em qualquer conversa cujo UUID conheça.

## Testes

TDD, red-green-refactor conforme o `CLAUDE.md` do repositório — os testes são escritos junto com cada comportamento, não depois.

```
uv run pytest
```

**Ressalva conhecida:** as respostas de `Conversation` retornam participantes ordenados por `user_id`, mas essa ordenação hoje é efeito colateral do plano de execução do Postgres sobre o índice único composto de `conversation_participants`, não uma garantia de um `ORDER BY` explícito — descoberto ao escrever o RED de um teste de regressão do ticket 23, que passava mesmo sem o fix pretendido. Adicionar um `ORDER BY` explícito antes de depender mais disso.

## Isolamento por Company

Nenhuma leitura atravessa uma Company. A [ADR-0007](../docs/adr/0007-own-database-company-boundary-in-code.md) tirou esse isolamento do banco e o deixou no código, e chamou isso de risco central da arquitetura: sem um queryset carregando o invariante, todo caminho de leitura precisa filtrar por Company explicitamente, e um que esqueça vaza as conversas de uma Company para outra.

O piso que substitui o queryset é `app/core/company_scope.py`:

- Toda linha legível carrega sua Company (`CompanyScoped` — `conversations`, `conversation_participants`, `messages`).
- Toda leitura de uma dessas entidades nasce de `CompanyScope.select`, que tira a Company do token de quem chamou. Nenhum serviço ou router monta a própria query, e nenhum router constrói o próprio escopo: ele chega pela dependência `get_company_scope` (`app/core/security.py`).
- O canal de lista de conversas do Redis é `user:{company_id}:{user_id}`, não `user:{user_id}`. O mesmo id de usuário pode existir em duas Companies, e o resumo de Chat empurrado por `/websocket/users/me` carrega id, nome e participantes — chaveado só por usuário, ele cairia no socket aberto com o token da outra Company.
- O filtro cai no `WHERE`, então uma linha de outra Company não é proibida, é **ausente**: um pedido cruzando a fronteira e um pedido por algo que nunca existiu devolvem `404` com o mesmo corpo, e nada na resposta distingue os dois.

`tests/test_company_isolation.py` cobre cada caminho de leitura e, por último, faz um teste estrutural: ele varre a AST de todo o `app/` atrás de `select(E)`, `sa.select(E)`, `session.get(E, ...)`/`get_one` e `session.query(E)` sobre uma entidade escopada fora do módulo de escopo, e falha apontando arquivo e linha. O conjunto de entidades escopadas sai do registry do SQLAlchemy, não de uma lista escrita à mão, então uma entidade nova entra na varredura assim que é mapeada.

**Ao adicionar uma entidade legível nova, acrescente o teste de isolamento dela** — o teste estrutural garante que a query passe pelo escopo, não que alguém tenha verificado o comportamento pela borda. Dois limites que ele não cobre, e que o teste documenta: ele reconhece `scope.select(...)` pela grafia do receptor (não por tipo), e `text("SELECT ...")` cru é invisível para ele. **Fan-out também não é leitura de query**: um caminho que empurra dados por canal (Redis, WebSocket) precisa carregar a Company na própria chave do canal — foi assim que `/websocket/users/me` vazou antes de ser corrigido.

O webhook é o único chamador sem token: ele nomeia a Company no próprio payload (veja a seção Webhook) e lê a conversa dentro dela.

## Débito técnico conhecido

Não bloqueia o funcionamento hoje, mas seria o primeiro ponto de atenção antes de qualquer uso com carga real:

- **BLOQUEADOR DE PRODUÇÃO: o chat token ainda é HS256.** `app/core/chat_token.py`
  verifica com um segredo compartilhado, então o serviço **consegue emitir um
  token que ele próprio aceita**. O [ADR-0009](../docs/adr/0009-chat-owns-token-in-rs256.md)
  foi aceito justamente para remover essa propriedade e ainda não está
  implementado. Ticket 19 troca por RS256 + `kid` + JWKS + `aud` obrigatório.
  Nada abaixo desta linha é um risco da mesma ordem.
- **Sem índice em `messages.conversation_id`.** Nenhuma migração cria esse índice — `list_messages` (filtra por `conversation_id`, ordena por `created_at`) e a busca da última mensagem por conversa fazem table scan à medida que o histórico cresce.
- **Índice de `conversation_participants` favorece a query errada.** O `UniqueConstraint(conversation_id, user_id)` serve bem a checagem de membership, mas `list_conversations` — chamada a cada carregamento da sidebar — filtra só por `user_id`; faltaria um índice dedicado liderado por esse campo.
- **Sem rate limiting** em `/webhook/messages`.
- **Sem paginação** em nenhuma listagem (`GET /conversations`, `GET /conversations/{id}/messages`) — todas devolvem o conjunto inteiro.
- **Zero logging estruturado** em todo o `app/` — combinado com o subscriber Redis sem tratamento de falha (acima), é o ponto mais arriscado de operar isso em produção sem visibilidade.

## Migrations

```
uv run alembic revision --autogenerate -m "message"
uv run alembic upgrade head
```

`alembic/env.py` lê a URL do banco a partir de `app.core.config.settings` (ou seja, do `.env`), não do `alembic.ini`.
