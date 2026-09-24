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
├── drain.py    # processo do drain do outbox (entrypoint próprio)
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

### Composição é um comando, não um pedido do browser

Criar um Chat e adicionar ou remover um Participant deixaram de ser coisas que um browser pede ao serviço.
O monolito valida contra dado vivo — pertencimento à Company, se a pessoa está ativa e, para um cliente
final, a relação de contato no CRM, que é consulta impossível de espelhar — e então **chama o serviço**
([ADR-0010](../docs/adr/0010-no-request-depends-on-the-monolith.md)). Nenhum caminho de request do serviço
consulta o monolito, e esta é a operação onde dado velho doeria mais: quem entra num Chat lê tudo que foi
dito nele desde que ele foi criado.

Não existe endpoint público que crie Chat ou adicione Participant, e não existe endpoint que **liste quem
pode participar** — quem é cliente de uma Company é fato de CRM, não fato de chat, e espelhar isso seria
espelhar a agenda de contatos e a rotatividade dela. `tests/test_composition_commands.py` falha se qualquer
uma das duas voltar.

#### As três rotas de composição

A ingress interna tem cinco rotas sob `/internal`: as três de composição abaixo e as duas da projeção de
identidade, descritas em "Projeção de identidade". Todas as cinco são autenticadas por
`Authorization: Bearer $INTERNAL_SERVICE_TOKEN`; só as três de composição exigem, além disso, **dois headers
nomeando o usuário por quem o monolito age**. As da projeção não os exigem de propósito — não existe Chat sem
autor, mas o nome de um usuário mudando no monolito não tem autor para nomear.

| Header | O quê |
| --- | --- |
| `X-Acting-User` | identificador de quem está agindo |
| `X-Acting-Company` | a Company dele — id de usuário sozinho não nomeia ninguém aqui, o mesmo id pode existir em duas Companies |

Faltar qualquer um dos dois numa rota de composição é recusa (`401`), não default: é isso que impede a
credencial de serviço de virar uma credencial onipotente — ela não amplia o que pode ser feito, só permite
fazer em nome de alguém identificado. A Company nomeada no header é a Company em que o comando escreve.

- `POST /internal/chats` — cria o Chat.
- `POST /internal/chats/{id}/participants` — coloca alguém no Chat.
- `DELETE /internal/chats/{id}/participants/{user_id}` — tira alguém do Chat.

O comando **carrega a identidade de cada Participant** (identificador, Company, kind, display name, avatar),
porque o monolito já tinha esse dado em mãos para validar — mandar junto não custa nada e elimina o único
caso que forçaria o serviço a perguntar de volta. `display_name` é obrigatório: um comando que nomeia só um
identificador descreve alguém que o serviço nunca conseguiria renderizar. O display name e o avatar viram a
primeira escrita da projeção de identidade, descrita abaixo.

```http
POST /internal/chats
Authorization: Bearer <INTERNAL_SERVICE_TOKEN>
X-Acting-User: <uuid>
X-Acting-Company: <uuid>

{
  "type": "staff",
  "name": null,
  "participants": [
    {
      "user_id": "<uuid>",
      "company_id": "<uuid>",
      "user_kind": "staff",
      "display_name": "Ana Souza",
      "avatar_url": null
    }
  ]
}
```

O Chat guarda quem foi composto por ele: `chats.created_by_user_id` recebe o `X-Acting-User` do comando.
Nada lê essa coluna num caminho de request — ela existe para que "não existe Chat sem autor" seja respondível
depois, e não só barrado na porta. Nulo lá significa um Chat anterior ao ticket 05, aberto por um browser com
token próprio, de quem o serviço nunca soube o nome.

O comando nomeia **todo mundo** e o serviço não acrescenta ninguém — inclusive quem está agindo, se ele
estiver no Chat. A resposta é o Chat como o comando o deixou (`id`, `type`, `name`, `participant_user_ids`)
e não carrega `last_message_at`: esse campo é relativo ao leitor — é o timestamp da última mensagem que
*aquele* leitor pode ver — e um comando não tem leitor para preenchê-lo.

#### O que o serviço valida, e o que ele não revalida

O serviço não revalida o que quem assinou o comando já é autoridade sobre. Ele valida a **forma** do Chat,
que é invariante dele, e responde `422`:

- `a staff chat cannot contain an end client` — Staff Chat é definido pela ausência do cliente final.
- `name is required for group chats` — grupo (3+ Participants) precisa de nome; 1:1 não.
- `a participant from outside the company the command acts for` — o Chat e seus Participants respondem à
  mesma fronteira, ou o comando falha; se pudessem divergir, `list_chats` juntaria através de Companies.
