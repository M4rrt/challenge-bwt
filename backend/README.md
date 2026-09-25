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
- **Participant** carrega Chat, identificador do usuário, Company, papel (`staff` | `client`), `joined_at`, `left_at` e o estado de leitura (`last_read_at`, `last_read_message_id`) — a marca d'água que o ticket 09 passou a ler e escrever; ver "Ler: paginação por cursor, marca d'água e não lidas".
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

### A conexão ao vivo: renovação em banda, revalidação e três close codes

Um socket é longo e a credencial dele não é. A [ADR-0011](../docs/adr/0011-revocation-at-the-next-token.md) reconcilia os dois **em banda**: o serviço avisa pouco antes de expirar, o cliente manda um token novo pelo mesmo socket, e o serviço revalida. A alternativa — fechar e deixar reconectar — custa uma query de recuperação a cada quinze minutos e abre uma janela em que mensagem se perde.

O prazo continua existindo como rede de segurança, e ter os dois é o ponto: só o prazo custa uma recuperação por token; só a renovação deixa um caminho em que esquecer de reagendar o prazo mantém a conexão viva para sempre — e esse defeito é silencioso.

**Os frames** (`app/services/connection.py` nomeia cada um em uma constante, para que o nome exista em um lugar só):

| direção | `type` | conteúdo |
| --- | --- | --- |
| serviço → cliente | `token.expiring` | `expires_at` — vá buscar um token novo |
| cliente → serviço | `token.renew` | `token` — o novo, por este mesmo socket |
| serviço → cliente | `token.renewed` | `expires_at` — aceito, revalidado, a conexão segue |

O aviso sai `RENEWAL_WARNING_LEAD` (60s) antes do `exp` do token. Um `type` que o serviço não conhece continua sendo ignorado, como sempre foi.

**A renovação revalida as duas coisas**: o token *e* a autorização no Chat. Um token que verifica não é a mesma afirmação que um Chat que continua sendo seu — sair de um Chat não aparece em claim nenhuma. O token novo também precisa nomear a **mesma pessoa na mesma Company**: os endereços do socket foram decididos num handshake que já acabou, e aceitar token de outra pessoa entregaria o fan-out de uma para a outra.

**Revalidação periódica** (`REVALIDATION_INTERVAL`, 60s) por cima disso. Ela limita a **um intervalo** — em vez de a um tempo de vida de token — a janela entre uma escrita deste lado e o socket perceber: um Participant removido cuja expulsão não chegou (drain parado, instância que perdeu o frame) e uma entrada de denylist que apareceu enquanto ninguém estava renovando.

**O que ela não faz sozinha é reler uma claim.** Uma desativação e um escopo de supervisão perdido moram no token, e o token não muda entre renovações — rodar o mesmo predicado contra o mesmo `Caller` deriva a mesma resposta, por mais vezes que rode. Esses dois são cobertos pela **renovação** (o monólito emite o próximo token sem o escopo, ou não emite) e, quando um tempo de vida é demais, pelo **denylist**. A [ADR-0011](../docs/adr/0011-revocation-at-the-next-token.md) credita "revalida periodicamente e em toda renovação" com cobrir os dois, e é o par que cobre; a metade periódica sozinha cobre o que este serviço consegue ver por si — ele não tem tabela de usuários para consultar, e consultar o monólito é o que a [ADR-0010](../docs/adr/0010-no-request-depends-on-the-monolith.md) proíbe.

A **renovação** é o que fecha a lacuna que o ticket 07 registrou contra si mesmo: o endereço staff era escolhido no handshake e o handshake nunca era revisitado, então um Participant cujo `user_kind` virasse `client` seguia recebendo Staff-only Message pelo resto daquela conexão. Hoje ele simplesmente deixa de ouvir o endereço que perdeu, sem cair — continua no Chat, só tem direito a um endereço menos. É a renovação e não o tique periódico pela razão do parágrafo acima: `user_kind` é uma claim, então quem a vê mudar é quem recebe um token novo. O tique limita a espera a um tempo de vida de token, que é o que a ADR-0011 compra ao encurtá-lo.

#### Os três close codes

Parte do contrato, não detalhe de implementação (`app/core/close_codes.py`). Tratar os três como falha transforma toda expiração de rotina num backoff crescente; tratar os três como expiração faz o cliente martelar um Chat de que ele foi removido.

| código | significado | o que o cliente faz |
| --- | --- | --- |
| `1008` | **unauthenticated** — a credencial nunca valeu aqui | não tenta de novo com ela |
| `4401` | **token expired** — valeu e acabou | renova e reconecta |
| `4403` | **access revoked** — a credencial está boa, o Chat não é seu | sai dele, não insiste |

