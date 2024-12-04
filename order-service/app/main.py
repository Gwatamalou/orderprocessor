import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging import setup_logging
from app.core.broker import broker
from app.core.database import engine
from app.models import Base
from app.api.orders import router as orders_router
from app.api.health import router as health_router
from app.services.consumer import consumer


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await broker.connect()
    asyncio.create_task(consumer.start())

    yield

    await consumer.stop()
    await broker.close()


app = FastAPI(
    title="Order Service",
    description="Order management microservice",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(orders_router)