- um `user_kind` fora de `staff`/`client` não tem lugar em regras escritas nessas duas palavras, e o schema
  o recusa antes de virar linha.

A forma é propriedade do Chat, não do instante em que ele foi alcançado: `_validate_shape` é a mesma função
na criação e na adição. Checada só na entrada, a regra teria atalho — abra o Staff Chat, depois adicione o
cliente — e a regra de visibilidade do ticket 04 leria um Chat cujo tipo diz que não há de quem esconder uma
Staff-only Message. É por isso que `POST /internal/chats/{id}/participants` aceita um `name`: adicionar um
terceiro transforma um 1:1 em grupo, e mandar o nome junto é um ato de composição em vez de dois.

#### Repetir um comando

Composição chega **at-least-once**, então repetir é o comando já ter dado certo, e não um erro:

- abrir um 1:1 que já existe devolve o Chat existente ([ADR-0002](../docs/adr/0002-explicit-idempotent-chat-creation.md));
  se alguém saiu dele, aquele 1:1 já não existe como tal e um Chat novo é criado — devolver o antigo
  readmitiria em silêncio quem saiu;
- adicionar quem já está no Chat não muda nada; nomear de novo quem saiu **revive a linha** em vez de criar
  uma segunda, que é a única leitura que a unique constraint em (Chat, usuário) permite;
- remover quem já saiu não move o instante em que ele saiu — uma reentrega não é uma segunda saída;
- remover quem nunca esteve lá é `404`, igual a um Chat de outra Company e a um Chat que não existe.

#### Monolito fora do ar

Composição falha e todo Chat existente continua mandando e recebendo normalmente. Isso não é disciplina, é
estrutural: `tests/test_composition_commands.py` falha se qualquer módulo de `app/` passar a importar um
cliente HTTP, porque no instante em que um existe aqui dentro, o primeiro "só pergunta pro monolito se esse
usuário ainda está ativo" está a uma linha de distância — e vai ser escrito dentro de um request, onde o
monolito lento vira o chat lento.

## Projeção de identidade

O serviço sabe o nome e o avatar de um usuário sem nunca perguntar ao monolito na hora do request — a
[ADR-0010](../docs/adr/0010-no-request-depends-on-the-monolith.md) proíbe esse caminho, então o nome precisa
já estar aqui quando a resposta é montada. `user_profiles` é onde ele está: Company, user kind, display name,
avatar, `source_updated_at` e `synced_at`, com chave única em `(company_id, user_id)` — o mesmo id de usuário
pode existir em duas Companies, exatamente pelo motivo que põe a Company em todo endereço de fan-out.

**Nenhuma tabela de mensagem guarda nome, email ou avatar.** A mensagem guarda o identificador e mais nada; o
nome é resolvido da projeção quando a resposta é construída. É isso que faz uma anonimização no monolito
alcançar o histórico do chat: uma linha de perfil reescrita e toda mensagem que aquele usuário já mandou passa
a ser assinada diferente, sem o serviço precisar saber o que é uma lei de proteção de dados. Denormalizar o
nome na mensagem "para economizar um join" quebra isso em silêncio e só para o passado — mensagens novas
parecem certas e o histórico mantém o nome de quem pediu para ser esquecido.
`tests/test_identity_projection.py` falha se uma coluna dessas aparecer em qualquer tabela de mensagem, e
acha as tabelas em vez de listá-las, para que a próxima cobrir-se sozinha.

### As três escritas de entrada

Todas idempotentes, porque todas chegam at-least-once. Nenhuma delas tem caminho de miss: nada aqui busca uma
identidade que não tem, e um nome que a projeção nunca ouviu falar simplesmente não vem na resposta.

- **O comando de composição.** `POST /internal/chats` e `POST /internal/chats/{id}/participants` já carregam a
  identidade de cada Participant, então criar o Chat é o que ensina os nomes. Na prática a projeção conhece
  qualquer usuário antes dele entrar em qualquer coisa.
- **O stream de eventos.** `POST /internal/identity-events`, um usuário por vez.
- **A carga em massa.** `POST /internal/identities`, para popular um ambiente novo ou reconstruir uma projeção
  corrompida sem reprocessar todo o histórico.

As duas últimas exigem só a credencial de serviço, sem header de ator — diferente dos comandos acima. Não
existe Chat sem autor, mas o nome de um usuário mudando no monolito não tem autor para nomear, e exigir um
seria pedir ao monolito que inventasse. A Company vem do próprio payload, do mesmo jeito que o webhook já faz.