Falha de rede é deliberadamente nenhum dos três: continua sendo erro de socket e continua em backoff exponencial. É isso que faz os três códigos significarem algo.

`1008` é o código de *policy violation* do próprio protocolo, e é o que o handshake sempre respondeu — os outros dois estão na faixa 4000–4999 que o protocolo reserva para a aplicação, com os três últimos dígitos ecoando os status HTTP que um leitor já associa a "quem é você" e "não é seu".

Um Chat que não existe, um Chat de outra Company e um Chat em que você não está fecham todos com `1008`, igual a um token inválido. Os três serem indistinguíveis é a decisão 404-não-403 de `docs/decisions.md` e não está em questão.

**O que está em questão é serem `1008` e não `4403`**, e isso é comportamento que já era assim antes do ticket 11 — foi preservado, não escolhido aqui. O custo é real: a credencial de quem bate num Chat que não é dele está perfeitamente boa, e `1008` diz ao cliente "não tente de novo com ela", o que manda a pessoa para uma tela de login. `4403` — "a credencial está boa, o Chat não é seu, saia dele" — é a instrução correta, e trocar não vazaria nada, porque um token inválido responde `1008` em qualquer Chat e a indistinguibilidade entre os três casos acima se mantém. Não foi trocado porque é mudança de contrato que o ticket 11 não pediu e que a interface (tickets 16 e 17) vai consumir; vale decidir de propósito antes de ela ser escrita.

#### Expulsão: o quarto canal

Autorizar só no connect significa que remover um Participant **avisa o Chat e não expulsa ninguém** — até reconectar, aquela pessoa continua recebendo. Por isso as conexões são indexadas **por Chat e por usuário**: por usuário porque o token dela continua valendo para todo o resto, e por Chat porque perder um Chat não é perder o chat.

A conexão a fechar quase nunca está na instância que tratou a remoção, então a expulsão viaja o mesmo Redis que uma entrega — por um canal próprio, `control:{company_id}`:

- **Não é entrega.** Uma entrega nomeia uma audiência (um canal) e o subscriber encaminha sem saber quem escuta. Uma expulsão nomeia **sockets**, e nenhum nome de canal responde isso.
- **O prefixo decide, não o payload.** Farejar um `type` dentro de todo frame poria uma regra de volta no caminho quente, que é o defeito que a [ADR-0008](../docs/adr/0008-domain-rewritten-in-fastapi.md) registra.
- **Vai pelo outbox**, na mesma transação da saída: ninguém é desconectado por uma remoção que um rollback apagou.

Uma expulsão nomeia o Chat (remoção de Participant) ou nenhum (banimento, todas as conexões daquela pessoa). Um payload que não parseia é logado e descartado — deixá-lo subir mataria o subscriber, e um subscriber morto para de entregar tudo naquela instância, em silêncio.

#### O denylist é a exceção, não o caminho normal

O caminho normal não custa nada e chega sozinho: o monólito revoga **não emitindo o próximo token**, e o serviço percebe dentro de um TTL. Para quando quinze minutos é demais — uma demissão, um banimento, uma credencial que se acredita vazada — existe `POST /internal/revocations` (credencial de serviço, sem `X-Acting-User`, pela mesma razão que o stream de identidade não tem: uma demissão não tem autor a nomear deste lado do fio).

- Body `{ "company_id": "<uuid>", "user_id": "<uuid>" }` — tudo o que a pessoa tem. Bloqueia e fecha todas as conexões dela.
- Body `{ "company_id": "<uuid>", "token": "<jwt>" }` — só aquela credencial, sem tirar o acesso de ninguém. Uma conexão que já a segura cai na próxima revalidação, não na hora: os sockets são indexados por quem os segura, não por qual string apresentaram, e um terceiro índice para a metade mais rara de um caminho de exceção renderia menos do que custa.
- Nomear os dois, ou nenhum, é `422`. A entrega é at-least-once, então um comando que revogou nada e respondeu sucesso seria repetido, teria sucesso igual, e seria acreditado.
- `204` mesmo que nada estivesse segurando conexão: "já estava banido" é este comando já tendo funcionado.

