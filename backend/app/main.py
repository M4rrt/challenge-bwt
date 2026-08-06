from fastapi import FastAPI

from app.routers import auth, conversations, messages

app = FastAPI()
app.include_router(auth.router)
app.include_router(conversations.router)
app.include_router(messages.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