### A ordem é decidida por `source_updated_at`, não por chegada

Last-writer-wins pelo relógio do **monolito**, comparado dentro do banco em vez de ler-e-então-escrever, para
que dois eventos do mesmo usuário correndo em dois workers não leiam ambos a linha velha e decidam ambos que
são os mais novos. Sem isso, um evento reentregue com dias de atraso reinstala o nome que carregava — que é o
defeito que essa projeção existe para impedir, e aparece como um usuário cujo nome antigo volta sem que
ninguém consiga reproduzir.

A identidade que vem no comando de composição não tem `source_updated_at`: `ParticipantIdentity` é o formato
de fio que o ticket 05 fixou, e fazer a projeção aterrissar não podia mexer nele. Ela assume então a única
leitura que sobra — uma identidade de idade desconhecida é a coisa mais velha que existe, então cria a linha
quando ninguém falou daquele usuário ainda e nunca sobrescreve o que algo datado já disse.

**Não há tabela de event ids vistos.** `event_id` é obrigatório no fio e é o que torna um replay legível num
log, mas a deduplicação por ele seria um segundo mecanismo para algo que o `source_updated_at` já resolve: um
evento reentregue carrega o timestamp que carregava da primeira vez, a comparação é estrita, e timestamp igual
perde. Um replay não escreve nada, chegando uma ou dez vezes, em qualquer ordem, intercalado com qualquer
coisa. No instante em que essa ingress ganhar trabalho que não é idempotente por construção — uma linha de
outbox na saída, que é o ticket 15 — o timestamp deixa de cobrir e a tabela passa a ser estrutural. Ela
pertence àquele trabalho, não a este.

Uma carga em massa que nomeia o mesmo usuário duas vezes é reduzida ao snapshot mais novo antes de escrever.
Postgres se recusa a deixar um único `ON CONFLICT DO UPDATE` tocar a mesma linha duas vezes, e um rebuild é
justamente a escrita que plausivelmente carrega um usuário repetido — duas páginas costuradas, ou um usuário
que mudou enquanto o export rodava. Sem a regra não é uma linha perdida, é a carga inteira falhando.

### O sinal de saúde é o lag

`projection_lag(db)` (`app/services/projection_health.py`) devolve a maior distância entre `source_updated_at`
e `synced_at`. Não há hit rate de cache para observar, porque não há caminho de miss: um stream parado é
invisível por dentro — toda resposta continua respondendo, rápido, com um nome silenciosamente velho. A maior
distância e não uma média, porque a média esconderia o único usuário cujas atualizações pararam de chegar
atrás de milhares que estão bem. Linhas sem `source_updated_at` ficam de fora e não são lag: vieram de um
comando de composição, que não carrega timestamp nenhum para medir contra.

Como `oldest_unpublished_age`, é uma função hoje e o ticket 18 é quem a transforma em algo monitorado. Ela não
passa por `CompanyScope` — quem observa isso é um operador, que não tem token nem Company, e um lag calculado
por Company esconderia a que parou atrás das que estão bem. Por isso mora num módulo só dela: a isenção em
`tests/test_company_isolation.py` é por entidade e só pode ser declarada por arquivo, e `profiles_by_user_id`,
que **é** uma leitura em nome de um usuário, continua guardada em `app/services/identity.py`.

## Tempo real: outbox, drain e três endereços

A entrega deixou de acontecer dentro do request. O que o request faz é **escrever a linha** que descreve a entrega, na mesma transação da mensagem que ela anuncia; um **drain** separado publica depois. Isso compra as duas metades da mesma garantia: ninguém é avisado de uma mensagem que um rollback vai apagar, e nada se perde se o processo morrer entre o commit e o publish.

### Os três endereços

Ver [ADR-0003](../docs/adr/0003-redis-pubsub-for-horizontal-scaling.md) e [`docs/architecture.md`](../docs/architecture.md) para o diagrama. Cada instância faz `PSUBSCRIBE chat:*` e `user:*` uma única vez — não subscribe/unsubscribe por chat, o que evitaria race de reference-counting ao abrir e fechar várias abas.

- `chat:{company_id}:{chat_id}` — corpo da mensagem, para todo mundo no Chat.
- `chat:{company_id}:{chat_id}:staff` — só para a staff da Company naquele Chat. É para cá que vai uma **Staff-only Message**, e para lugar nenhum além.
- `user:{company_id}:{user_id}` — resumo leve ("esse Chat mudou"), para manter a prévia viva na lista sem cada cliente assinar todos os seus chats.

