# Multi-user Chat

A real-time chat application where multiple users exchange messages, with strict isolation between conversations they don't participate in.

## Language

**Conversation**:
A container for messages between a set of participants. Covers both 1:1 and group chats uniformly — a 1:1 is a Conversation with exactly two participants, not a separate concept.
_Avoid_: Room, Chat, Sala, DM
