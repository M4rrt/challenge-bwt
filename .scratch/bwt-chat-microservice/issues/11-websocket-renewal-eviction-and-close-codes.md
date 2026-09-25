# 11 — WebSocket renewal, eviction and close codes

**What to build:** A Participant's connection survives a routine credential expiry without dropping, and someone who loses access to a Chat stops receiving it immediately rather than at their next reconnect.

An expiring token cannot mean reconnecting: a reconnect costs a recovery query and opens a window in which messages are lost. So the service warns the connection shortly before expiry, the client sends a new token over that same connection, and the service revalidates both the token and the Chat's authorisation. That revalidation is the moment revocation actually happens — the monolith simply does not issue the next token, or issues it without the scope.

The deadline stays as a backstop. Having both is the point: the deadline alone costs a recovery every fifteen minutes, and in-band renewal alone creates a path where forgetting to reschedule the deadline leaves a connection alive forever — and that defect is silent.

**Blocked by:** 07.

**Status:** done

- [x] The service warns a connection shortly before its credential expires
- [x] A client sends a new token over the same connection; the service revalidates the token and the Chat's authorisation and confirms, without dropping
- [x] A connection whose renewal does not arrive by expiry is closed with a dedicated token-expired code, distinct from the unauthenticated one
- [x] Connections are indexed by Chat and by user, so removing a Participant closes that user's connections in that Chat with a dedicated access-revoked code, leaving their other connections alone
- [x] Room connections revalidate authorisation periodically as well as on renewal, covering a lost supervision scope and a deactivation, not only explicit removal
- [x] An event from the monolith can put a token or user on a short-lived denylist whose entries expire alongside the token they block, and closes that user's connections
- [x] The three close codes are documented as part of the contract

## Comments

**2026-09-23 — nota vinda do ticket 07.**

O direito de um socket aos endereços de fan-out é decidido **uma vez, no handshake** (`app/routers/websocket.py`), pelo mesmo `may_read` da API. Um Participant cujo papel mude de `staff` para `client` continua no endereço `chat:{company}:{chat}:staff` pelo resto da vida daquela conexão, e segue recebendo Staff-only Message.

Este ticket já cobre revalidação na renovação e periodicamente, o que fecha o caso. Registrado aqui porque o gap não é de nenhum ticket hoje: o 07 construiu o endereço, o 05 constrói a troca de composição, e nenhum dos dois revalida uma conexão já aberta.

**2026-09-24 — implementado.**

Onde as coisas ficaram:

- `app/core/close_codes.py` — os três códigos e o que o cliente faz com cada um. `1008` continua sendo o que o handshake sempre respondeu; `4401` e `4403` estão na faixa que o protocolo reserva para a aplicação.
- `app/core/connection_schedule.py` — quando. Aritmética pura sobre um `now` que quem chama fornece, porque três tasks dormindo por conexão não se asserta sem dormir, e uma renovação move dois prazos ao mesmo tempo (então as tasks teriam que combinar quem cancela e rearma quem).
- `app/services/connection.py` — o quê. **Uma task, um laço**: o receive e os três compromissos são esperados juntos. Além da razão acima, todo ramo toca a sessão do banco e os índices de endereço, que são os do request e não podem ser usados por duas tasks ao mesmo tempo. O receive pendente nunca é cancelado para disparar um compromisso, só no teardown — cancelar um socket no meio de um `receive` é como um frame se perde entre o transporte e o handler, que é exatamente a perda que a renovação em banda existe para evitar.
- `app/services/realtime.py` — `Holder`, os dois índices novos (`_by_holder`, `_by_user`) e o canal `control:{company}`.
- `app/services/denylist.py`, `app/schemas/revocation.py`, `POST /internal/revocations` — a exceção.
- `_evict` em `app/services/chat.py` — a expulsão entra na mesma transação da saída, pelo outbox.

Duas coisas que o ticket não pediu e que caíram aqui:

- **Um token sem `exp` passou a ser recusado.** A biblioteca só verifica um `exp` que encontra, e a ADR-0011 faz do tempo de vida *o* mecanismo de revogação — então um token sem prazo é um token que o serviço não consegue tirar. `Caller` passou a carregar o momento em vez de a biblioteca descartá-lo.
- **A lacuna que o ticket 07 registrou contra si mesmo fechou junto.** Um Participant cujo `user_kind` vira `client` deixa de ouvir o endereço staff na próxima renovação ou revalidação, sem cair. `tests/test_connection_lifetime.py` tem o teste com esse nome.

Uma ressalva sobre o critério 5, registrada porque a revisão a levantou e ela é justa: **a revalidação periódica não relê uma claim.** Uma desativação e um escopo de supervisão perdido moram no token, e o token não muda entre renovações — rodar o mesmo predicado contra o mesmo `Caller` deriva a mesma resposta. Esses dois são cobertos pela renovação (o monólito emite o próximo token sem o escopo, ou não emite) e pelo denylist quando quinze minutos é demais. A ADR-0011 credita "revalida periodicamente e em toda renovação" com cobrir os dois e é o **par** que cobre; a metade periódica sozinha cobre o que o serviço vê por si — a linha de Participant e o denylist. Fechar isso de outra forma exigiria uma tabela de usuários que o serviço não tem ou uma chamada ao monólito que a ADR-0010 proíbe. `backend/README.md` e a docstring de `REVALIDATION_INTERVAL` dizem isso onde alguém iria olhar.

Fora de escopo, registrado como débito em `backend/README.md`:

- **O denylist não vale para a API.** O ticket pediu fechar as conexões e é o que ele fecha; o token de quem foi banido continua lendo pela API até expirar. Falta uma linha em `get_current_caller`, e o que ela custa — um round-trip ao Redis em todo request autenticado, e Redis fora do ar virando 500 em vez do que o fan-out faz hoje — é uma decisão maior que este ticket.
- **Um socket segura uma conexão de banco e uma transação abertas pela vida dele.** Já era assim antes; o que mudou é que a sessão agora é usada de novo uma vez por minuto em vez de só no handshake.

Testes: `tests/test_connection_schedule.py` (a aritmética), `tests/test_connection_lifetime.py` (aviso, prazo, renovação, revalidação, demoção), `tests/test_connection_eviction.py` (o índice), `tests/test_denylist.py` (a exceção). `tests/sockets.py` tem o `closed_with` que lê até o serviço desligar — um close no meio da conexão chega embrulhado num `ExceptionGroup` pelo task group do `httpx_ws`, diferente de um close no handshake, que `test_websocket.py` já assertava direto.
