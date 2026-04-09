import asyncio
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import agents, analytics, auth, campaigns, chatbot, leads, properties, webhooks
from app.scheduler.jobs import process_follow_ups_job

settings = get_settings()
scheduler = AsyncIOScheduler()


def _schedule_followups() -> None:
    asyncio.create_task(process_follow_ups_job())


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        _schedule_followups,
        "interval",
        minutes=5,
        id="bahera_followups",
        replace_existing=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Bahera API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"https://baheera-.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

v1 = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=v1)
app.include_router(leads.router, prefix=v1)
app.include_router(agents.router, prefix=v1)
app.include_router(campaigns.router, prefix=v1)
app.include_router(properties.router, prefix=v1)
app.include_router(analytics.router, prefix=v1)
app.include_router(chatbot.router, prefix=v1)
app.include_router(webhooks.router)


@app.get("/")
async def root():
    return {"name": "Bahera API", "version": "1.0.0", "docs": "Disabled in production"}


@app.get("/health")
async def health():
    return {"status": "ok"}
