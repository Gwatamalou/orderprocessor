from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.order import OrderRepository
from app.repositories.outbox import OutboxRepository
from app.services.order import OrderService
from app.schemas.order import OrderCreate, OrderResponse

router = APIRouter(prefix="/orders", tags=["orders"])


def get_order_service(db: AsyncSession = Depends(get_db)) -> OrderService:
    repository = OrderRepository(db)
    outbox_repository = OutboxRepository(db)
    return OrderService(repository, outbox_repository)


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    service: OrderService = Depends(get_order_service)
) -> OrderResponse:
    return await service.create_order(order_data)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    service: OrderService = Depends(get_order_service)
) -> OrderResponse:
    order = await service.get_order(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found"
        )
    return order
