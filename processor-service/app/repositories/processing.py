from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.processing import ProcessingRecord


class ProcessingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, record: ProcessingRecord) -> ProcessingRecord:
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get_by_order_id(self, order_id: str) -> Optional[ProcessingRecord]:
        result = await self.session.execute(
            select(ProcessingRecord).where(ProcessingRecord.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def update(self, record: ProcessingRecord) -> ProcessingRecord:
        await self.session.commit()
        await self.session.refresh(record)
        return record
