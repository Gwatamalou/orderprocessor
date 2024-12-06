import logging
from typing import Optional
import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel

from app.core.config import settings

logger = logging.getLogger(__name__)


class RabbitMQBroker:
    def __init__(self) -> None:
        self.connection: Optional[AbstractRobustConnection] = None
        self.channel: Optional[AbstractRobustChannel] = None

    async def connect(self) -> None:
        self.connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=settings.rabbitmq_prefetch_count)

        await self.channel.declare_exchange(
            "orders",
            ExchangeType.TOPIC,
            durable=True
        )

        await self.channel.declare_exchange(
            "orders.dlx",
            ExchangeType.TOPIC,
            durable=True
        )

        logger.info("Connected to RabbitMQ")

    async def close(self) -> None:
        if self.channel:
            await self.channel.close()
        if self.connection:
            await self.connection.close()
        logger.info("Disconnected from RabbitMQ")

    async def publish(self, routing_key: str, message: bytes) -> None:
        if not self.channel:
            raise RuntimeError("Channel is not initialized")

        exchange = await self.channel.get_exchange("orders")
        await exchange.publish(
            aio_pika.Message(
                body=message,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=routing_key
        )
        logger.info(f"Published message to {routing_key}")


broker = RabbitMQBroker()
