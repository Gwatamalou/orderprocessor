from datetime import datetime
from typing import List
from pydantic import BaseModel, Field, field_validator


class OrderItem(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)
    price: float = Field(gt=0)


class OrderCreate(BaseModel):
    customer_id: str
    items: List[OrderItem] = Field(min_length=1)

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: List[OrderItem]) -> List[OrderItem]:
        if not v:
            raise ValueError("Order must contain at least one item")
        return v


class OrderResponse(BaseModel):
    id: str
    customer_id: str
    items: List[OrderItem]
    total_amount: float
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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
