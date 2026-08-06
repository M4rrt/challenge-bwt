import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import auth, conversations, messages, users, websocket
from app.services.realtime import run_subscriber


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    subscriber_task = asyncio.create_task(run_subscriber())
    try:
        yield
    finally:
        subscriber_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await subscriber_task


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(conversations.router)
app.include_router(messages.router)
app.include_router(users.router)
app.include_router(websocket.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
