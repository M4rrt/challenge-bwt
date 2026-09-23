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
├── db.py       # engine async, session, declarative Base, helper de coluna enum
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

## Domínio: Chat e Participant

O vocabulário vem do `CONTEXT.md` na raiz — Chat, Company, Staff Chat, Client Chat, Participant. As palavras que ele lista em _Avoid_ (Conversation, Conversa, Room, Sala) não aparecem em `app/` nem em `tests/`, e `tests/test_glossary.py` falha apontando arquivo e linha se voltarem. `alembic/versions/` fica de fora: uma migration é um registro datado, e a que criou `conversations` descreve um schema que realmente existiu com esse nome.

- **Chat** carrega Company, tipo (`staff` | `client`), nome opcional e timestamps. 1:1 e grupo são a mesma entidade — um 1:1 é um Chat com exatamente dois Participants, não um conceito à parte.
- **Participant** carrega Chat, identificador do usuário, Company, papel (`staff` | `client`), `joined_at`, `left_at` e o estado de leitura (`last_read_at`, `last_read_message_id`). O estado de leitura ainda não tem leitor: entra no ticket 09.
- **Sair de um Chat é um instante, não um delete.** Com `left_at` preenchido a pessoa some de todo caminho de leitura sem que a linha seja apagada — as mensagens que ela mandou seguem atribuíveis e o Chat segue explicável. `STILL_IN_THE_CHAT` (`app/models/chat.py`) é a única grafia de "é Participant atual" em query, e `Chat.current_participants` a única em Python.

### `POST /chats`

A criação pública ainda existe e é substituída pelo comando interno do ticket 05. O corpo nomeia o tipo do Chat e o kind de cada Participant, porque o serviço não tem tabela de usuários para consultar:

```json
{
  "type": "staff",
  "participants": [{ "user_id": "<uuid>", "user_kind": "staff" }],
  "name": null
}
```

Quem chama entra como Participant com o `user_kind` do próprio token — esse claim o comando não escolhe. O serviço valida a **forma** do Chat, que é invariante dele e não do chamador, e responde `422` quando ela não fecha:

- `a staff chat cannot contain an end client` — Staff Chat é definido pela ausência do cliente final.
- `name is required for group chats` — grupo (3+ Participants) precisa de nome; 1:1 não.
- `unrecognised user kind` — um kind fora de `staff`/`client` não tem lugar em regras escritas nessas duas palavras.

Abrir um 1:1 que já existe devolve o Chat existente ([ADR-0002](../docs/adr/0002-explicit-idempotent-chat-creation.md)). Se alguém saiu dele, aquele 1:1 já não existe como tal e um Chat novo é criado — devolver o antigo readmitiria em silêncio quem saiu.

## Tempo real (WebSocket + Redis)

Duas famílias de canais Redis pub/sub, uma por instância do backend (ver [ADR-0003](../docs/adr/0003-redis-pubsub-for-horizontal-scaling.md) e [`docs/architecture.md`](../docs/architecture.md) para o diagrama completo):

- `chat:{id}` — corpo da mensagem, entregue a quem tem aquele chat aberto no WebSocket. Cada instância faz um único `PSUBSCRIBE chat:*` (não subscribe/unsubscribe por chat), evitando race de reference-counting ao abrir/fechar várias abas.
- `user:{company_id}:{user_id}` — resumo leve ("esse chat mudou"), entregue a todo participante independente de qual chat está aberto; é o que mantém a prévia da última mensagem viva na lista de chats sem cada cliente assinar todos os chats de que participa. A Company entra na chave do canal porque o mesmo id de usuário pode existir em duas delas (ver "Isolamento por Company").

Endpoints: `WS /websocket/chats/{id}` e `WS /websocket/users/me`, ambos autenticados via chat token como query param `token` (o handshake do WebSocket não carrega header `Authorization` customizado). Isso tem um custo: query strings tendem a ser gravadas em logs de acesso de proxies/ALB e no histórico do navegador, diferente de um header — trade-off não documentado em nenhum ADR até agora. A alternativa mais comum é conectar sem token e autenticar pela primeira mensagem do socket.

Se a conexão com o Redis cair, `run_subscriber` (`app/services/realtime.py`) simplesmente morre — sem log, sem retry, sem healthcheck que detecte isso. A entrega em tempo real para silenciosamente até o processo ser reiniciado.