**Toda entrada expira junto com o token que ela bloqueia.** É isso que impede o denylist de virar a lista de revogação distribuída que a ADR recusou: nada poda, nada cresce sem limite, e nenhuma entrada sobrevive à credencial de que ela fala. Uma entrada de *usuário* vive `CHAT_TOKEN_TTL_SECONDS` (900), porque o serviço não guarda registro do que o monólito emitiu e portanto não sabe quais tokens daquela pessoa ainda estão fora. Uma entrada de *token* vive o que aquele token tem de vida. O token é guardado por digest SHA-256, não por valor: um denylist existe para ser lido por quem perguntar, e é o lugar errado para manter uma cópia funcional de uma credencial bearer.

O denylist é consultado no **handshake**, em **toda renovação** e em **toda revalidação periódica** — e deliberadamente **não** no caminho HTTP. Ver "Débito técnico conhecido".

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

## Enviar e apagar mensagens

`POST /chats/{id}/messages` exige `client_message_id`, um identificador que o cliente gera
**antes de enviar** e repete quando reenvia. Não tem default: um envio sem ele é recusado com 422,
em vez de ser gravado com nulo. A diferença importa porque um cliente que desistiu da garantia de
retry e um que esqueceu o campo seriam indistinguíveis — e só um dos dois descobre isso depois, como
uma duplicata do que a pessoa falou uma vez só.

A unicidade é `(chat_id, sender_id, client_message_id)`, constraint no banco. Ter o `sender_id`
dentro dela é o que deixa dois clientes diferentes usarem o mesmo valor sem colidir: o identificador
é do cliente, então ele só é único para aquele cliente, e juntar os dois engoliria em silêncio a
mensagem da segunda pessoa.

**O caminho da repetição é o caminho da recusa.** `_persist_and_announce` tenta o INSERT, e é o
`IntegrityError` que leva à busca pela mensagem original — não há consulta antes. Uma consulta antes
seria uma segunda opinião sobre uma corrida que o banco já está decidindo: duas cópias do mesmo retry
chegando juntas não achariam nada, ambas inseririam, e alguém ainda teria que tratar isso aqui. Com
um caminho só, o retry sequencial comum já exercita o mesmo código que a corrida.

O retry responde 201 com a mensagem original, não 409. Um cliente que nunca viu a primeira resposta
não tem como distinguir os dois casos, e um erro só o empurraria a decidir se tenta de novo. E a
resposta é montada a partir da **linha gravada**, não do que o retry trouxe: um reenvio com o corpo
alterado não vira um endpoint de edição que ninguém desenhou. O retry também sai antes do outbox e do
push da lista — reanunciar mexeria a lista de Chats de todo mundo por uma mensagem que já está lá.

### Apagar marca, não remove

`DELETE /chats/{chat_id}/messages/{message_id}`, com `{"reason": "..."}` opcional. A linha fica: o
corpo é esvaziado e a exclusão é registrada em `deleted_at`, `deleted_by_user_id` e `deletion_reason`.

Duas coisas dependem da linha continuar existindo. A constraint de unicidade: apagar de verdade faria
o próximo retry do autor **escrever a mensagem de novo**, desfazendo a exclusão em nome dele —
`tests/test_message_send_semantics.py` prende exatamente isso. E o cursor do ticket 09, que pagina
sobre as linhas e moveria a fronteira de quem já rolou além dela.

A resposta e o fan-out mandam o marcador: corpo vazio e `deleted_at` preenchido. Quem apagou e por quê
ficam **na linha e fora da resposta** — o que interessa à thread é que algo foi retirado; o resto é
para quem perguntar depois. O `reason` é opcional porque apagar o próprio erro de digitação não deve
satisfação a ninguém, e exigi-lo só encheria a coluna de ponto final. O que todo tombstone carrega é o
autor.

Só o autor apaga, e essa é a única refusa do serviço que é **403 e não 404**. A regra 404-não-403 de
`docs/decisions.md` existe para não confirmar que um Chat existe a quem está fora dele; aqui quem pede
está dentro e já leu a mensagem, então não sobra nada para esconder e o 404 seria só mentira sobre o
motivo. Já uma mensagem endereçada a um conjunto do qual o leitor não faz parte volta como 404: ela
passa pelos mesmos dois filtros da leitura, e distinguir "não é sua para ver" de "não existe" deixaria
enumerar as Staff-only Messages de um Chat pedindo para apagar identificador por identificador.

O tombstone sai no mesmo endereço em que a mensagem foi anunciada (`_address_of`), então quem viu é
exatamente quem é avisado — o cliente final nunca é informado de que sumiu algo que ele não podia nomear.

## Ler: paginação por cursor, marca d'água e não lidas

### A ordem tem desempate

