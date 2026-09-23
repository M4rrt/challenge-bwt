# 15 — Outbound push events

**What to build:** A Participant who is not connected still hears about a message addressed to them, because the service tells the monolith something happened and the monolith decides whom to tell and how.

This is the only outbound path in the whole design, and it is asynchronous and one-way. Keeping it that way is what keeps push credentials, device tokens and notification wording out of the service: it knows *when*, the monolith knows *to whom and how*. Delivery is at-least-once, with an event id so the far side can deduplicate.

**Blocked by:** 07, 21.

**Status:** ready-for-agent

- [ ] Message events are published to the monolith from the same outbox as the realtime fan-out
- [ ] Each event carries an id for deduplication on the far side
- [ ] Delivery is at-least-once and retried; a backlog never slows down or fails a message send
- [ ] No push credential, device token or notification text exists anywhere in the service
- [ ] The event carries enough for the monolith to decide recipients, and no message body it does not need

## Comments

**2026-09-23 — por que o [21](21-the-outbox-survives-a-bad-row-and-time.md) entrou como bloqueador.**

Este ticket põe uma chamada HTTP ao monólito no mesmo caminho do drain. Hoje o drain só faz `redis.publish`, onde o que falha é conexão e isso derruba todas as linhas igualmente. Com HTTP, uma linha específica que o outro lado rejeita com `400` é comum — e `drain_once` sempre pega a linha pendente mais antiga, então essa linha seria retomada para sempre e tudo atrás dela nunca sairia.

O 21 dá à linha uma contagem de tentativas e um estado terminal. Sem ele, este ticket transforma um risco improvável numa parada de tempo real esperando acontecer.
