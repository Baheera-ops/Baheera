import asyncio
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.modules.agents.router import router as agents_router
from app.modules.campaigns.router import router as campaigns_router
from app.modules.leads.router import router as leads_router
from app.modules.properties.router import router as properties_router
from app.modules.settings.router import router as settings_router
from app.modules.webhooks.meta import router as meta_webhook_router
from app.modules.webhooks.widget import router as widget_webhook_router
from app.scheduler.jobs import process_follow_ups_job

settings = get_settings()
scheduler = AsyncIOScheduler()


def _schedule_followups() -> None:
    asyncio.create_task(process_follow_ups_job())


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(_schedule_followups, "interval", minutes=5, id="bahera_followups", replace_existing=True)
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
app.include_router(leads_router, prefix=v1)
app.include_router(agents_router, prefix=v1)
app.include_router(campaigns_router, prefix=v1)
app.include_router(properties_router, prefix=v1)
app.include_router(settings_router, prefix=v1)
app.include_router(meta_webhook_router)
app.include_router(widget_webhook_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