`list_messages` ordena por `(created_at, id)`, não só por `created_at`. Duas mensagens que o relógio
não separa teriam ordem relativa decidida pelo plano de execução — e podendo mudar entre duas leituras
das mesmas linhas. Isso não é só desleixo: o cursor pagina **exatamente sobre essa ordem**, então um par
que sai de um jeito numa página e do outro na seguinte é uma mensagem pulada ou servida duas vezes. O
identificador é o desempate: arbitrário (um uuid v4 não diz nada sobre tempo), mas total e estável, que
é tudo que um cursor precisa. `OLDEST_FIRST` e `NEWEST_FIRST` (`app/models/message.py`) são a única
grafia dessa ordem, e o segundo é derivado do primeiro — as duas direções discordarem do desempate é
justamente o bug que o desempate existe para evitar.

O índice `ix_messages_chat_id_created_at_id` (migration `d8f1a5c37b92`) acompanha esse par. Sem ele o
banco ordena o Chat inteiro para devolver cinquenta linhas, a cada página, e pior exatamente nas
threads longas que tornaram a paginação necessária.

### `GET /chats/{id}/messages?before=<cursor>&limit=<n>`

A resposta deixou de ser um array e passou a ser `{"messages": [...], "next_cursor": "..."}`. O cursor
é parte da resposta, não metadado sobre ela: sem ele a resposta não diz se há mais thread acima, e
`next_cursor: null` é a única coisa que significa "você chegou ao começo".

A busca anda **de trás para frente** e a resposta vem **de frente para trás**: uma thread abre no que foi
dito por último, então a página é encontrada a partir do fim e revertida antes de sair — desfazer a
caminhada não é trabalho de cada cliente. `before` nomeia uma linha, não uma contagem: a comparação é de
tupla contra o mesmo par da ordenação, então a página retoma exatamente na linha onde a anterior parou,
por mais mensagens que tenham chegado acima. É isso que um offset não consegue fazer, e é o que um chat
garante que vai ser testado.

Busca-se **uma linha a mais** do que o pedido e descarta-se. Essa linha sobrando é como a resposta sabe se
manda cursor: sem ela, chegar ao começo e parar exatamente nele são indistinguíveis, e o cliente fica com
um cursor que não traz nada e sem saber que acabou.

O cursor é opaco de propósito (`app/core/cursor.py`): entregue como timestamp e identificador legíveis,
clientes montam o próprio, e aí a ordenação nunca mais muda sem quebrá-los. Base64 aqui não é segredo e
não pretende ser — é um formato que diz "isto veio de nós, devolva sem alterar". Um cursor que o serviço
não emitiu é **recusado com 422**, não tratado como "sem cursor": responder o topo da thread a uma posição
de rolagem corrompida, em silêncio, é indistinguível de ter realmente chegado ao começo.

### `POST /chats/{id}/read`

`{"read_at": "...", "message_id": "..."}`, com `message_id` opcional. A marca d'água é um instante **e**
uma mensagem: o instante é do que a contagem de não lidas é calculada, a mensagem é onde um cliente
reancora a rolagem. `message_id` é opcional porque quem leu um Chat vazio não tem mensagem para apontar.

**O `read_at` é grampeado em `now()`.** Ele vem do relógio do chamador porque só ele sabe quando olhou —
e é exatamente por isso: um aparelho um dia adiantado marcaria como lido tudo que fosse dito nas
próximas vinte e quatro horas, e o estado de não lidas do Chat não voltaria até o desvio passar, em
silêncio. Um `read_at` **sem fuso é recusado com 422**, pelo mesmo argumento do cursor: um timestamp sem
fuso não nomeia instante nenhum, e adivinhar erra pelo offset do chamador ou pelo do servidor.

**A marca d'água só anda para frente.** Dois clientes numa conta é o caso comum — um celular no fim da
thread, um laptop rolado para cima — e sem isso quem marca por último ganha, a contagem volta, e o Chat
re-notifica por mensagens que a pessoa já leu. As duas metades andam juntas ou nenhuma: guardar o
instante e pegar a mensagem mais antiga deixaria um Participant cujo estado de leitura diz duas coisas
diferentes. A regra inteira é `advanced_to`, função pura sobre três instantes.

A `message_id` nomeada passa pelo **mesmo filtro de visibilidade** de qualquer leitura (`visible_to`).
Sem isso o endpoint é um oráculo: um cliente final percorre identificadores, vê quais são aceitos, e
aprende quais Staff-only Messages existem sem nunca ver uma. Responde 404, como toda mensagem que ele
não pode ler.

