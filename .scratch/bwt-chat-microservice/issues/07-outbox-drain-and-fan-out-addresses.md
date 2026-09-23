# 07 — Outbox, drain and the three fan-out addresses

**What to build:** Realtime delivery stops being a side effect of the request. The event is written in the same transaction as the message and published by a separate drain, which buys two properties at once: nobody is told about a message a rollback will erase, and nothing is lost if the process dies between commit and publish.

Fan-out addresses three groups rather than one group per Chat with filtering at delivery: what is computed for a single user, what is true for everyone in the Chat, and what is true only for the Company's staff in it. Isolation comes from the address, not from an `if` every future emitter has to remember to write — which is exactly the failure mode ticket 04 exists to prevent, now enforced at the transport.

**Blocked by:** 04.

**Status:** ready-for-human

- [x] The outbox row is written in the same transaction as the message it announces
- [x] A rolled-back transaction produces no delivery
- [x] The drain is a single callable that processes the pending batch once and returns — this is what tests run between sending and asserting, and what the production process calls in a loop
- [x] A drain that dies mid-batch loses nothing; the next run delivers what it did not
- [x] Three fan-out addresses exist: per-user, per-Chat, and per-Chat staff
- [x] A Staff-only Message is published only to the staff address and never reaches an end client's connection
- [x] The age of the oldest unpublished row is observable

## Comments

**2026-09-23 — implementado.**

A entrega saiu do request. `_persist_and_announce` escreve a Message, faz `flush` para que ela ganhe id e timestamp sem encerrar a transação, monta os payloads e enfileira as linhas do outbox — **um único commit no fim**. O teste que garante isso falha se alguém puser um commit no meio: ele derruba o envio *depois* da Message e *antes* dos resumos, e exige que nem a mensagem nem o anúncio sobrevivam.

`drain_once(db)` processa o lote pendente uma vez e retorna quantas saíram. Um callable para dois consumidores: `app/drain.py` o chama em laço (contêiner `drain` no compose), e os testes o chamam entre enviar e asserir. Processo separado, não tarefa de fundo do API — em produção porque entrega que divide processo com request morre junto com ele, e nos testes porque um tick de fundo faria de cada asserção de tempo real uma corrida.

**At-least-once, decidido com você:** publica e só então marca, um commit por linha. Verifiquei que o teste tem dentes invertendo a ordem — marcar antes perde exatamente uma linha.

**Os três endereços:** `chat:{company}:{chat}`, `chat:{company}:{chat}:staff` e `user:{company}:{user}`. O `ConnectionManager` passou a ser indexado pelo endereço em si, e o subscriber encaminha por nome de canal — sem parsear UUID, sem ramificar por prefixo, sem saber o que é um Chat. O socket entra nos endereços a que tem direito **no handshake**, pelo mesmo `may_read` da API. O socket do cliente final nunca entra no endereço staff: não há nada para filtrar depois, que é a diferença entre isolamento por endereço e um `if` na entrega.

**Fechou o gap que o ticket 04 deixou aberto de propósito.** A Staff-only Message não chega mais no socket do cliente final, e o resumo de lista agora é montado **por papel** — cada Participant recebe o `last_message_at` do que ele mesmo pode ler, então o Chat não flutua para o topo da lista do cliente quando a staff cochicha.

`oldest_unpublished_age(db)` responde quão atrás a entrega está. Idade e não contagem: mil linhas de um segundo atrás é um serviço movimentado, uma linha de dez minutos atrás é um drain parado. O ticket 18 transforma isso em algo monitorado.

**Assunção registrada, não confirmada:** a linha publicada **fica** com `published_at` preenchida em vez de ser apagada, pelo rastro de entrega. Cresce sem coletor — anotado no débito técnico de `backend/README.md`. Apagar ao publicar é uma migração para reverter.

**O guard de isolamento ganhou uma exceção nomeada.** `app/services/outbox.py` lê o outbox de todas as Companies de propósito: o drain não tem chamador, nem token, nem Company. É seguro pela razão em que este ticket inteiro se apoia — a Company já está no endereço, decidida quando a linha foi escrita. A exceção é uma lista em `test_company_isolation.py`, não uma convenção, para que uma terceira seja uma edição que alguém tenha de justificar.

Mudança de seam: todo teste de tempo real agora faz um tick de drain entre enviar e asserir. É o seam 2 que o spec previu.

**Achados da revisão, corrigidos.**

O mais sério era um bug de produção que o seam de teste escondia: `create_chat` enfileirava os resumos **depois** do próprio commit, e em produção `get_db` fecha a sessão — que faz rollback do que ficou aberto. A criação de Chat não anunciava nada. Os testes passavam porque o drain roda na mesma sessão e o commit dele adotava as linhas órfãs. O teste que fecha isso faz `rollback` antes de drenar, que é exatamente o que fechar a sessão faz, e assim só sobrevive o que o request commitou. `create_chat` agora tem a mesma forma de `_persist_and_announce`: flush, enfileira, um commit.

O drain não travava linha nenhuma, então duas réplicas publicariam **tudo** em duplicata — não ocasionalmente, sempre. At-least-once foi decidido com você; duplicação irrestrita sob scale-out não. Agora é uma linha por transação com `FOR UPDATE SKIP LOCKED`. Travar o lote inteiro não serviria: o primeiro commit solta todas as travas da transação.

O docstring afirmava ordem mais forte do que o código entrega — `created_at` é carimbado no insert, então uma transação lenta pode commitar depois de uma que começou mais tarde. Reescrito para dizer o que vale: a ordem é de inserção, e dentro de um envio ela se mantém porque tudo é inserido junto.

`Address` virou um tipo (`company_id` + `channel`). Passados apart, os dois podiam discordar — uma linha arquivada sob uma Company e endereçada ao canal de outra seria um vazamento que nada a jusante pegaria, já que o desenho inteiro se apoia no canal ser o isolamento.

A exceção do guard de isolamento passou a ser **por entidade**: `services/outbox.py` pode ler `OutboxEvent` e só isso. Por arquivo, um `select(Chat)` crescendo lá dentro ficaria invisível — verifiquei que a versão nova aponta exatamente esse caso.

Menores: o modelo declarava `index=True` em `address` e `published_at` sem índice correspondente na migração (a próxima autogeneração emitiria índices fantasmas); o índice de `address` foi removido de vez, porque nada consulta por ele e índice não consultado se paga em todo insert. O `idle_seconds` de `run_forever` não tinha chamador nem teste e virou a constante. O compose repetia as cinco variáveis do backend — agora é uma âncora YAML, e o drain ganhou `restart: unless-stopped`.

**Consequência de deploy, agora rastreada no [20](20-the-drain-runs-in-production.md).** O request não publica mais, então um deploy sem o processo de drain rodando armazena tudo e entrega nada em tempo real — em silêncio. O `docker-compose.yml` ganhou o serviço `drain`; `infra/` ainda não.
