# 04 — Staff-only Message visibility

**What to build:** A Company staff member writes a Staff-only Message inside a Client Chat and coordinates with colleagues without leaving the thread. The end client does not receive it and does not learn it exists — not in the list, not in a count, not as a gap in pagination.

This is the rule with the worst failure history in the source module: a Participant loaded through a relation came back as the base user class, so an `isinstance` check answered "no" for an employee — sometimes dropping employees from their own fan-out, sometimes keeping an end client in it, and failing silently in both directions. ADR-0008 says it gets a test before it gets code. The re-introducible form here is an unrecognised user kind claim, which is why the predicate has an explicit default-deny branch.

**Blocked by:** 03.

**Status:** ready-for-human

_Uma caixa segue aberta e é do ticket 09; veja a lista abaixo._

- [x] Message visibility is `all` or `staff_only`
- [x] A Staff-only Message is only legal in a Client Chat; attempting one in a Staff Chat is rejected rather than silently accepted
- [x] Who may read a Staff-only Message is a single pure predicate over user kind, Company, Chat type and visibility
- [x] The predicate has an explicit default-deny branch for an unclassifiable reader, tested directly as a pure function
- [x] An end client's message list never contains a Staff-only Message, and pagination shows no gap where one was
- [ ] Their unread count never counts one — **nada a contar ainda**: não existe contador nem cursor no serviço. O ticket 09 os constrói por cima de `readable_visibilities` e herda o filtro. Marcado aberto porque uma caixa marcada sobre código inexistente é uma promessa que ninguém cobra.
- [x] A Company staff member in the same Client Chat does read it

## Comments

**2026-09-23 — implementado.**

A regra vive em `backend/app/core/message_visibility.py` como `may_read`, função pura sobre (user kind, Company, tipo do Chat, visibilidade). Irmã de `company_scope.py` de propósito: as duas regras perderam o piso do Django na mudança para FastAPI e as duas falham em silêncio quando falham.

Nenhum caminho de leitura reescreve a regra em SQL. `readable_visibilities` monta o `WHERE` perguntando ao próprio `may_read` sobre cada visibilidade, então não existe segunda grafia para divergir da primeira. Três caminhos passam por ela: o histórico (`GET /chats/{id}/messages`), o `last_message_at` da lista de chats — que é o timestamp exibido *e* a chave da ordenação, e sem filtro anunciaria a Staff-only Message sem citá-la — e a escrita.

**A escrita é a regra de leitura lida ao contrário:** quem escreve só endereça uma mensagem a um conjunto do qual faz parte. Isso recusa com `422` tanto uma staff-only num Staff Chat quanto uma escrita pelo cliente final, sem uma segunda regra para manter em dia.

**Default-deny decidido para tudo, não só para staff-only.** Um `user_kind` que a regra não classifica não lê nada. Uma thread vazia é uma falha que alguém reporta; uma Staff-only Message vazada é uma que ninguém vê.

**Gap aceito, e é do ticket 07.** A regra vale na API e ainda não no transporte: `publish_message` manda toda mensagem para o canal único `chat:{id}`, então o cliente final com a tela aberta recebe o frame ao vivo, e o resumo de `user:{company_id}:{user_id}` carrega `last_message_at` sem filtro. Decisão consciente — o ticket 07 é o que dá à staff da Company um endereço próprio, e antecipá-lo aqui seria construir transporte sem o outbox que ele exige. Registrado no débito técnico de `backend/README.md`.

Fora do escopo deste ticket e cobertos pelo 09: contagem de não lidas e paginação por cursor. As duas nascem por cima de `readable_visibilities` e por isso herdam o filtro.

Colateral: `MessageRead` era construído à mão em quatro lugares (REST, histórico, webhook, fan-out) e acrescentar `visibility` quebrou três de uma vez. Agora há um `MessageRead.of`, como já havia `ChatRead.of`.