A resposta é o estado **gravado**, não o eco do pedido — o grampo e a monotonia podem mudá-lo, e um
cliente que assumisse o próprio pedido mostraria uma contagem que o serviço não confirma.

### A posição também é legível

`GET /chats` carrega `last_read_at` e `last_read_message_id` além de `unread_count`. A contagem diz
**quanto** está acima da marca d'água; só esses dois dizem **onde** ela está — e quem pergunta é um
cliente que não fez o `POST /read` que a moveu: um que voltou de uma reconexão, ou um segundo aparelho.
Null nos dois é resposta de verdade, e diferente de zero: é quem não leu nada ali, por oposição a quem
leu a primeira mensagem.

A âncora **segue o instante**. Uma marcação que não move a marca d'água não move nenhuma das duas
metades; uma que move e **não nomeia mensagem** mantém a âncora anterior em vez de apagá-la — nomear é
opcional, e um cliente que só tem relógio manda só o relógio. Consequência aceita: uma marcação no
**mesmo instante** nomeando outra mensagem não mexe na âncora, porque não há instante novo para
ancorar. O caso é estreito (`created_at` é `clock_timestamp()`, resolução de microssegundo) e a
alternativa seria comparar posições na ordem total a cada marcação.

### `unread_count` em cada Chat

`GET /chats` passou a carregar `unread_count`. São três condições, e todas as três estão no JOIN
(`unread_counts`, `app/services/chat.py`) — a contagem é resposta do banco, não lista filtrada aqui:

1. chegou depois da marca d'água **daquele** Participant, que vem da linha dele (os limiares diferem por
   pessoa, então a marca é juntada e não passada como parâmetro);
2. **outra pessoa** disse: enviar é ter lido. Sem isso, um Chat sem resposta fica na lista de quem
   mandou com um badge pelas próprias mensagens;
3. aquele Participant **pode** ler: é o que mantém uma Staff-only Message fora da contagem do cliente
   final. Ele não é informado de que existe uma, e um badge subindo por uma mensagem que ele nunca verá
   avisa que ela está lá.

Chats são agrupados por conjunto de visibilidades, como em `get_last_message_at_by_chat`: um leitor tem
no máximo um conjunto por tipo de Chat, então o OR fica com dois ramos por mais longa que seja a lista.
O JOIN é externo e a resposta cobre todo Participant perguntado, inclusive os com nada a ler — chave
ausente significaria "ninguém falou aqui", tradução que um dos dois call sites esqueceria.

O push da lista por WebSocket carrega a mesma contagem. Ele continua agrupado por papel para o
`last_message_at`, mas a contagem é por pessoa: uma query por papel responde por todas as pessoas dele,
então o custo segue sendo um agregado por papel, não um por Participant.


## A lista de Chats: prévia, ordem, cursor e busca por nome

### `GET /chats?search=<texto>&before=<cursor>&limit=<n>`

A resposta deixou de ser um array e passou a ser `{"chats": [...], "next_cursor": "..."}`, pelo mesmo
motivo que `GET /chats/{id}/messages` mudou no ticket 09: um array não tem onde guardar o cursor, e
`next_cursor: null` é a única coisa que diz "acabou" — uma página que voltou curta não diz, porque um
limite e um resto podem coincidir. **Isso quebra o parse `Chat[]` do frontend legado**
(`frontend/src/lib/api.ts`), que os tickets 16-18 substituem, exatamente como o ticket 09 quebrou o
parse `Message[]`.

Cada item carrega `last_message` — a **resposta inteira** da última mensagem, não só o texto. Uma
prévia que só tivesse o corpo não saberia dizer quem falou, se a mensagem foi apagada, ou se veio de
fora — e cada uma dessas viria depois como mais um campo ao lado, descrevendo uma mensagem que o
objeto já tem. `last_message_at` é derivado dela em `ChatRead.of`, e não passado à parte: aceitar os
dois deixaria alguém entregar um timestamp de uma mensagem diferente da que está sendo exibida.

### A ordem é a última atividade, e o cursor percorre ela

Ordenação, filtro e paginação acontecem **no banco**, não em Python. Isso não é preferência de
desempenho: uma lista ordenada depois da consulta não pode ser paginada, porque a fronteira da página
teria que ser decidida antes da ordenação que decide o que fica de cada lado dela.

O cursor é o mesmo de `core/cursor.py` — um par `(instante, identificador)` opaco — percorrendo
`(última atividade, id do Chat)`. Duas consequências que valem dizer:

