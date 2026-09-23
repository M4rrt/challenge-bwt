# 05 — Composition arrives as a command

**What to build:** Creating a Chat and adding or removing a Participant stop being things a browser asks the service to do. The monolith validates them against live data — Company membership, active status, and for an end client the CRM contact relation that cannot be mirrored — and then calls the service with a command that already carries each Participant's identity.

ADR-0010 is what this implements: no request path of the service queries the monolith, and this is the one operation where stale data would hurt most, because whoever joins reads everything said since the Chat was created. The service validates the shape of the Chat and does not re-check what the caller signing the command is the authority on.

**Blocked by:** 03.

**Status:** ready-for-human

- [x] Create Chat, add Participant and remove Participant are internal routes, authenticated by a service credential
- [x] A command arriving without a header naming the acting user is refused — there is no Chat without an author, and this is what stops the service credential becoming an omnipotent one
- [x] The command carries each Participant's identifier, Company, user kind, display name and avatar
- [x] The service validates the shape of the Chat and does not attempt to re-validate Company membership or contact status
- [x] The public endpoints that created a Chat or added a Participant are removed
- [x] The service exposes no endpoint listing who may participate — that list stays in the monolith
- [x] With the monolith unreachable, composition fails and every existing Chat keeps sending and receiving normally

## Comments

**As três rotas internas.** `POST /internal/chats`, `POST /internal/chats/{id}/participants` e
`DELETE /internal/chats/{id}/participants/{user_id}`. Autenticadas por `Authorization: Bearer
$INTERNAL_SERVICE_TOKEN` e por **dois** headers: `X-Acting-User` e `X-Acting-Company`.

**Por que dois headers, e não um.** O spec fala em "um header nomeando o usuário", mas um id de usuário
sozinho não nomeia ninguém aqui — o mesmo id pode existir em duas Companies, coisa que `services/realtime.py`
já carrega em todo endereço por exatamente essa razão. A Company nomeada é também a Company em que o comando
escreve, o que dá um único construtor de escopo (`CompanyScope.of`) servindo token e comando. **Assunção, não
confirmada com você:** se preferir um header só, a Company passa a sair dos participantes no create e não sai
de lugar nenhum no remove — foi por isso que escolhi assim.

**O comando nomeia todo mundo; o serviço não acrescenta ninguém.** Antes o chamador entrava no Chat a partir
do próprio token. Agora não há token: o monolito valida contra dado vivo e manda a identidade de cada
Participant (identificador, Company, kind, display name, avatar). Consequência direta: um comando que não
nomeia ninguém virou recusa explícita (`EmptyChatError`) — antes o Chat sempre tinha pelo menos quem o abriu.

**A forma do Chat é validada num lugar só.** `_validate_shape` serve criar e adicionar, porque a forma é
propriedade do Chat e não do instante: checada só na entrada, "Staff Chat não contém cliente final" teria
atalho — abre o Staff Chat, depois adiciona o cliente. É por isso que o comando de adicionar aceita um `name`:
o terceiro Participant transforma 1:1 em grupo, e grupo precisa de nome.

**Remover não passa por lá, de propósito.** "Um Chat se compõe com alguém dentro" é regra sobre compor um;
um Chat de onde todos saíram não está malformado, acabou. Recusar a última saída prenderia a última pessoa
num Chat que ela pediu para sair.

**Repetição.** Composição chega at-least-once: adicionar quem já está não muda nada **e não anuncia nada**
(o resumo de lista vai para todo Participant, e uma reentrega moveria toda lista aberta à toa); nomear de novo
quem saiu revive a linha, que é a única leitura que a unique constraint em (Chat, usuário) permite; remover
quem já saiu não move o instante da saída.

**Dois guards estruturais novos**, ambos verificados com dentes (quebrei o código e vi falhar):
`tests/test_composition_commands.py` falha se qualquer módulo de `app/` passar a importar cliente HTTP — é
assim que "nenhum request depende do monolito" deixa de ser disciplina — e falha se aparecer qualquer rota
`GET` terminando em `users` ou `participants`, que é o "não" que a ADR-0010 diz ser fácil de desfazer sem
entender. O segundo guard eu escrevi primeiro sobre `app.routes` e ele passava **vacuamente**: FastAPI não
achata router incluído ali. Está sobre `app.openapi()` agora.

**O que a revisão apontou e eu mudei.** Eu tinha adicionado uma regra no ALB devolvendo 404 para `/internal/*`
— e ela deixaria a composição **inalcançável em produção**, porque o monolito ainda não tem presença na VPC e
o ALB público é a única entrada que existe hoje. Tirei. Ficou registrado como lacuna no
`infra/README.md` e no débito técnico, junto do ticket 18, que é onde as duas metades andam juntas: por onde o
monolito entra e o fechamento do caminho público. Também: o `name` do comando de adicionar era adotado mesmo
quando o Chat continuava 1:1, então uma reentrega nomeava um Chat que ninguém pediu para nomear; e o comando
reescrevia o papel de quem já estava no Chat, o que é evento de identidade (ticket 06) e não composição.

**O autor passou a ficar registrado, decidido com você.** A revisão apontou que `X-Acting-User` era condição
para o comando passar e nada mais: qualquer UUID válido servia e depois ninguém conseguia responder quem abriu
o Chat. `chats.created_by_user_id` (migração `f3c9a1e70b24`) recebe o acting user na criação. A coluna é
anulável e o nulo diz algo verdadeiro — Chat anterior ao ticket 05, aberto por um browser, de quem o serviço
nunca soube o nome; escrever um palpite numa coluna que existe para responder "quem fez isso" seria pior que
a lacuna. Diferente de `b7e1d0c4a92f`, as linhas antigas ficam: nenhuma regra é avaliada contra essa coluna,
então autor desconhecido não degrada nada. **Adicionar e remover Participant continuam sem atribuição** — seria
outra coluna, em `participants`.

**Duas lacunas registradas, nenhuma no escopo deste ticket:**

- **Criar grupo não é idempotente.** Só o 1:1 deduplica ([ADR-0002](../../docs/adr/0002-explicit-idempotent-chat-creation.md)).
  Um comando de grupo reentregue cria um segundo Chat idêntico. Resolve com chave de idempotência no comando,
  parente da do ticket 08.
- **`display_name` e `avatar_url` são obrigatórios no fio e não são guardados.** O armazenamento é o ticket 06;
  o contrato está fixado agora para que aquele ticket não mexa no formato do payload.

**A interface não foi tocada.** `frontend/src/lib/api.ts` já chamava `/auth/login`, `/auth/register` e `/users`,
que não existem desde o ticket 01; `createChat` entra nessa mesma lista agora. A interface é reconstruída nos
tickets 16 e 17. A coleção do Insomnia também já estava parada no ticket 04 pelo mesmo motivo.

**ADRs.** A [0010](../../docs/adr/0010-no-request-depends-on-the-monolith.md) ganhou nota dizendo o que está
de pé (a metade de composição) e o que não (o stream de identidade é o 06, os eventos de saída são o 15).
A [0002](../../docs/adr/0002-explicit-idempotent-chat-creation.md) ganhou nota de que a decisão não mudou,
só quem pode pedir.
