# Chat

BR Wine Tours' chat as a service of its own: a microservice with its own
database, identity issued by the monolith, and an interface on a separate
domain.

## Language

**Chat**:
A container for messages between a set of participants. Covers 1:1 and group
uniformly — a 1:1 is a Chat with exactly two participants, not a separate
concept.
_Avoid_: Conversation, Conversa, Room, Sala, DM, NewChat

**Company**:
The company that owns a Chat. It is the isolation boundary: no read ever crosses
Companies.
_Avoid_: Tenant, organisation, client (in the sense of the contracting company)

**Staff Chat**:
A Chat whose participants are all from the Company. No end client inside it.
_Avoid_: Internal chat, chat interno

**Client Chat**:
A Chat that includes the end client among its participants.
_Avoid_: Negotiation, negociação, external chat

**Staff-only Message**:
A message inside a Client Chat visible only to the participants from the
Company. The end client does not receive it and does not learn it exists.
_Avoid_: Internal message, nota interna, internal note

**Participant**:
The link between a user and a Chat. Carries that user's read state in that Chat,
and the moment they left it, if they did.
_Avoid_: Member, membro

**Supervisor**:
Someone who may read their Company's Chats without being a Participant of them.
Because they are not a Participant, their reading never produces a read receipt.
_Avoid_: Admin, observer, auditor