- **Um Chat em que ninguém falou ordena na época Unix**, atrás de tudo que já foi dito. Precisa de um
  instante de mentira porque nulo ordena onde o plano quiser, e um cursor sobre uma ordem que o plano
  escolhe é um cursor que pula linhas. O `COALESCE` em `_last_activity` e o `_activity_of` em Python
  são a mesma constante escrita duas vezes, e elas têm que concordar até o microssegundo.
- **O desempate é o id do Chat**, pelo mesmo motivo do desempate das mensagens: todo Chat silencioso
  compartilha a época, e um cursor sobre uma ordem parcial serve uma linha duas vezes ou a perde.

### Uma linha por Chat, não a coleção inteira

`_last_message_of_each_chat` é um `LATERAL` com `LIMIT 1`, correlacionado no `Chat.id`. Carregar as
mensagens de cada Chat para ficar com a última lê a história inteira de uma thread para exibir uma
linha dela — e a conta é paga exatamente pelas Companies para quem essa lista existe, as que têm anos
de mensagem atrás de cada Chat. `test_the_preview_costs_the_same_whatever_the_list_is_worth` afirma
isso pela borda: listar cinco Chats custa o mesmo número de statements que listar dois.

O filtro de visibilidade fica **dentro** da subconsulta, não fora. Fora, uma Staff-only Message ainda
seria a linha mais recente e a prévia do cliente final voltaria vazia em vez de cair para a última
coisa que ele pode ler — anunciando a Staff-only Message pelo buraco que ela deixou.

### `search`: o nome vem da projeção

Casa com o `display_name` de qualquer **outro** Participant atual OU com o nome do próprio Chat. O
nome do próprio Chat entra porque é a única coisa que distingue threads de cinco pessoas umas das
outras (item 21 do spec); quem pergunta fica de fora porque é Participant de todos os Chats da
própria lista, e casar consigo mesmo responderia "ache a pessoa com quem eu falei" com a lista
inteira — o que parece o filtro não estar funcionando.

**É este endpoint que faz a projeção de identidade valer o preço dela.** O nome não sai do comando que
compôs o Chat, nem de token nenhum, nem de uma chamada ao monólito (proibida pela
[ADR-0010](../docs/adr/0010-no-request-depends-on-the-monolith.md)): é uma coluna neste banco. É a
única razão pela qual uma lista filtrada por nome pode ser paginada — o resto seria filtrar em Python
depois da consulta, e aí não há fronteira de página. Renomeou no monólito, o evento chega
(`/internal/identity-events`), e a busca passa a achar pelo nome novo e a não achar pelo antigo.

Acentos e caixa são ignorados nos **dois lados**: `joao` acha João e `João` acha Joao. A normalização é
`immutable_unaccent` (migration `f2b7d419ac53`) aplicada à coluna e ao padrão — só à coluna
consertaria metade. O `unaccent` do Postgres é apenas STABLE e por isso não pode entrar num índice; o
wrapper nomeia o dicionário explicitamente, que é o que o torna honestamente imutável. O índice é GIN
com `gin_trgm_ops`: o filtro é `ILIKE '%...%'` e um curinga à esquerda é exatamente o que um btree não
responde.

`%` e `_` digitados na busca são **texto**, não padrão. Sem escapar, um `_` perdido casa com qualquer
caractere e um `%` casa com a lista inteira — e uma busca que devolve demais parece o filtro quebrado,
não a entrada sendo lida como padrão.

### O limite do filtro

A busca casa **substring**, não palavra: `ana` acha "Ana", "Mariana" e "Joana". É o que quem procura
espera ao digitar parte de um sobrenome, e é também o motivo de o índice ser trigrama. O que ela não
faz é ordenar por relevância — os resultados saem na ordem da lista, por última atividade, o que é o
que um chat quer.

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
- `GET /chats` tira `last_message` **e** `last_message_at` só do que o leitor pode ler, e os dois saem da mesma linha. O timestamp é exibido ao lado do Chat **e** é a chave da ordenação — sem filtro ele avançaria e flutuaria o Chat para o topo toda vez que o staff dissesse algo que o cliente final não pode ler, anunciando a Staff-only Message sem citá-la. A prévia é o outro lado do mesmo vazamento: filtrada **depois** de escolhida a linha mais recente, ela voltaria vazia para o cliente final enquanto o staff vê texto, o que anuncia a mensagem pelo buraco. Por isso o filtro está dentro do `LATERAL`, e a prévia cai para a última mensagem que aquele leitor pode ler.
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

