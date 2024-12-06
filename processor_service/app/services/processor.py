import logging
import random
from datetime import datetime, timezone

from app.models.processing import ProcessingRecord, ProcessingStatus
from app.repositories.processing import ProcessingRepository
from app.schemas.events import OrderCreatedEvent, OrderProcessedEvent
from app.core.broker import broker

logger = logging.getLogger(__name__)


class OrderProcessor:
    def __init__(self, repository: ProcessingRepository) -> None:
        self.repository = repository

    async def process_order(self, event: OrderCreatedEvent) -> None:
        existing = await self.repository.get_by_order_id(event.order_id)

        if existing:
            logger.info(f"Order {event.order_id} already processed, skipping (idempotency)")
            return

        record = ProcessingRecord(
            order_id=event.order_id,
            customer_id=event.customer_id,
            items=[item.model_dump() for item in event.items],
            total_amount=event.total_amount,
            status=ProcessingStatus.PROCESSING.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        await self.repository.create(record)
        logger.info(f"Created processing record for order {event.order_id}")

        try:
            await self._validate_order(event)

            record.status = ProcessingStatus.COMPLETED.value
            record.processed_at = datetime.now(timezone.utc)
            record.updated_at = datetime.now(timezone.utc)
            await self.repository.update(record)

            result_event = OrderProcessedEvent(
                order_id=event.order_id,
                status="completed"
            )

            try:
                await broker.publish(
                    "order.processed",
                    result_event.model_dump_json().encode()
                )
                logger.info(f"Order {event.order_id} processed successfully")
            except Exception as e:
                logger.error(f"Failed to publish order.processed event for order {event.order_id}: {e}", exc_info=True)

        except Exception as e:
            record.status = ProcessingStatus.FAILED.value
            record.error_message = str(e)
            record.retry_count += 1
            record.updated_at = datetime.now(timezone.utc)
            await self.repository.update(record)

            result_event = OrderProcessedEvent(
                order_id=event.order_id,
                status="failed",
                error_message=str(e)
            )

            try:
                await broker.publish(
                    "order.processed",
                    result_event.model_dump_json().encode()
                )
            except Exception as pub_error:
                logger.error(f"Failed to publish order.processed event for order {event.order_id}: {pub_error}", exc_info=True)

            logger.error(f"Order {event.order_id} processing failed: {e}")

    async def _validate_order(self, event: OrderCreatedEvent) -> None:
        if random.random() < 0.2:
            raise ValueError("Random validation failure")

        if event.total_amount <= 0:
            raise ValueError("Total amount must be positive")

        if not event.items:
            raise ValueError("Order must contain items")

        for item in event.items:
            if item.quantity <= 0:
                raise ValueError(f"Invalid quantity for product {item.product_id}")
            if item.price <= 0:
                raise ValueError(f"Invalid price for product {item.product_id}")
