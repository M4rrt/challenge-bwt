import sqlalchemy as sa

from app.models.conversation import Conversation, ConversationParticipant


def test_participants_relationship_orders_by_user_id():
    relationship = sa.inspect(Conversation).relationships["participants"]

    assert relationship.order_by == (ConversationParticipant.user_id,)