## Autenticação

JWT de acesso de curta duração + refresh token opaco (ver [ADR-0004](../docs/adr/0004-jwt-in-localstorage.md) para o trade-off de guardar o JWT em `localStorage`). Duas decisões do refresh token, não cobertas na ADR:

- **Hash com SHA-256, não bcrypt.** O refresh token é um valor aleatório de alta entropia, não uma senha de baixo espaço de busca — o que ele precisa é um lookup indexado por igualdade exata, não uma comparação lenta e salgada pensada para resistir a brute-force de senha.
- **Sem rotação no uso.** Cada refresh token continua válido até expirar (7 dias) ou até logout explícito — não há esquema de rotate-and-detect-reuse. Um token vazado permanece utilizável nesse intervalo; simplificação deliberada dentro do escopo de "auth simplificada" do desafio, rotação seria o próximo passo de hardening.

## Webhook

`POST /webhook/messages` permite que um sistema externo entregue uma mensagem em um chat existente, autenticado por uma assinatura HMAC de segredo compartilhado em vez de um JWT.

**Request:**

- Body (JSON): `{ "company_id": "<uuid>", "chat_id": "<uuid>", "body": "<texto>", "source_label": "<string, opcional>" }` — `company_id` é a Company em que a mensagem está sendo escrita, e o chat é lido dentro dela: apontar para um chat de outra Company responde `404`, igual a um chat que não existe. `source_label` identifica o remetente externo na UI (ex.: `"Shipping Bot"`); omita ou envie `null` para um fallback genérico.
- Header `X-Signature`: `HMAC-SHA256(WEBHOOK_HMAC_SECRET, raw_request_body_bytes)` em hexadecimal.

A assinatura deve ser calculada sobre os **bytes exatos** enviados como corpo da requisição — reserializar o JSON (ordem de chaves diferente, espaços em branco) antes de assinar produz uma assinatura que falha na verificação, já que o servidor faz hash dos bytes brutos recebidos em vez de recodificar o payload já parseado.

Exemplo (Python):

```python
import hmac, hashlib, httpx

body = b'{"company_id": "0f1d6c21-9a1e-4f7a-9c2b-0f4b1a7e3d55", "chat_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "body": "Your order shipped!", "source_label": "Shipping Bot"}'
signature = hmac.new(settings.webhook_hmac_secret.encode(), body, hashlib.sha256).hexdigest()

httpx.post(
    "http://localhost:8000/webhook/messages",
    content=body,
    headers={"X-Signature": signature, "Content-Type": "application/json"},
)
```

**Respostas:** `401` se a assinatura estiver ausente/inválida (checado antes de qualquer acesso ao banco), `404` se `chat_id` não referenciar um chat existente **dentro de `company_id`**, `201` com a mensagem criada em caso de sucesso — entregue em tempo real aos participantes conectados do chat pelo mesmo caminho Redis/WebSocket de uma mensagem normal.

**Lacunas conhecidas** (ver `docs/decisions.md`):

- Sem proteção contra replay — uma requisição válida capturada pode ser reenviada.
- Sem forma segura de o sistema externo descobrir qual `chat_id` usar — ele precisa já saber o UUID de antemão.
- **O segredo HMAC é um só para todas as Companies.** O payload agora nomeia a `company_id` e um chat de outra Company é recusado, mas nada amarra a assinatura àquela Company: quem tem o segredo pode assinar um payload nomeando qualquer Company. Ticket 14 dá a cada Company um segredo próprio.
- Sem checagem de que o `chat_id` pertence a um participante — dentro da Company certa, qualquer chamador com o segredo pode injetar mensagem em qualquer chat cujo UUID conheça.

## Testes

TDD, red-green-refactor conforme o `CLAUDE.md` do repositório — os testes são escritos junto com cada comportamento, não depois.

```
uv run pytest
```

As respostas de `Chat` retornam participantes ordenados por `user_id`, e essa ordenação é um `order_by` explícito no relacionamento, não um efeito colateral do plano de execução do Postgres — a distinção custou o RED de um teste de regressão do ticket 23, que passava mesmo sem o fix pretendido. `tests/test_chat_model.py` falha se o `order_by` sair.

## Staff-only Message

