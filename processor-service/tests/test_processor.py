import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from datetime import datetime

from app.main import app
from app.core.database import Base, get_db
from app.repositories.processing import ProcessingRepository
from app.services.processor import OrderProcessor
from app.schemas.events import OrderCreatedEvent, OrderItem


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_process_order_idempotency(db_session: AsyncSession):
    repository = ProcessingRepository(db_session)
    processor = OrderProcessor(repository)

    event = OrderCreatedEvent(
        order_id="order-123",
        customer_id="customer-456",
        items=[OrderItem(product_id="product-1", quantity=2, price=10.0)],
        total_amount=20.0,
        created_at=datetime.utcnow()
    )

    await processor.process_order(event)
    first_record = await repository.get_by_order_id("order-123")
    assert first_record is not None

    await processor.process_order(event)
    second_record = await repository.get_by_order_id("order-123")

    assert first_record.id == second_record.id
