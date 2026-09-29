from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    chat_token_jwks: str
    """The public key(s) the service trusts, as a JWKS document (RFC 7517).

    Read once at boot, so the service never needs the network to start
    verifying tokens. `CHAT_TOKEN_JWKS_URL` below is how a key gets rotated in
    without a redeploy; this is what makes rotation optional rather than
    required.
    """
    chat_token_jwks_url: str | None = None
    """Consulted opportunistically to pick up a rotated key. Unset means the
    service verifies against `chat_token_jwks` for as long as it runs — a
    valid, if unrotatable, configuration.
    """
    chat_token_audience: str
    """The `aud` every chat token must carry. Ties a chat token to chat and
    nothing else: the product's own token was never issued with this
    audience, and a chat token presented back to the product would fail this
    same check there.
    """
    chat_token_issuer: str | None = None
    """The `iss` every chat token must carry, when set.

    Checked by `verify_chat_token`: a token with a different `iss`, or none, is
    refused. Unset means `iss` is not checked, which keeps the service bootable
    in environments that have not been given the monolith's issuer yet.
    """
    webhook_hmac_secret: str
    internal_service_token: str
    frontend_origin: str = "http://localhost:5173"
    chat_token_ttl_seconds: int = 900
    """How long the monolith's chat tokens live, as the service is told, not as it decides.

    It mints nothing and so enforces nothing with this. What it is for is the
    denylist: an entry blocking a *person* has to expire alongside the tokens it
    blocks, and the longest any of them can still be good is one lifetime from
    the moment the event arrived. Raising it in the monolith without raising it
    here leaves a ban that lapses early.
    """


settings = Settings()
