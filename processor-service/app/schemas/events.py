from datetime import datetime
from typing import List
from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)
    price: float = Field(gt=0)


class OrderCreatedEvent(BaseModel):
    order_id: str
    customer_id: str
    items: List[OrderItem]
    total_amount: float
    created_at: datetime


class OrderProcessedEvent(BaseModel):
    order_id: str
    status: str
    error_message: str | None = None
