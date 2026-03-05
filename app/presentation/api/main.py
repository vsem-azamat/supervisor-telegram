"""FastAPI application for webapp backend."""

from app.core.config import settings
from app.presentation.api.routers import chats
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Moderator Bot API", version="1.0.0")

# Configure CORS for webapp
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.webapp.url] if hasattr(settings, "webapp") else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chats.router, prefix="/api/v1/chats", tags=["chats"])


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "message": "API is running"}