**O isolamento vem do endereço.** Nada no caminho de entrega lê uma regra ou aplica um filtro: quem pode ver um payload foi decidido quando a linha foi endereçada, e o subscriber encaminha por nome de canal sem saber o que é um Chat ou um user kind. A alternativa — um grupo por Chat mais um `if` na entrega — é justamente o `if` que todo emissor futuro precisa lembrar de escrever, e o defeito da [ADR-0008](../docs/adr/0008-domain-rewritten-in-fastapi.md) foi exatamente uma regra avaliada em mais de um lugar.

O socket entra nos endereços a que seu portador tem direito **no handshake**, decidido pelo mesmo `may_read` que a API usa. O socket do cliente final nunca entrou no endereço staff — por isso não há nada para filtrar depois.

A Company está nos três endereços. Para um usuário ela é estrutural: o mesmo id pode existir em duas Companies e um resumo publicado para uma cairia no socket aberto com o token da outra. Para um Chat é cinto sobre cinto já afivelado — um id de Chat já é único — e está lá porque a regra em "Isolamento por Company" é que caminho de fan-out carrega a Company na chave do canal, sem exceção para lembrar.

### O drain

`drain_once(db)` (`app/services/outbox.py`) processa o lote pendente uma vez e retorna quantas linhas saíram. Um único callable serve aos dois consumidores: o processo de produção (`app/drain.py`, contêiner `drain` no compose) o chama em laço, e os testes o chamam entre enviar e asserir. Isso é deliberado — um drain que só pudesse ser observado esperando uma tarefa de fundo faria de cada teste de tempo real uma corrida.

Cada linha é tomada com `FOR UPDATE SKIP LOCKED`, **uma por transação**. É isso que torna o drain seguro em mais de uma réplica: uma linha que outro drain já segura é pulada em vez de esperada, então as réplicas dividem o backlog em vez de publicarem tudo em duplicata. Travar o lote inteiro não serviria — o primeiro commit solta todas as travas da transação e deixa o resto do lote desguardado enquanto ainda está sendo processado.

Cada linha é **publicada e só então marcada**. A ordem é a escolha de **at-least-once**: morrer depois do publish e antes da marca reentrega aquela linha na próxima rodada, enquanto marcar antes a descartaria em silêncio. Um frame duplicado é visível e deduplicável pelo id da mensagem; um frame que ninguém mandou não é nenhum dos dois.

Falha no drain é registrada em log e repetida, não fatal — seguro exatamente por causa dessa ordem: uma queda do Redis deixa toda linha não entregue pendente, e o backlog se drena sozinho quando o Redis volta. O que uma queda dessas move é `oldest_unpublished_age`, o sinal de saúde do tempo real, que o ticket 18 transforma em algo monitorado. É idade e não contagem porque mil linhas escritas há um segundo é um serviço movimentado e uma linha escrita há dez minutos é um drain parado, e uma contagem não distingue os dois.

Endpoints: `WS /websocket/chats/{id}` e `WS /websocket/users/me`, ambos autenticados via chat token como query param `token` (o handshake do WebSocket não carrega header `Authorization` customizado). Isso tem um custo: query strings tendem a ser gravadas em logs de acesso de proxies/ALB e no histórico do navegador, diferente de um header — trade-off não documentado em nenhum ADR até agora. A alternativa mais comum é conectar sem token e autenticar pela primeira mensagem do socket.

Se a conexão com o Redis cair, `run_subscriber` (`app/services/realtime.py`) simplesmente morre — sem log, sem retry, sem healthcheck que detecte isso. O lado de **publicação** deixou de depender disso (as linhas ficam pendentes e saem quando o Redis volta), mas o lado de **entrega** de uma instância cujo subscriber morreu continua parado em silêncio até o processo ser reiniciado.

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
- O handshake do WebSocket usa o predicado para decidir em quais endereços o socket entra (ver "Tempo real"). O socket do cliente final nunca entra no endereço staff, então a regra vale no transporte sem nenhum filtro na entrega.
- `POST /chats/{id}/messages` valida a escrita com o **mesmo** predicado: quem escreve só endereça uma mensagem a um conjunto do qual faz parte. Isso torna `422` tanto uma staff-only num Staff Chat (não há ninguém lá para excluir, a restrição não significa nada) quanto uma escrita por cliente final (ele escreveria algo que não poderia depois ler) — sem uma segunda regra para alguém manter em dia. Recusar é melhor que guardar como mensagem comum: um rebaixamento silencioso diz ao remetente que a mensagem foi restrita quando não foi.

