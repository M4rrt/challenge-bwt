# 13 — Supervisor reading

**What to build:** A Supervisor reads their Company's Chats without being a Participant of them, so they can audit or assist without joining every thread — and because they are not a Participant, their reading never produces a read receipt.

The scope is resolved in the monolith, against a permission system the service does not know, and arrives as a claim. The service's job is to honour it and to refuse to let it become a cross-Company key.

**Blocked by:** 04, 06.

**Status:** ready-for-human

- [x] A caller carrying the supervision scope reads their Company's Chats without being a Participant
- [x] Supervised reading produces no read receipt and does not move any watermark
- [x] Supervision never crosses a Company, whatever the claim says
- [x] A Supervisor's access to a Staff-only Message follows the same predicate as everyone else's, not a bypass
- [x] A caller without the scope reads nothing they are not a Participant of

## Comments

**2026-09-23 — nota vinda do ticket 04.**

`may_read` (`backend/app/core/message_visibility.py`) classifica o leitor por `ParticipantRole(reader_kind)`, cujos membros são exatamente `staff | client`. Reusar o predicado para o Supervisor — em vez de abrir um desvio para ele, que é o que este ticket proíbe — só funciona se o token do Supervisor trouxer `user_kind: "staff"` e carregar a supervisão como **scope**, não como um terceiro kind.

Se o monolito emitir `user_kind: "supervisor"`, o ramo default-deny entrega um serviço vazio a ele. É a falha barulhenta que o desenho prefere ao vazamento, mas confirme a forma do claim com o monolito antes de construir por cima.

**2026-09-28 — implementado.**

A supervisão chega como `SUPERVISION_SCOPE = "chat:supervise"` em `Caller.scopes`
(`backend/app/core/chat_token.py`), exatamente como a nota do ticket 04 previa:
um scope sobre um `user_kind` comum (`staff`/`client`), nunca um terceiro kind.
`is_supervisor(caller)` é o único lugar que lê essa claim.

Dois pontos de leitura ganharam um ramo para o Supervisor, e nenhum outro
mudou:

- `list_chats` (`app/services/chat.py`, `_chats_of`) — para um Supervisor, a
  query larga o JOIN em `Participant` e o filtro por `user_id`; o resto (Company
  via `scope.select`, ordenação, cursor, preview via `LATERAL`) é a mesma
  query de sempre. Um Supervisor que também é Participant em algum Chat
  continua lendo seu próprio watermark ali via `_read_by`.
- `list_messages` (`app/services/message.py`) — trocou `chat_of_participant`
  por `chat_for_reading`, que bifurca: Participant vai por
  `chat_of_participant` (como antes), Supervisor vai por `assert_chat_exists`
  (só `scope.select`, sem exigir uma linha de Participant). Envio e exclusão
  continuam só por `chat_of_participant` — supervisão é escopo de leitura, não
  abre escrita.

Nenhuma das duas toca `may_read`/`readable_visibilities`: a fronteira de
Staff-only Message é decidida do mesmo jeito para todo mundo, porque nenhum dos
dois caminhos novos pergunta nada diferente do que os antigos perguntavam — só
muda quem tem permissão de fazer a pergunta sem ser Participant.

**Sem recibo de leitura de graça.** `mark_read`/`_participant_in`
(`app/services/read_state.py`) já exigia uma linha de `Participant`, e um
Supervisor não tem uma no Chat que só supervisiona — então `POST
/chats/{id}/read` já recusava com 404 antes deste ticket. Fechado por
argumento e travado por teste de regressão
(`test_supervised_reading_produces_no_read_receipt`), sem precisar de código
novo — mesma forma da nota do ticket 06 sobre "fechado por argumento".

**Fronteira de Company:** nenhum caminho novo aceita `company_id` do chamador;
a Company de um Supervisor é a mesma claim do token que qualquer outro
`Caller` usa (`CompanyScope.of`). `test_supervision_never_crosses_a_company`
prova pela borda que a claim de supervisão não abre um segundo parâmetro para
nomear outra Company.

Fora do escopo, como o ticket pede: WebSocket (`app/routers/websocket.py`)
continua exigindo `chat_of_participant` — um Supervisor não abre socket num
Chat que não é seu sem entrar nele. Não havia critério pedindo isso, e a
conversa em tempo real de um Chat que a checklist não cobre teria sido escopo
por cima do ticket.

Testes em `backend/tests/test_supervisor_reading.py`, mais dois em
`backend/tests/test_chat_token.py` para `is_supervisor` como função pura —
a mesma forma dupla que `test_message_visibility.py`/`test_messages.py` já
usam para `may_read`.
