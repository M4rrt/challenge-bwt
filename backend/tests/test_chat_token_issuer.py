import pytest

from app.core.chat_token import verify_chat_token
from app.core.config import settings
from tests.chat_tokens import mint_chat_token

ISSUER = "https://api.brwinetours.com"


@pytest.fixture
def issuer_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "chat_token_issuer", ISSUER)


@pytest.mark.usefixtures("issuer_required")
def test_a_token_from_the_configured_issuer_is_accepted():
    assert verify_chat_token(mint_chat_token(issuer=ISSUER)) is not None


@pytest.mark.usefixtures("issuer_required")
def test_a_token_from_another_issuer_is_refused():
    assert verify_chat_token(mint_chat_token(issuer="https://evil.example")) is None


@pytest.mark.usefixtures("issuer_required")
def test_a_token_with_no_issuer_is_refused_when_one_is_configured():
    assert verify_chat_token(mint_chat_token(issuer=None)) is None


def test_the_issuer_is_not_checked_when_none_is_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "chat_token_issuer", None)

    assert verify_chat_token(mint_chat_token(issuer="https://anything.example")) is not None
    assert verify_chat_token(mint_chat_token(issuer=None)) is not None
