# No request of the service depends on the monolith

**Status:** accepted

No request path in chat queries the monolith. What needs fresh data arrives by
routes that never block the service: **commands** the monolith sends, **events**
it publishes, and **claims** in the chat token. The product's hot path — sending
and reading messages, keeping the WebSocket up — does not have the monolith in
it.

This does not forbid traffic between the two: it forbids a **synchronous
dependency from the service on the monolith** inside a request. The two
directions that do exist are one-way and block nothing: the monolith commands,
and the service publishes events.

## Composition belongs to the monolith, and arrives as a command

Creating a chat and adding or removing a participant need to know, freshly,
whether each user belongs to that company and is active — and, for clients,
whether they are a contact of that company, which is a CRM query impossible to
mirror. Those validations run in the monolith, against local data, and it then
**calls the service**, with a service token and a mandatory header naming the
user it is acting for: without it the service refuses, because there is no chat
without an author. That is what stops the service token becoming an omnipotent
credential — it does not widen what can be done, it only allows doing it on
behalf of someone identified.

**The command carries each participant's identity.** The monolith already had
that data in hand to validate, so sending it along costs nothing and removes the
one case that would force the service to ask back. The service validates what is
its own business — the shape of the chat — and does not re-check what whoever
signed the command is already the authority on.

An alternative considered and rejected was a **signed pass**: the monolith would
validate and hand the interface a short-lived pass to present to the service. It
removes even the monolith-to-service call, but it does not cover a chat born from
a business event — a negotiation opens, a chat opens — where there is no
browser to carry any pass. A monolith-to-service call creates no dependency of
the service on anything: if the service is down, composition fails, which it
would anyway.

## The "no" that is easy to undo without understanding

**The list of who may participate stays in the monolith and does not come here.**
Who is a client of a company is a CRM fact, not a chat fact; mirroring it would
mean mirroring the contact book and its churn. Someone will propose "bring this
into chat so the interface talks to one origin" — this section is the answer.

## Consequences

Monolith down means no new chats and no new participants; existing chats keep
sending and receiving normally. That is a far better degradation profile than the
reverse, and it is what justifies the extraction.

The interface talks to two origins — the service for chat, the monolith
for composition and for obtaining a chat token — which requires CORS on the
monolith for the chat's origin.

In the outbound direction there is **one** path, asynchronous and one-way: the
service publishes events the monolith consumes to decide push notification. That
keeps FCM credentials, device tokens and notification i18n out of the service: it
knows *when* something happened, the monolith knows *to whom and how* to tell.
Delivery is at-least-once, with an event id for deduplication on the far side.

The network enforces the rule: the internal routes are not public, and each
security group opens a direction only to the other end.
