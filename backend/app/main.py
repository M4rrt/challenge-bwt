from fastapi import FastAPI

from app.routers import auth, conversations

app = FastAPI()
app.include_router(auth.router)
app.include_router(conversations.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
