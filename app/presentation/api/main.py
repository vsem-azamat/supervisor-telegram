"""FastAPI application for webapp backend."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.bot_factory import create_bot
from app.core.config import settings
from app.core.container import setup_container
from app.infrastructure.db.session import create_session_maker
from app.presentation.api.routers import chats


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan events."""
    # Startup
    # Create database session maker
    session_maker = create_session_maker()

    # Create bot instance for container (though we don't need it for API)
    bot = create_bot()

    # Setup dependency injection
    setup_container(session_maker, bot)

    yield

    # Shutdown
    await bot.session.close()


app = FastAPI(
    title="Moderator Dashboard API",
    version="1.0.0",
    # Disable automatic redirect for trailing slashes to avoid HTTPS->HTTP redirects
    redirect_slashes=False,
    lifespan=lifespan,
)

# Configure CORS for webapp
allowed_origins = ["http://localhost:3000"]
if hasattr(settings, "webapp") and settings.webapp.url:
    allowed_origins.append(settings.webapp.url)
# Allow dynamic tunnel domains (ngrok and cloudflare)
tunnel_origin_regex = r"https://.*\.ngrok\.app|https://.*\.ngrok-free\.app|https://.*\.trycloudflare\.com"

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=tunnel_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# Add middleware to handle forwarded headers properly for ngrok/proxy setups
@app.middleware("http")
async def force_https_redirect(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Force HTTPS redirects to use HTTPS scheme when behind proxy."""
    # Check if request came through proxy with HTTPS (ngrok sets this header)
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto == "https":
        # Override scheme to prevent HTTP redirects from FastAPI
        request.scope["scheme"] = "https"

    return await call_next(request)


# Include routers
app.include_router(chats.router, prefix="/api/v1/chats", tags=["chats"])


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "message": "API is running"}
