from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo
import re

from pydantic import (
    BaseModel, ConfigDict, EmailStr, Field, StringConstraints,
    computed_field, field_validator, model_validator,
)

from .models import OrderDirection, OrderStatus


Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200, pattern=r"^[^\x00]+$"),
]
Sku = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
]
PositiveInteger = Annotated[int, Field(strict=True, gt=0, le=2_147_483_647)]


class RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClientCreate(RequestBody):
    name: Name
    email: Annotated[EmailStr, Field(max_length=254)]
    phone: str | None = Field(default=None, max_length=32)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not re.fullmatch(r"\+?[0-9 ()-]+", value) or not 7 <= len(re.sub(r"\D", "", value)) <= 15:
            raise ValueError("Enter a phone number containing 7 to 15 digits")
        return value


class ClientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    phone: str | None = None


class ProductCreate(RequestBody):
    sku: Sku
    name: Name


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str


class OrderItemCreate(RequestBody):
    product_id: PositiveInteger
    quantity: PositiveInteger


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    quantity: int


class OrderCreate(RequestBody):
    client_id: PositiveInteger
    direction: OrderDirection
    order_date: date
    items: list[OrderItemCreate] = Field(min_length=1, max_length=100)

    @field_validator("items")
    @classmethod
    def ensure_unique_products(cls, items: list[OrderItemCreate]) -> list[OrderItemCreate]:
        if len({item.product_id for item in items}) != len(items):
            raise ValueError("Each product can appear only once per order")
        return items


class OrderStatusUpdate(RequestBody):
    status: OrderStatus


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    direction: OrderDirection
    status: OrderStatus
    order_date: date
    items: list[OrderItemRead]


def today_in_dubai() -> date:
    return datetime.now(ZoneInfo("Asia/Dubai")).date()


class ShipmentCreate(RequestBody):
    order_id: PositiveInteger
    courier: Name
    tracking_number: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[^\x00]+$"),
    ]
    dispatch_date: date
    expected_delivery_date: date
    delivered_date: date | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.expected_delivery_date < self.dispatch_date:
            raise ValueError("Expected delivery must be on or after dispatch")
        if self.delivered_date is not None:
            if self.delivered_date < self.dispatch_date:
                raise ValueError("Delivery must be on or after dispatch")
            if self.delivered_date > today_in_dubai():
                raise ValueError("Actual delivery cannot be in the future")
        return self


class ShipmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    courier: str
    tracking_number: str
    dispatch_date: date
    expected_delivery_date: date
    delivered_date: date | None

    @computed_field
    @property
    def status(self) -> str:
        if self.delivered_date is not None:
            return "delivered"
        if self.expected_delivery_date < today_in_dubai():
            return "delayed"
        if self.dispatch_date > today_in_dubai():
            return "scheduled"
        return "in_transit"