**Um lado de JOIN não é visto pelo teste estrutural.** `unread_counts` (`app/services/chat.py`) nasce de `scope.select(Participant)` — então o `Participant` está coberto — mas o `Message` entra por `outerjoin`, e a condição do join é invisível para uma varredura que reconhece escopo pela grafia do receptor. Por isso o `Message.company_id == scope.company_id` está escrito à mão lá dentro, com comentário dizendo por quê, e por isso `test_the_unread_count_does_not_cross_company` verifica pela borda: os dois lados de um join precisam responder à fronteira, e só a entidade que `scope.select` recebeu carrega isso sozinha.

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
- ~~**Índice de `messages` favorece a query errada.**~~ *(Resolvido no ticket 09: `ix_messages_chat_id_created_at_id`, migration `d8f1a5c37b92`, é `(chat_id, created_at, id)` — o par que o cursor percorre. A constraint de unicidade do ticket 08 continua servindo ao filtro de retry; o que faltava era a ordenação, que o Postgres fazia à parte a cada página.)*
- **Índice de `participants` favorece a query errada.** O `UniqueConstraint(chat_id, user_id)` serve bem a checagem de membership, mas `list_chats` — chamada a cada carregamento da sidebar — filtra só por `user_id`; faltaria um índice dedicado liderado por esse campo. O `EXISTS` da busca por nome percorre `participants` por `chat_id`, que a constraint já atende.
- **O denylist não vale para a API, só para os sockets.** `POST /internal/revocations` fecha as conexões
  da pessoa e recusa novos handshakes, mas `GET /chats`, `GET /chats/{id}/messages` e `POST .../messages`
  continuam aceitando o token dela até ele expirar — até quinze minutos de leitura depois de um banimento.
  O que falta é uma linha em `get_current_caller`, e o que ela custa é o motivo de não estar lá: um
  round-trip ao Redis em **todo** request autenticado, e um Redis fora do ar virando 500 em todo request
  em vez do que o fan-out faz hoje (as linhas ficam pendentes e saem depois). O ticket 11 pediu fechar as
  conexões e é o que ele fechou; a decisão de acoplar a disponibilidade da API ao Redis é maior que ele.
- **Um socket segura uma conexão de banco e uma transação abertas pela vida dele.** `Depends(get_db)` num
  endpoint WebSocket dá uma sessão por socket, e o primeiro `SELECT` (a autorização do handshake) abre uma
  transação que fica aberta até o socket cair. Em `READ COMMITTED` isso não é problema de correção — cada
  statement da revalidação vê dado fresco, que é por que a expulsão por revalidação funciona — mas são
  N conexões `idle in transaction` para N abas abertas. Já era assim antes do ticket 11; o que mudou é que
  agora a sessão é realmente usada de novo, uma vez por minuto, em vez de só no handshake.
- **Sem rate limiting** em `/webhook/messages`.
- ~~**`GET /chats` ainda devolve o conjunto inteiro.**~~ *(Resolvido no ticket 10: a lista pagina pelo mesmo contrato de cursor de `GET /chats/{id}/messages`, sobre `(última atividade, id do Chat)`, e aceita `search` por nome de participante ou do próprio Chat.)*
- **A busca só enxerga quem ainda está no Chat.** O `EXISTS` de `_matching_the_search` carrega `STILL_IN_THE_CHAT`, então um 1:1 deixa de ser achável pelo nome da outra pessoa assim que ela sai — e um 1:1 não tem nome próprio para servir de alternativa. É coerente com todo o resto (`participant_user_ids` só mostra quem está), mas um Chat na sua lista que nenhum nome acha é um Chat que só o scroll alcança. Ver `docs/decisions.md`.
- **A metade do `OR` que casa o nome do próprio Chat não tem índice.** O nome do participante passa pelo GIN trigrama da migration `f2b7d419ac53`; `chats.name` é varrido. O alcance é a lista de quem pergunta, não os profiles da Company inteira, e por isso ficou.
- **A busca não ordena por relevância.** `search` casa substring e devolve na ordem da lista, por última atividade. Quem digita `ana` procurando "Ana Souza" recebe antes um Chat com "Mariana" se alguém falou nele mais recentemente. Numa lista de centenas isso incomoda; o que resolve é pontuar a similaridade (`similarity()` do `pg_trgm`, que já está instalado) como critério de ordenação secundário — o que muda a chave de ordenação e portanto o cursor, então não cabia no ticket 10.
- **`GET /chats` não tem índice para a ordem que ela percorre.** O `LATERAL` da prévia usa `ix_messages_chat_id_created_at_id`, mas a ordenação da lista é por uma expressão (`COALESCE` sobre a saída do lateral) e não por coluna — o Postgres ordena o resultado do join. É barato enquanto uma pessoa está em dezenas de Chats, e deixa de ser quando estiver em milhares.
- **Zero logging estruturado** em todo o `app/` — combinado com o subscriber Redis sem tratamento de falha (acima), é o ponto mais arriscado de operar isso em produção sem visibilidade.

