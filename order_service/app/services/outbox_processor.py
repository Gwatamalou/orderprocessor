import asyncio
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.broker import broker
from app.repositories.outbox import OutboxRepository
from app.models.outbox import OutboxMessage

logger = logging.getLogger(__name__)


class OutboxProcessor:

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        poll_interval: int = 5,
        batch_size: int = 100,
        max_retries: int = 3
    ) -> None:
        self.session_maker = session_maker
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.max_retries = max_retries
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._running:
            logger.warning("OutboxProcessor is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("OutboxProcessor started")

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("OutboxProcessor stopped")

    async def _process_loop(self) -> None:
        while self._running:
            try:
                await self._process_batch()
            except Exception as e:
                logger.error(f"Error in outbox processor loop: {e}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    async def _process_batch(self) -> None:
        async with self.session_maker() as session:
            repository = OutboxRepository(session)

            try:
                messages = await repository.get_unprocessed_messages(limit=self.batch_size)

                if not messages:
                    return

                logger.debug(f"Processing {len(messages)} outbox messages")

                for message in messages:
                    await self._process_message(message, repository)

                await session.commit()

            except Exception as e:
                logger.error(f"Error processing outbox batch: {e}", exc_info=True)
                await session.rollback()

    async def _process_message(self, message: OutboxMessage, repository: OutboxRepository) -> None:
        if message.retry_count >= self.max_retries:
            logger.warning(
                f"Outbox message {message.id} exceeded max retries ({self.max_retries}), skipping"
            )
            return

        try:
            await broker.publish(
                message.event_type,
                message.payload.encode()
            )

            await repository.mark_as_processed(message)
            logger.info(
                f"Successfully published outbox message {message.id} "
                f"(event: {message.event_type}, aggregate: {message.aggregate_id})"
            )

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            await repository.mark_as_failed(message, error_msg)
            logger.error(
                f"Failed to publish outbox message {message.id} "
                f"(retry {message.retry_count + 1}/{self.max_retries}): {error_msg}"
            )

    async def cleanup_old_messages(self, older_than_hours: int = 24) -> int:
        async with self.session_maker() as session:
            repository = OutboxRepository(session)
            try:
                deleted_count = await repository.delete_processed_messages(older_than_hours)
                await session.commit()
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old outbox messages")
                return deleted_count
            except Exception as e:
                logger.error(f"Error cleaning up old messages: {e}", exc_info=True)
                await session.rollback()
                return 0
