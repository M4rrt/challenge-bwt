# 08 — Message send semantics: idempotency and tombstones

**What to build:** A Participant sends a message and it is stored exactly once even if their client retried, and deleting a message takes back what was said without changing the shape of the thread for everyone else.

Deletion marks, it does not remove: the row stays because the idempotency constraint and the pagination cursor both depend on it existing. The content is cleared and the deletion is recorded with author and reason, and the message keeps appearing in the list as a marker.

**Blocked by:** 03.

**Status:** ready-for-human

- [x] A message carries a client message id supplied by the sender
- [x] Sending the same client message id twice in the same Chat from the same sender returns the original message rather than an error, and stores one row
- [x] Two different senders may use the same client message id without colliding
- [x] Deleting a message clears its body and records who deleted it and why, leaving the row in place
- [x] A deleted message still appears in the list, as a marker, and still occupies its position in the cursor
- [x] A Participant cannot delete someone else's message

## Comments

### O retry passa pela recusa, não por uma consulta antes

A idempotência podia ter sido uma busca antes do INSERT. Não é: `_persist_and_announce`
tenta gravar e é o `IntegrityError` da constraint que leva à mensagem original. Uma
busca antes seria uma segunda opinião sobre uma corrida que o banco já decide — duas
cópias do mesmo retry chegando juntas não achariam nada, as duas inseririam, e uma
delas ainda cairia aqui. Com um caminho só, o retry sequencial comum exercita o mesmo
código que a corrida, e não existe um segundo ramo que só produção visita.

### A resposta do retry vem da linha, não do que o retry trouxe

Um reenvio com o corpo alterado devolve o corpo **gravado**. Caso contrário o cliente
teria achado um endpoint de edição que ninguém desenhou — e um que reescreve a história
em silêncio, já que o original nunca mais aparece. O primeiro envio é o que aconteceu.

### 403 para apagar mensagem alheia, contra a regra 404-não-403

É a única exceção à regra de `docs/decisions.md`, e ela não é uma exceção de verdade: a
regra existe para não confirmar que um Chat existe a quem está fora dele, e quem pede
aqui está dentro e já leu a mensagem. Não sobra nada para o 404 esconder, então ele
seria só uma mentira sobre o motivo. A mensagem que o leitor não pode ver continua 404,
pelo motivo original — distinguir os dois casos deixaria enumerar as Staff-only Messages
de um Chat pedindo para apagar identificador por identificador.

### O que o tombstone protege é o próprio retry

O motivo mais concreto de a linha ficar não é o cursor do ticket 09, é a constraint deste
ticket: apagar a linha de verdade faria o próximo retry do autor escrever a mensagem
outra vez, desfazendo a exclusão em nome dele.
`test_a_retry_after_a_deletion_does_not_bring_the_message_back` prende isso, e passou sem
nenhum código novo — que é o desenho funcionando, não um teste sobrando.

### Apagar duas vezes não desfaz o registro

Achado da revisão. Sem guarda, um segundo DELETE sem body sobrescrevia
`deletion_reason` com nulo e remarcava `deleted_at` — um duplo clique apagava o
porquê e movia o instante da exclusão para o momento do acidente. Uma mensagem já
retirada é um pedido que já deu certo, então o segundo devolve o marcador existente
e não escreve nada.

### `client_message_id` volta na resposta, e isso é uma escolha

Nem o ticket nem o spec pedem o campo de volta — a revisão levantou como escopo a
mais, com razão de perguntar. Ele fica porque o frame do fan-out chega **sem par
request/response**: o cliente que mandou a mensagem pode receber o broadcast antes
da resposta do próprio POST, e sem o identificador que ele mesmo gerou não tem como
casar o balão otimista com a mensagem que voltou — renderiza duas. É o ticket 17 que
vai bater nisso.

O custo, declarado: o identificador de cada cliente fica visível para todo o Chat, e
um cliente que numere sequencialmente revela quantas mensagens já mandou. Devolver só
para quem enviou exigiria que `MessageRead.of` soubesse quem está lendo, o que ele
hoje deliberadamente não sabe.

### O rollback do retry virou savepoint

Também da revisão, levantada pelos dois eixos. `db.rollback()` descartava a transação
inteira da sessão, não só o INSERT recusado. Funciona hoje porque os dois chamadores
só leem antes — mas isso é uma condição sobre todo chamador futuro, guardada em lugar
nenhum, que falharia descartando o trabalho dele em silêncio. Agora o INSERT vai num
`begin_nested()`.

### Ficou de fora

- **O webhook não ganhou `client_message_id`.** Mensagem externa não tem sender, e nulo
  nunca colide, então ela passa pela constraint sem nunca se encontrar nela. Deduplicação
  de entrada externa é replay protection, que é o ticket 14.
- **As coleções do Insomnia continuam desatualizadas.** `insomnia/insomnia-mensagens.json`
  ainda chama `/auth/register`, `/auth/login` e `POST /chats` — rotas que os tickets 01 e 05
  removeram. Consertar só o corpo do envio seria polir um artefato quebrado em três lugares.
