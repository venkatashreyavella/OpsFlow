from __future__ import annotations

from datetime import date
from enum import Enum
import time

from sqlalchemy import CheckConstraint, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy import Enum as DatabaseEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class OrderDirection(str, Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32))


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    direction: Mapped[OrderDirection] = mapped_column(
        DatabaseEnum(OrderDirection, name="order_direction", create_constraint=True)
    )
    status: Mapped[OrderStatus] = mapped_column(
        DatabaseEnum(OrderStatus, name="order_status", create_constraint=True),
        default=OrderStatus.PENDING,
    )
    order_date: Mapped[date]
    items: Mapped[list[OrderItem]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="OrderItem.product_id",
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="positive_quantity"),)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    quantity: Mapped[int]


class Shipment(Base):
    __tablename__ = "shipments"
    __table_args__ = (
        CheckConstraint("expected_delivery_date >= dispatch_date", name="valid_expected_delivery"),
        CheckConstraint(
            "delivered_date IS NULL OR delivered_date >= dispatch_date", name="valid_delivery"
        ),
        UniqueConstraint("courier", "tracking_number", name="unique_courier_tracking"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    courier: Mapped[str] = mapped_column(String(200))
    tracking_number: Mapped[str] = mapped_column(String(100))
    dispatch_date: Mapped[date]
    expected_delivery_date: Mapped[date]
    delivered_date: Mapped[date | None]


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (CheckConstraint("role IN ('admin', 'operator', 'viewer')", name="employee_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[int] = mapped_column(default=lambda: int(time.time()))


class SetupClaim(Base):
    __tablename__ = "setup_claim"

    id: Mapped[int] = mapped_column(primary_key=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    expires_at: Mapped[int]


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    action: Mapped[str] = mapped_column(String(30))
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(80))
    changes: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[int] = mapped_column(default=lambda: int(time.time()), index=True)


class SystemEvent(Base):
    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(300))
    status_code: Mapped[int]
    message: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[int] = mapped_column(default=lambda: int(time.time()), index=True)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (CheckConstraint("category IN ('invoice', 'purchase_order', 'delivery', 'other')", name="document_category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(30))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    archived: Mapped[bool] = mapped_column(default=False)
    versions: Mapped[list[DocumentVersion]] = relationship(order_by="DocumentVersion.version")


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version", name="unique_document_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    version: Mapped[int]
    original_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(50), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    created_at: Mapped[int] = mapped_column(default=lambda: int(time.time()))


class DataIssue(Base):
    __tablename__ = "data_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(120), unique=True)
    code: Mapped[str] = mapped_column(String(60))
    severity: Mapped[str] = mapped_column(String(20))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int]
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    first_seen: Mapped[int] = mapped_column(default=lambda: int(time.time()))
    last_seen: Mapped[int] = mapped_column(default=lambda: int(time.time()))
    resolved_at: Mapped[int | None]


class QualityRun(Base):
    __tablename__ = "quality_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    scanned_at: Mapped[int] = mapped_column(default=lambda: int(time.time()))
    open_issues: Mapped[int]
