import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from datetime import datetime, timezone
from unittest.mock import patch

from app.main import app
from app.core.database import Base, get_db
from app.models.processing import ProcessingRecord, ProcessingStatus
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
    data = response.json()
    assert "status" in data
    assert "checks" in data


@pytest.mark.asyncio
async def test_process_order_success(db_session: AsyncSession, mock_broker):
    repository = ProcessingRepository(db_session)
    processor = OrderProcessor(repository)

    event = OrderCreatedEvent(
        order_id="order-success-1",
        customer_id="customer-1",
        items=[
            OrderItem(product_id="product-1", quantity=2, price=10.0)
        ],
        total_amount=20.0,
        created_at=datetime.now(timezone.utc)
    )

    with patch('random.random', return_value=0.5):
        await processor.process_order(event)

    record = await repository.get_by_order_id("order-success-1")
    assert record is not None
    assert record.order_id == "order-success-1"
    assert record.customer_id == "customer-1"
    assert record.status == ProcessingStatus.COMPLETED.value
    assert record.error_message is None
    assert record.processed_at is not None

    assert len(mock_broker) == 1
    published = mock_broker[0]
    assert published["routing_key"] == "order.processed"


@pytest.mark.asyncio
async def test_process_order_validation_failure(db_session: AsyncSession, mock_broker):
    repository = ProcessingRepository(db_session)
    processor = OrderProcessor(repository)

    event = OrderCreatedEvent(
        order_id="order-fail-1",
        customer_id="customer-2",
        items=[
            OrderItem(product_id="product-1", quantity=2, price=10.0)
        ],
        total_amount=20.0,
        created_at=datetime.now(timezone.utc)
    )

    with patch('random.random', return_value=0.1):
        await processor.process_order(event)

    record = await repository.get_by_order_id("order-fail-1")
    assert record is not None
    assert record.status == ProcessingStatus.FAILED.value
    assert record.error_message == "Random validation failure"
    assert record.retry_count == 1
    assert record.processed_at is None

    assert len(mock_broker) == 1
    published = mock_broker[0]
    assert published["routing_key"] == "order.processed"


@pytest.mark.asyncio
async def test_process_order_idempotency(db_session: AsyncSession, mock_broker):
    repository = ProcessingRepository(db_session)
    processor = OrderProcessor(repository)

    event = OrderCreatedEvent(
        order_id="order-idempotent-1",
        customer_id="customer-1",
        items=[
            OrderItem(product_id="product-1", quantity=2, price=10.0)
        ],
        total_amount=20.0,
        created_at=datetime.now(timezone.utc)
    )

    with patch('random.random', return_value=0.5):
        await processor.process_order(event)

    first_record = await repository.get_by_order_id("order-idempotent-1")
    assert first_record is not None
    assert first_record.order_id == "order-idempotent-1"

    with patch('random.random', return_value=0.5):
        await processor.process_order(event)

    from sqlalchemy import select, func
    from app.models.processing import ProcessingRecord

    result = await db_session.execute(
        select(func.count()).select_from(ProcessingRecord).where(
            ProcessingRecord.order_id == "order-idempotent-1"
        )
    )
    count = result.scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_process_order_invalid_total_amount(db_session: AsyncSession, mock_broker):
    repository = ProcessingRepository(db_session)
    processor = OrderProcessor(repository)

    event = OrderCreatedEvent(
        order_id="order-invalid-total",
        customer_id="customer-3",
        items=[
            OrderItem(product_id="product-1", quantity=1, price=10.0)
        ],
        total_amount=-5.0,
        created_at=datetime.now(timezone.utc)
    )

    with patch('random.random', return_value=0.5):
        await processor.process_order(event)

    record = await repository.get_by_order_id("order-invalid-total")
    assert record is not None
    assert record.status == ProcessingStatus.FAILED.value
    assert "Total amount must be positive" in record.error_message


@pytest.mark.asyncio
async def test_process_order_empty_items(db_session: AsyncSession, mock_broker):
    repository = ProcessingRepository(db_session)
    processor = OrderProcessor(repository)

    event = OrderCreatedEvent(
        order_id="order-empty-items",
        customer_id="customer-4",
        items=[],
        total_amount=0.0,
        created_at=datetime.now(timezone.utc)
    )

    with patch('random.random', return_value=0.5):
        await processor.process_order(event)

    record = await repository.get_by_order_id("order-empty-items")
    assert record is not None
    assert record.status == ProcessingStatus.FAILED.value
    assert "Order must contain items" in record.error_message


