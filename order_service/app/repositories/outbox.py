from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxMessage


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, message: OutboxMessage) -> OutboxMessage:
        self.session.add(message)
        await self.session.flush()
        await self.session.refresh(message)
        return message

    async def get_unprocessed_messages(self, limit: int = 100) -> List[OutboxMessage]:
        result = await self.session.execute(
            select(OutboxMessage)
            .where(OutboxMessage.processed_at.is_(None))
            .order_by(OutboxMessage.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_as_processed(self, message: OutboxMessage) -> OutboxMessage:
        message.processed_at = datetime.now(timezone.utc)
        message.error_message = None
        await self.session.flush()
        await self.session.refresh(message)
        return message

    async def mark_as_failed(self, message: OutboxMessage, error: str) -> OutboxMessage:
        message.retry_count += 1
        message.error_message = error
        await self.session.flush()
        await self.session.refresh(message)
        return message

    async def get_by_id(self, message_id: int) -> Optional[OutboxMessage]:
        result = await self.session.execute(
            select(OutboxMessage).where(OutboxMessage.id == message_id)
        )
        return result.scalar_one_or_none()

    async def delete_processed_messages(self, older_than_hours: int = 24) -> int:
        from datetime import timedelta
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)

        result = await self.session.execute(
            select(OutboxMessage)
            .where(OutboxMessage.processed_at.isnot(None))
            .where(OutboxMessage.processed_at < cutoff_time)
        )
        messages = result.scalars().all()

        for message in messages:
            await self.session.delete(message)

        await self.session.flush()
        return len(messages)
