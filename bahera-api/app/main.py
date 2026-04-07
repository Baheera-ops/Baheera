"""
BAHERA API — Main application entry point.
Mounts all routers, configures CORS, lifespan events.
Run with: uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import agents, analytics, auth, campaigns, chatbot, leads, properties, webhooks

settings = get_settings()

from fastapi.middleware.cors import CORSMiddleware
 
app = FastAPI()
 
app.add_middleware(

    CORSMiddleware,

    allow_origins=["https://baheera-qpbooya1t-baheera-ops-projects.vercel.app"],  # Your Vercel URL

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)
 

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup: verify DB connection, warm caches
    print(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    yield
    # Shutdown: cleanup
    print("Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered real estate lead generation and qualification platform",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# ── CORS ─────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Route mounting ───────────────────────────────────────────────────
app.include_router(auth.router,       prefix="/api/v1")
app.include_router(leads.router,      prefix="/api/v1")
app.include_router(chatbot.router,    prefix="/api/v1")
app.include_router(campaigns.router,  prefix="/api/v1")
app.include_router(agents.router,     prefix="/api/v1")
app.include_router(analytics.router,  prefix="/api/v1")
app.include_router(properties.router, prefix="/api/v1")
app.include_router(webhooks.router)  # Public — no /api/v1 prefix


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.APP_VERSION}


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs" if settings.DEBUG else "Disabled in production",
    }
