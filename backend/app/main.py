import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import auth, chats, internal, messages, webhook, websocket
from app.services.chat_token_keys import run_jwks_refresh
from app.services.realtime import run_subscriber


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    subscribed = asyncio.Event()
    subscriber_task = asyncio.create_task(run_subscriber(subscribed))
    await subscribed.wait()

    jwks_started = asyncio.Event()
    jwks_refresh_task = asyncio.create_task(run_jwks_refresh(jwks_started))
    await jwks_started.wait()
    try:
        yield
    finally:
        subscriber_task.cancel()
        jwks_refresh_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await subscriber_task
        with contextlib.suppress(asyncio.CancelledError):
            await jwks_refresh_task


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(chats.router)
app.include_router(internal.router)
app.include_router(messages.router)
app.include_router(webhook.router)
app.include_router(websocket.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
