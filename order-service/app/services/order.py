import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.models.order import Order, OrderStatus
from app.repositories.order import OrderRepository
from app.schemas.order import OrderCreate, OrderResponse, OrderCreatedEvent, OrderProcessedEvent, OrderItem
from app.core.broker import broker

logger = logging.getLogger(__name__)


class OrderService:
    def __init__(self, repository: OrderRepository) -> None:
        self.repository = repository

    async def create_order(self, order_data: OrderCreate) -> OrderResponse:
        total_amount = sum(item.price * item.quantity for item in order_data.items)

        order = Order(
            id=str(uuid.uuid4()),
            customer_id=order_data.customer_id,
            items=[item.model_dump() for item in order_data.items],
            total_amount=total_amount,
            status=OrderStatus.PENDING.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        created_order = await self.repository.create(order)

        event = OrderCreatedEvent(
            order_id=created_order.id,
            customer_id=created_order.customer_id,
            items=order_data.items,
            total_amount=total_amount,
            created_at=created_order.created_at
        )

        try:
            await broker.publish(
                "order.created",
                event.model_dump_json().encode()
            )
            logger.info(f"Order created: {created_order.id}")
        except Exception as e:
            logger.error(f"Failed to publish order.created event for order {created_order.id}: {e}", exc_info=True)

        return OrderResponse(
            id=created_order.id,
            customer_id=created_order.customer_id,
            items=[OrderItem(**item) for item in created_order.items],
            total_amount=float(created_order.total_amount),
            status=created_order.status,
            error_message=created_order.error_message,
            created_at=created_order.created_at,
            updated_at=created_order.updated_at
        )

    async def get_order(self, order_id: str) -> Optional[OrderResponse]:
        order = await self.repository.get_by_id(order_id)
        if not order:
            return None

        return OrderResponse(
            id=order.id,
            customer_id=order.customer_id,
            items=[OrderItem(**item) for item in order.items],
            total_amount=float(order.total_amount),
            status=order.status,
            error_message=order.error_message,
            created_at=order.created_at,
            updated_at=order.updated_at
        )

    async def process_order_result(self, event: OrderProcessedEvent) -> None:
        order = await self.repository.get_by_id(event.order_id)
        if not order:
            logger.error(f"Order not found: {event.order_id}")
            return

        order.status = event.status
        order.error_message = event.error_message
        order.updated_at = datetime.now(timezone.utc)

        await self.repository.update(order)
        logger.info(f"Order updated: {order.id}, status: {order.status}")