Uma **Staff-only Message** é uma mensagem dentro de um Client Chat visível só para os Participants da Company. O cliente final não a recebe e não descobre que ela existe.

Essa é a regra com o pior histórico de falha do módulo de origem, registrado na [ADR-0008](../docs/adr/0008-domain-rewritten-in-fastapi.md): um Participant carregado por relação voltava como a classe-base de usuário, um `isinstance` respondia "não" para um funcionário, e a regra falhava **em silêncio nas duas direções** — às vezes tirando funcionários do próprio fan-out, às vezes mantendo um cliente final dentro dele.

O que aquele bug era de verdade: a regra era avaliada em mais de um lugar, sobre um valor que ninguém tinha fixado. Então aqui ela é **uma função pura** em `app/core/message_visibility.py`, irmã de `company_scope.py`, sobre quatro argumentos e nada mais — sem sessão, sem relação para carregar, sem linha cuja classe possa surpreendê-la:

```
may_read(reader_kind, reader_company_id, chat_company_id, chat_type, visibility) -> bool
```

- Company do leitor diferente da Company do Chat → **não**.
- `reader_kind` fora de `staff`/`client` → **não**, para toda visibilidade — e, porque a escrita passa pelo mesmo predicado, esse remetente também não escreve nada, nem mensagem comum. Esse é o ramo **default-deny**, e é a forma re-introduzível do bug: um token pode reivindicar qualquer kind e o serviço não tem tabela de usuários para conferir. Uma thread vazia é uma falha que alguém reporta; uma Staff-only Message vazada é uma que ninguém vê.
- `visibility = all` → **sim**.
- `visibility = staff_only` → só em Client Chat, e só para `staff`.

O predicado não diz nada sobre pertencimento: se o leitor tem lugar no Chat é pergunta separada, respondida por `chat_of_participant` antes desta.

**Nenhum caminho de leitura reescreve a regra.** `readable_visibilities` monta o `WHERE` perguntando ao próprio `may_read` sobre cada visibilidade, em vez de restatá-la em SQL — uma segunda grafia seria uma segunda coisa para manter em dia, e as duas divergiriam na primeira vez que só uma fosse atualizada. Três leituras passam por ela:

- `GET /chats/{id}/messages` filtra o histórico. Como a ordenação é por `created_at` e não por posição, a mensagem omitida **não deixa buraco**: o cliente final vê uma lista contígua, sem nada indicando que faltou algo.
- `GET /chats` tira `last_message_at` só do que o leitor pode ler. Esse campo é o timestamp exibido ao lado do Chat **e** a chave da ordenação — sem filtro ele avançaria e flutuaria o Chat para o topo toda vez que o staff dissesse algo que o cliente final não pode ler, anunciando a Staff-only Message sem citá-la.
- `POST /chats/{id}/messages` valida a escrita com o **mesmo** predicado: quem escreve só endereça uma mensagem a um conjunto do qual faz parte. Isso torna `422` tanto uma staff-only num Staff Chat (não há ninguém lá para excluir, a restrição não significa nada) quanto uma escrita por cliente final (ele escreveria algo que não poderia depois ler) — sem uma segunda regra para alguém manter em dia. Recusar é melhor que guardar como mensagem comum: um rebaixamento silencioso diz ao remetente que a mensagem foi restrita quando não foi.

`tests/test_message_visibility.py` cobre a tabela-verdade como função pura; `tests/test_messages.py` prova pela borda que ela está ligada. A regra é testada duas vezes de propósito — o teste de API prova a ligação, o unitário prova o ramo default-deny, que é quase inalcançável pela API.

## Isolamento por Company

Nenhuma leitura atravessa uma Company. A [ADR-0007](../docs/adr/0007-own-database-company-boundary-in-code.md) tirou esse isolamento do banco e o deixou no código, e chamou isso de risco central da arquitetura: sem um queryset carregando o invariante, todo caminho de leitura precisa filtrar por Company explicitamente, e um que esqueça vaza os chats de uma Company para outra.

O piso que substitui o queryset é `app/core/company_scope.py`:

