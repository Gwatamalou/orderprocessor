import logging
import json
from aio_pika import connect_robust, IncomingMessage
from aio_pika.abc import AbstractRobustConnection
from pydantic import ValidationError

from app.core.config import settings
from app.core.database import async_session_maker
from app.repositories.order import OrderRepository
from app.services.order import OrderService
from app.schemas.order import OrderProcessedEvent

logger = logging.getLogger(__name__)


class MessageConsumer:
    def __init__(self) -> None:
        self.connection: AbstractRobustConnection | None = None

    async def start(self) -> None:
        self.connection = await connect_robust(settings.rabbitmq_url)
        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=settings.rabbitmq_prefetch_count)

        exchange = await channel.declare_exchange("orders", durable=True)

        dlx = await channel.declare_exchange("orders.dlx", durable=True)

        dlq = await channel.declare_queue(
            "order-service.order.processed.failed",
            durable=True
        )
        await dlq.bind(dlx, routing_key="order.processed.failed")

        queue = await channel.declare_queue(
            "order-service.order.processed",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "orders.dlx",
                "x-dead-letter-routing-key": "order.processed.failed"
            }
        )

        await queue.bind(exchange, routing_key="order.processed")

        await queue.consume(self._process_message)
        logger.info("Started consuming order.processed events")

    async def _process_message(self, message: IncomingMessage) -> None:
        try:
            event_data = json.loads(message.body.decode())
            event = OrderProcessedEvent(**event_data)

            async with async_session_maker() as session:
                repository = OrderRepository(session)
                service = OrderService(repository)
                await service.process_order_result(event)

            await message.ack()
            logger.info(f"Processed order.processed event for order {event.order_id}")
        except ValidationError as e:
            logger.error(f"Validation error processing message: {e}", exc_info=True)
            await message.reject(requeue=False)
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            await message.reject(requeue=False)

    async def stop(self) -> None:
        if self.connection:
            await self.connection.close()
            logger.info("Stopped message consumer")


consumer = MessageConsumer()
