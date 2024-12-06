import logging
import json
from aio_pika import connect_robust, IncomingMessage, ExchangeType
from aio_pika.abc import AbstractRobustConnection
from pydantic import ValidationError

from app.core.config import settings
from app.core.database import async_session_maker
from app.repositories.processing import ProcessingRepository
from app.services.processor import OrderProcessor
from app.schemas.events import OrderCreatedEvent

logger = logging.getLogger(__name__)


class MessageConsumer:
    def __init__(self) -> None:
        self.connection: AbstractRobustConnection | None = None

    async def start(self) -> None:
        self.connection = await connect_robust(settings.rabbitmq_url)
        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=settings.rabbitmq_prefetch_count)

        exchange = await channel.declare_exchange("orders", ExchangeType.TOPIC, durable=True)

        dlx = await channel.declare_exchange("orders.dlx", ExchangeType.TOPIC, durable=True)

        dlq = await channel.declare_queue(
            "processor_service.order.created.failed",
            durable=True
        )
        await dlq.bind(dlx, routing_key="order.created.failed")

        queue = await channel.declare_queue(
            "processor_service.order.created",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "orders.dlx",
                "x-dead-letter-routing-key": "order.created.failed"
            }
        )

        await queue.bind(exchange, routing_key="order.created")

        await queue.consume(self._process_message)
        logger.info("Started consuming order.created events")

    async def _process_message(self, message: IncomingMessage) -> None:
        try:
            event_data = json.loads(message.body.decode())
            event = OrderCreatedEvent(**event_data)

            async with async_session_maker() as session:
                repository = ProcessingRepository(session)
                processor = OrderProcessor(repository)
                await processor.process_order(event)

            await message.ack()
            logger.info(f"Processed order.created event for order {event.order_id}")
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