## Testes manuais: Insomnia e os dois scripts

`insomnia/` tem quatro coleções — composição e lista de Chats, mensagens/leitura/paginação, webhook e
WebSocket. Importe o `.json` no Insomnia e preencha o Base Environment.

**Não existe login.** O monolito é o único emissor de chat token (ticket 01), então nenhuma requisição
devolve um. `scripts/mint_chat_token.py` faz o papel do monolito:

```
uv run python -m scripts.mint_chat_token --insomnia
```

Isso imprime o Base Environment inteiro — cinco usuários (A–D staff, E cliente final), os tokens deles,
o `service_token` e o `company_id` — para colar na coleção. D nunca entra em Chat nenhum, para que
"não vê nada" seja afirmado por alguém real e não por um banco vazio; E existe para a Staff-only
Message ter de quem ser escondida. Os tokens valem 12h (`--minutes`).

O script só funciona porque a verificação ainda é HS256 sobre segredo compartilhado — a propriedade que
a [ADR-0009](../docs/adr/0009-chat-owns-token-in-rs256.md) existe para remover. Quando o ticket 19
trocar por RS256, ele passa a precisar da chave privada de teste e o serviço fica só com a pública.

**A assinatura do webhook cobre bytes, não um documento.** `scripts/sign_webhook.py` recebe o corpo na
entrada padrão e imprime duas linhas: o corpo compacto e a assinatura.

```
echo '{"company_id": "...", "chat_id": "...", "body": "oi"}' | uv run python -m scripts.sign_webhook
```

Por isso o `chat_id` **não** é templatizado nas requisições de webhook: o serviço é quem gera esse
identificador, e um `{{ chat_id }}` produziria bytes diferentes dos assinados. As assinaturas gravadas
na coleção valem para `WEBHOOK_HMAC_SECRET=change-me` e um `chat_id` de exemplo — as que esperam 401 e
404 rodam como estão, e as que esperam 201 pedem que você re-assine com o seu Chat.

**O WebSocket depende do drain.** Desde o ticket 07 a requisição não publica: ela grava no outbox e um
processo separado publica. Com `docker compose up` o drain sobe junto; rodando o backend à mão, nada
chega no socket até o drain rodar também.

## Migrations

```
uv run alembic revision --autogenerate -m "message"
uv run alembic upgrade head
uv run alembic check
```

`alembic check` faz a mesma comparação que o `--autogenerate` — os modelos contra o schema vivo — mas
em vez de escrever migration ele só pergunta se haveria alguma. Sai 0 quando não há, 1 e a lista quando
há. É guarda de CI: garante que migrations e modelos ainda descrevem o mesmo banco.

Duas coisas mantêm isso verdadeiro, e as duas já falharam aqui:

- **Todo índice é declarado no modelo também**, não só na migration. Um índice que os modelos não
  mencionam é lido como um que alguém dropou, e o próximo `--autogenerate` propõe apagá-lo — foi o que
  aconteceu com `ix_outbox_pending`, o índice parcial em que o drain varre.
- **`include_object` em `alembic/env.py` filtra check constraints.** `stored_by_value` constrói as
  colunas com `Enum(create_constraint=True)`, então `chat_type`, `message_visibility` e
  `participant_role` são *type-bound* — pertencem ao tipo, não à tabela — e o Alembic tira constraints
  type-bound do lado dos metadados de propósito. As refletidas ficam sem par e todo run reportava as
  três como removidas, fazendo o `--autogenerate` emitir `op.drop_constraint` para cada uma. É
  supressão, não correção: se um dia existir uma check constraint escrita à mão, é a hora de revisitar.

**O downgrade até `base` não roda num banco com dados.** Reverter `a3f7c2e51b08` (a renomeação de
`conversations` para `chats`) repovoa `conversation_participants`, cuja FK aponta para a tabela `users`
que uma migration posterior removeu. Ir para frente funciona; voltar até o começo, não.

`alembic/env.py` lê a URL do banco a partir de `app.core.config.settings` (ou seja, do `.env`), não do `alembic.ini`.