`tests/test_message_visibility.py` cobre a tabela-verdade como função pura; `tests/test_messages.py` prova pela borda que ela está ligada. A regra é testada duas vezes de propósito — o teste de API prova a ligação, o unitário prova o ramo default-deny, que é quase inalcançável pela API.

## Isolamento por Company

Nenhuma leitura atravessa uma Company. A [ADR-0007](../docs/adr/0007-own-database-company-boundary-in-code.md) tirou esse isolamento do banco e o deixou no código, e chamou isso de risco central da arquitetura: sem um queryset carregando o invariante, todo caminho de leitura precisa filtrar por Company explicitamente, e um que esqueça vaza os chats de uma Company para outra.

O piso que substitui o queryset é `app/core/company_scope.py`:

- Toda linha legível carrega sua Company (`CompanyScoped` — `chats`, `participants`, `messages`, `outbox`).
- Toda leitura de uma dessas entidades nasce de `CompanyScope.select`, que tira a Company do token de quem chamou. Nenhum serviço ou router monta a própria query, e nenhum router constrói o próprio escopo: ele chega pela dependência `get_company_scope` (`app/core/security.py`).
- O canal de lista de chats do Redis é `user:{company_id}:{user_id}`, não `user:{user_id}`. O mesmo id de usuário pode existir em duas Companies, e o resumo de Chat empurrado por `/websocket/users/me` carrega id, nome e participantes — chaveado só por usuário, ele cairia no socket aberto com o token da outra Company.
- O filtro cai no `WHERE`, então uma linha de outra Company não é proibida, é **ausente**: um pedido cruzando a fronteira e um pedido por algo que nunca existiu devolvem `404` com o mesmo corpo, e nada na resposta distingue os dois.

As exceções do teste estrutural são nomeadas **por entidade**, não por arquivo: `app/services/outbox.py` pode ler `OutboxEvent` e só isso, porque o drain não tem chamador, nem token, nem Company — e é seguro porque a Company já foi decidida dentro do endereço quando a linha foi escrita. Um `select(Chat)` crescendo dentro do drain continua sendo apontado.

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
- **Uma linha ruim para o tempo real inteiro.** `drain_once` sempre pega a linha pendente **mais antiga**. Se publicá-la falhar de forma permanente, `run_forever` captura, dorme e pega a mesma linha de novo — para sempre — e tudo atrás dela nunca sai. Não é entrega degradada: é tempo real parado para o serviço todo por causa de uma linha. Hoje o drain só faz `redis.publish`, onde o que falha é conexão e isso derruba todas as linhas igualmente, então o raio é grande e a probabilidade baixa; ela sobe no ticket 15, que põe HTTP para o monólito no mesmo caminho. Ticket 21.
- **A tabela `outbox` cresce sem coletor.** A linha publicada fica com `published_at` preenchida em vez de ser apagada, o que dá rastro de o que saiu e quando — é o que o ticket 18 monitora e o que responde "esse evento saiu?" depois de um incidente. Nada poda as linhas antigas ainda. O índice do drain é parcial (`WHERE published_at IS NULL`), então a varredura não degrada junto; o que cresce é o disco. Ticket 21.
- **As rotas internas não são inalcançáveis da internet, só autenticadas.** O ALB do `infra/` encaminha todo
  caminho para o mesmo target group, `/internal/*` incluso, e a credencial de serviço é a única tranca. Bloquear
  o caminho público hoje deixaria a composição sem nenhuma entrada — o monolito ainda não tem presença na VPC —
  então as duas metades andam juntas no ticket 18: por onde o monolito entra, e o fechamento da rua.
- **Criar grupo não é idempotente.** O 1:1 devolve o Chat existente ([ADR-0002](../docs/adr/0002-explicit-idempotent-chat-creation.md)),
  mas um comando de criação de grupo reentregue cria um segundo Chat com as mesmas pessoas e o mesmo nome.
  A composição chega at-least-once; adicionar e remover são idempotentes, criar grupo não é. O que resolve é
  uma chave de idempotência no comando, como a do ticket 08 para mensagens.
- **Entrar e sair de um Chat não são atribuídos.** O Chat guarda quem o compôs (`chats.created_by_user_id`),
  mas `participants` não guarda quem adicionou nem quem removeu — nesses dois comandos o `X-Acting-User`
  continua sendo só condição para passar.
- **O drain não existe fora do `docker-compose.yml`.** `infra/` define uma task definition e um service, ambos `backend`. Um deploy sem o processo de drain armazena tudo e entrega nada em tempo real, em silêncio. Ticket 20.
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
