# Explicit, idempotent Chat creation

**Status:** accepted

Chats are created via an explicit `POST /chats` endpoint (participant user IDs, plus a required name for groups) rather than implicitly on the first message sent between users. This keeps message-sending a single state transition — a Chat must already exist — instead of branching on "does this chat exist yet?" inside the send path, and it extends naturally to groups, which need a name and 3+ participants chosen up front with no sensible implicit equivalent.

For 1:1 chats specifically, creation is idempotent: if a Chat with exactly the same two participants already exists, it is returned instead of creating a duplicate. Without this, a "message this user" action from a contact list would spawn a new empty chat on every click.
