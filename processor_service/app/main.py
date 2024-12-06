import asyncio
import signal
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging import setup_logging
from app.core.broker import broker
from app.core.database import engine, Base
from app.core.config import settings
from app.api.health import router as health_router
from app.services.consumer import consumer


shutdown_event = asyncio.Event()


async def shutdown_handler() -> None:
    shutdown_event.set()


def handle_signal(sig: int, frame: object) -> None:
    asyncio.create_task(shutdown_handler())


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await broker.connect()
    asyncio.create_task(consumer.start())

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    yield

    await consumer.stop()
    await broker.close()
    await engine.dispose()


app = FastAPI(
    title="Processor Service",
    description="Order processing microservice",
    version="0.1.0",
    lifespan=lifespan
)

cors_origins = settings.cors_origins.split(",") if settings.cors_origins else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