@pytest.mark.asyncio
async def test_process_order_invalid_quantity(db_session: AsyncSession, mock_broker):
    repository = ProcessingRepository(db_session)
    processor = OrderProcessor(repository)

    event = OrderCreatedEvent(
        order_id="order-invalid-qty",
        customer_id="customer-5",
        items=[
            OrderItem(product_id="product-1", quantity=-1, price=10.0)
        ],
        total_amount=10.0,
        created_at=datetime.now(timezone.utc)
    )

    with patch('random.random', return_value=0.5):
        await processor.process_order(event)

    record = await repository.get_by_order_id("order-invalid-qty")
    assert record is not None
    assert record.status == ProcessingStatus.FAILED.value
    assert "Invalid quantity" in record.error_message


@pytest.mark.asyncio
async def test_process_order_invalid_price(db_session: AsyncSession, mock_broker):
    repository = ProcessingRepository(db_session)
    processor = OrderProcessor(repository)

    event = OrderCreatedEvent(
        order_id="order-invalid-price",
        customer_id="customer-6",
        items=[
            OrderItem(product_id="product-1", quantity=1, price=-10.0)
        ],
        total_amount=10.0,
        created_at=datetime.now(timezone.utc)
    )

    with patch('random.random', return_value=0.5):
        await processor.process_order(event)

    record = await repository.get_by_order_id("order-invalid-price")
    assert record is not None
    assert record.status == ProcessingStatus.FAILED.value
    assert "Invalid price" in record.error_message


@pytest.mark.asyncio
async def test_process_multiple_orders(db_session: AsyncSession, mock_broker):
    repository = ProcessingRepository(db_session)
    processor = OrderProcessor(repository)

    events = [
        OrderCreatedEvent(
            order_id=f"order-multi-{i}",
            customer_id=f"customer-{i}",
            items=[
                OrderItem(product_id=f"product-{i}", quantity=i+1, price=10.0 * (i+1))
            ],
            total_amount=10.0 * (i+1) * (i+1),
            created_at=datetime.now(timezone.utc)
        )
        for i in range(5)
    ]

    with patch('random.random', return_value=0.5):
        for event in events:
            await processor.process_order(event)

    for i in range(5):
        record = await repository.get_by_order_id(f"order-multi-{i}")
        assert record is not None
        assert record.status == ProcessingStatus.COMPLETED.value

    assert len(mock_broker) == 5


@pytest.mark.asyncio
async def test_repository_get_by_order_id(db_session: AsyncSession):
    repository = ProcessingRepository(db_session)

    record = ProcessingRecord(
        order_id="test-repo-1",
        customer_id="customer-1",
        items=[{"product_id": "product-1", "quantity": 1, "price": 10.0}],
        total_amount=10.0,
        status=ProcessingStatus.PENDING.value,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    created = await repository.create(record)
    assert created.id is not None

    found = await repository.get_by_order_id("test-repo-1")
    assert found is not None
    assert found.order_id == "test-repo-1"
    assert found.customer_id == "customer-1"

    not_found = await repository.get_by_order_id("non-existent")
    assert not_found is None


@pytest.mark.asyncio
async def test_repository_update(db_session: AsyncSession):
    repository = ProcessingRepository(db_session)

    record = ProcessingRecord(
        order_id="test-update-1",
        customer_id="customer-1",
        items=[{"product_id": "product-1", "quantity": 1, "price": 10.0}],
        total_amount=10.0,
        status=ProcessingStatus.PENDING.value,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    created = await repository.create(record)
    assert created.status == ProcessingStatus.PENDING.value

    created.status = ProcessingStatus.COMPLETED.value
    created.processed_at = datetime.now(timezone.utc)

    updated = await repository.update(created)
    assert updated.status == ProcessingStatus.COMPLETED.value
    assert updated.processed_at is not None

    found = await repository.get_by_order_id("test-update-1")
    assert found.status == ProcessingStatus.COMPLETED.value
