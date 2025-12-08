import pytest
import json
from httpx import AsyncClient
from sqlalchemy import select

from app.models.outbox import OutboxMessage
from app.repositories.outbox import OutboxRepository
from app.services.outbox_processor import OutboxProcessor


@pytest.mark.asyncio
async def test_create_order_saves_to_outbox(client: AsyncClient, db_session):
    response = await client.post("/orders", json={
        "customer_id": "customer-123",
        "items": [
            {"product_id": "product-1", "quantity": 2, "price": 10.50}
        ]
    })

    assert response.status_code == 201
    order_data = response.json()

    result = await db_session.execute(select(OutboxMessage))
    outbox_messages = list(result.scalars().all())

    assert len(outbox_messages) == 1
    message = outbox_messages[0]

    assert message.aggregate_id == order_data["id"]
    assert message.aggregate_type == "Order"
    assert message.event_type == "order.created"
    assert message.processed_at is None
    assert message.retry_count == 0

    payload = json.loads(message.payload)
    assert payload["order_id"] == order_data["id"]
    assert payload["customer_id"] == "customer-123"
    assert payload["total_amount"] == 21.0


@pytest.mark.asyncio
async def test_outbox_processor_publishes_messages(db_session, mock_broker, test_async_session_maker):
    repository = OutboxRepository(db_session)
    message = OutboxMessage(
        aggregate_id="order-123",
        aggregate_type="Order",
        event_type="order.created",
        payload='{"order_id": "order-123", "customer_id": "customer-1"}',
        created_at=db_session.bind.sync_engine.pool._creator().execute("SELECT datetime('now')").fetchone()[0]
    )
    await repository.create(message)
    await db_session.commit()

    processor = OutboxProcessor(test_async_session_maker, poll_interval=1, batch_size=10, max_retries=3)
    await processor._process_batch()

    assert len(mock_broker) == 1
    published = mock_broker[0]
    assert published["routing_key"] == "order.created"

    await db_session.refresh(message)
    assert message.processed_at is not None
    assert message.error_message is None


@pytest.mark.asyncio
async def test_outbox_processor_handles_publish_failure(db_session, monkeypatch, test_async_session_maker):
    from app.core.broker import broker

    async def mock_publish_fail(routing_key: str, message: bytes):
        raise Exception("Broker connection failed")

    monkeypatch.setattr(broker, "publish", mock_publish_fail)

    repository = OutboxRepository(db_session)
    message = OutboxMessage(
        aggregate_id="order-456",
        aggregate_type="Order",
        event_type="order.created",
        payload='{"order_id": "order-456"}',
        created_at=db_session.bind.sync_engine.pool._creator().execute("SELECT datetime('now')").fetchone()[0]
    )
    await repository.create(message)
    await db_session.commit()

    processor = OutboxProcessor(test_async_session_maker, poll_interval=1, batch_size=10, max_retries=3)
    await processor._process_batch()

    await db_session.refresh(message)
    assert message.processed_at is None
    assert message.retry_count == 1
    assert "Broker connection failed" in message.error_message


@pytest.mark.asyncio
async def test_outbox_processor_skips_max_retries(db_session, monkeypatch, test_async_session_maker):
    from app.core.broker import broker

    publish_calls = []

    async def mock_publish_track(routing_key: str, message: bytes):
        publish_calls.append(routing_key)
        raise Exception("Always fails")

    monkeypatch.setattr(broker, "publish", mock_publish_track)

    repository = OutboxRepository(db_session)
    message = OutboxMessage(
        aggregate_id="order-789",
        aggregate_type="Order",
        event_type="order.created",
        payload='{"order_id": "order-789"}',
        created_at=db_session.bind.sync_engine.pool._creator().execute("SELECT datetime('now')").fetchone()[0],
        retry_count=3
    )
    await repository.create(message)
    await db_session.commit()

    processor = OutboxProcessor(test_async_session_maker, poll_interval=1, batch_size=10, max_retries=3)
    await processor._process_batch()

    assert len(publish_calls) == 0


@pytest.mark.asyncio
async def test_outbox_repository_get_unprocessed_messages(db_session):
    repository = OutboxRepository(db_session)

    from datetime import datetime, timezone

    processed_msg = OutboxMessage(
        aggregate_id="order-1",
        aggregate_type="Order",
        event_type="order.created",
        payload='{"order_id": "order-1"}',
        created_at=datetime.now(timezone.utc),
        processed_at=datetime.now(timezone.utc)
    )
    await repository.create(processed_msg)

    unprocessed_msg1 = OutboxMessage(
        aggregate_id="order-2",
        aggregate_type="Order",
        event_type="order.created",
        payload='{"order_id": "order-2"}',
        created_at=datetime.now(timezone.utc)
    )
    await repository.create(unprocessed_msg1)

    unprocessed_msg2 = OutboxMessage(
        aggregate_id="order-3",
        aggregate_type="Order",
        event_type="order.created",
        payload='{"order_id": "order-3"}',
        created_at=datetime.now(timezone.utc)
    )
    await repository.create(unprocessed_msg2)

    await db_session.commit()

    messages = await repository.get_unprocessed_messages(limit=10)

    assert len(messages) == 2
    assert all(msg.processed_at is None for msg in messages)


@pytest.mark.asyncio
async def test_outbox_cleanup_old_messages(db_session)
    from datetime import datetime, timezone, timedelta

    repository = OutboxRepository(db_session)

    old_msg = OutboxMessage(
        aggregate_id="order-old",
        aggregate_type="Order",
        event_type="order.created",
        payload='{"order_id": "order-old"}',
        created_at=datetime.now(timezone.utc) - timedelta(hours=48),
        processed_at=datetime.now(timezone.utc) - timedelta(hours=48)
    )
    await repository.create(old_msg)

    recent_msg = OutboxMessage(
        aggregate_id="order-recent",
        aggregate_type="Order",
        event_type="order.created",
        payload='{"order_id": "order-recent"}',
        created_at=datetime.now(timezone.utc),
        processed_at=datetime.now(timezone.utc)
    )
    await repository.create(recent_msg)

    await db_session.commit()

    deleted_count = await repository.delete_processed_messages(older_than_hours=24)
    await db_session.commit()

    assert deleted_count == 1

    messages = await repository.get_unprocessed_messages(limit=100)
    result = await db_session.execute(select(OutboxMessage))
    all_messages = list(result.scalars().all())

    assert len(all_messages) == 1
    assert all_messages[0].aggregate_id == "order-recent"


@pytest.mark.asyncio
async def test_multiple_orders_create_multiple_outbox_messages(client: AsyncClient, db_session):
    response1 = await client.post("/orders", json={
        "customer_id": "customer-1",
        "items": [{"product_id": "product-1", "quantity": 1, "price": 10.00}]
    })
    assert response1.status_code == 201

    response2 = await client.post("/orders", json={
        "customer_id": "customer-2",
        "items": [{"product_id": "product-2", "quantity": 2, "price": 20.00}]
    })
    assert response2.status_code == 201

    result = await db_session.execute(select(OutboxMessage))
    outbox_messages = list(result.scalars().all())

    assert len(outbox_messages) == 2
    assert all(msg.event_type == "order.created" for msg in outbox_messages)
    assert all(msg.processed_at is None for msg in outbox_messages)