- Toda linha legível carrega sua Company (`CompanyScoped` — `chats`, `participants`, `messages`).
- Toda leitura de uma dessas entidades nasce de `CompanyScope.select`, que tira a Company do token de quem chamou. Nenhum serviço ou router monta a própria query, e nenhum router constrói o próprio escopo: ele chega pela dependência `get_company_scope` (`app/core/security.py`).
- O canal de lista de chats do Redis é `user:{company_id}:{user_id}`, não `user:{user_id}`. O mesmo id de usuário pode existir em duas Companies, e o resumo de Chat empurrado por `/websocket/users/me` carrega id, nome e participantes — chaveado só por usuário, ele cairia no socket aberto com o token da outra Company.
- O filtro cai no `WHERE`, então uma linha de outra Company não é proibida, é **ausente**: um pedido cruzando a fronteira e um pedido por algo que nunca existiu devolvem `404` com o mesmo corpo, e nada na resposta distingue os dois.

`tests/test_company_isolation.py` cobre cada caminho de leitura e, por último, faz um teste estrutural: ele varre a AST de todo o `app/` atrás de `select(E)`, `sa.select(E)`, `session.get(E, ...)`/`get_one` e `session.query(E)` sobre uma entidade escopada fora do módulo de escopo, e falha apontando arquivo e linha. O conjunto de entidades escopadas sai do registry do SQLAlchemy, não de uma lista escrita à mão, então uma entidade nova entra na varredura assim que é mapeada.

**Ao adicionar uma entidade legível nova, acrescente o teste de isolamento dela** — o teste estrutural garante que a query passe pelo escopo, não que alguém tenha verificado o comportamento pela borda. Dois limites que ele não cobre, e que o teste documenta: ele reconhece `scope.select(...)` pela grafia do receptor (não por tipo), e `text("SELECT ...")` cru é invisível para ele. **Fan-out também não é leitura de query**: um caminho que empurra dados por canal (Redis, WebSocket) precisa carregar a Company na própria chave do canal — foi assim que `/websocket/users/me` vazou antes de ser corrigido.

O webhook é o único chamador sem token: ele nomeia a Company no próprio payload (veja a seção Webhook) e lê o chat dentro dela.

## Débito técnico conhecido

Não bloqueia o funcionamento hoje, mas seria o primeiro ponto de atenção antes de qualquer uso com carga real:

- **BLOQUEADOR DE PRODUÇÃO: o chat token ainda é HS256.** `app/core/chat_token.py`
  verifica com um segredo compartilhado, então o serviço **consegue emitir um
  token que ele próprio aceita**. O [ADR-0009](../docs/adr/0009-chat-owns-token-in-rs256.md)
  foi aceito justamente para remover essa propriedade e ainda não está
  implementado. Ticket 19 troca por RS256 + `kid` + JWKS + `aud` obrigatório.
  Nada abaixo desta linha é um risco da mesma ordem.
- **Uma Staff-only Message ainda vaza no WebSocket.** `publish_message` manda toda mensagem para o canal único `chat:{id}`, que todo Participant conectado lê, e o resumo de `user:{company_id}:{user_id}` carrega `last_message_at` sem filtro. A regra vale na API e ainda não no transporte. Fechar isso é o ticket 07, que dá à staff da Company um endereço próprio — o isolamento vem do endereço, não de um `if` que todo emissor futuro precise lembrar de escrever.
- **Sem índice em `messages.chat_id`.** Nenhuma migração cria esse índice — `list_messages` (filtra por `chat_id`, ordena por `created_at`) e a busca da última mensagem por chat fazem table scan à medida que o histórico cresce.
- **Índice de `participants` favorece a query errada.** O `UniqueConstraint(chat_id, user_id)` serve bem a checagem de membership, mas `list_chats` — chamada a cada carregamento da sidebar — filtra só por `user_id`; faltaria um índice dedicado liderado por esse campo.
- **Sem rate limiting** em `/webhook/messages`.
- **Sem paginação** em nenhuma listagem (`GET /chats`, `GET /chats/{id}/messages`) — todas devolvem o conjunto inteiro.
- **Zero logging estruturado** em todo o `app/` — combinado com o subscriber Redis sem tratamento de falha (acima), é o ponto mais arriscado de operar isso em produção sem visibilidade.

## Migrations

```
uv run alembic revision --autogenerate -m "message"
uv run alembic upgrade head
```

`alembic/env.py` lê a URL do banco a partir de `app.core.config.settings` (ou seja, do `.env`), não do `alembic.ini`.
