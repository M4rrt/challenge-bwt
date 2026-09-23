# Explicit, idempotent Chat creation

**Status:** accepted

Chats are created by an explicit creation command (each Participant's identity, plus a required name for groups) rather than implicitly on the first message sent between users. This keeps message-sending a single state transition — a Chat must already exist — instead of branching on "does this chat exist yet?" inside the send path, and it extends naturally to groups, which need a name and 3+ participants chosen up front with no sensible implicit equivalent.

For 1:1 chats specifically, creation is idempotent: if a Chat with exactly the same two participants already exists, it is returned instead of creating a duplicate. Without this, a "message this user" action from a contact list would spawn a new empty chat on every click.

**Where the route went.** Ticket 05 moved creation off the public surface: it is
`POST /internal/chats`, sent by the monolith with a service credential and a
header naming the user it acts for
([ADR-0010](0010-no-request-depends-on-the-monolith.md)). The decision above is
untouched by that — creation is still explicit rather than implicit in the send
path, and a 1:1 is still idempotent — only who is allowed to ask has changed.
