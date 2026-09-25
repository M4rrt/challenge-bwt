from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
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
