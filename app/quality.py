import time
import re
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import TypeAdapter, EmailStr, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from .auth import Db, current_employee, operator
from .models import Client, DataIssue, Document, Order, OrderStatus, Product, Shipment, QualityRun
from .schemas import today_in_dubai
from .settings import UPLOAD_DIR


router = APIRouter(prefix="/quality", tags=["Data quality"], dependencies=[Depends(current_employee)])


def detect_issues(session: Db) -> dict:
    found = {}

    def add(code, kind, identifier, message, severity="warning"):
        fingerprint = f"{code}:{kind}:{identifier}"
        found[fingerprint] = dict(code=code, entity_type=kind, entity_id=identifier, message=message, severity=severity)

    clients = {client.id: client for client in session.scalars(select(Client))}
    products = {product.id: product for product in session.scalars(select(Product))}
    orders = session.scalars(select(Order).options(selectinload(Order.items))).all()
    shipments = {shipment.order_id: shipment for shipment in session.scalars(select(Shipment))}
    email_adapter = TypeAdapter(EmailStr)
    for client in clients.values():
        if client.phone and (not re.fullmatch(r"\+?[0-9 ()-]+", client.phone) or not 7 <= len(re.sub(r"\D", "", client.phone)) <= 15):
            add("invalid_client_phone", "clients", client.id, "Correct the client's phone number", "error")
        if not client.name.strip():
            add("missing_client_name", "clients", client.id, "Enter the client's company name", "error")
        try:
            email_adapter.validate_python(client.email)
        except ValidationError:
            add("invalid_client_email", "clients", client.id, "Correct the client's contact email", "error")
    for product in products.values():
        if not product.name.strip() or not product.sku.strip():
            add("incomplete_product", "products", product.id, "Enter a product name and SKU", "error")
    duplicates = defaultdict(list)
    for order in orders:
        if order.client_id not in clients:
            add("missing_order_client", "orders", order.id, "This order references a missing client", "error")
        if not order.items or any(item.quantity <= 0 or item.product_id not in products for item in order.items):
            add("invalid_order_items", "orders", order.id, "Correct missing products or invalid quantities", "error")
        signature = (order.client_id, order.direction, order.order_date, tuple(sorted((item.product_id, item.quantity) for item in order.items)))
        duplicates[signature].append(order.id)
        shipment = shipments.get(order.id)
        if order.status == OrderStatus.COMPLETED and (not shipment or not shipment.delivered_date):
            add("completion_without_delivery", "orders", order.id, "Order is completed but a delivered shipment is not recorded")
        if shipment:
            if shipment.delivered_date and order.status != OrderStatus.COMPLETED:
                add("delivery_status_mismatch", "orders", order.id, "Shipment is delivered. Review and complete the order")
            if not shipment.courier.strip() or not shipment.tracking_number.strip():
                add("incomplete_shipment", "shipments", shipment.id, "Enter the courier and tracking number", "error")
            if shipment.dispatch_date < order.order_date or shipment.expected_delivery_date < shipment.dispatch_date or (shipment.delivered_date and shipment.delivered_date < shipment.dispatch_date):
                add("invalid_shipment_dates", "shipments", shipment.id, "Correct the shipment's dispatch or delivery dates", "error")
            if not shipment.delivered_date and shipment.expected_delivery_date < today_in_dubai():
                add("delayed_shipment", "shipments", shipment.id, "Expected delivery has passed. Follow up with the courier")
    for identifiers in duplicates.values():
        if len(identifiers) > 1:
            for identifier in identifiers:
                add("possible_duplicate_order", "orders", identifier, "Another order has the same client, date, direction, products, and quantities. Review whether both are needed")
    for document in session.scalars(select(Document).options(selectinload(Document.versions))):
        if not document.archived and any(not (UPLOAD_DIR / version.storage_key).is_file() for version in document.versions):
            add("missing_document_file", "documents", document.id, "An uploaded file is missing from storage", "error")
    return found


def scan_quality(session: Db) -> dict:
    now = int(time.time())
    found = detect_issues(session)
    existing = {issue.fingerprint: issue for issue in session.scalars(select(DataIssue))}
    for fingerprint, values in found.items():
        issue = existing.get(fingerprint)
        if issue is None:
            issue = DataIssue(fingerprint=fingerprint, first_seen=now, **values)
            session.add(issue)
        issue.status, issue.resolved_at, issue.last_seen = "open", None, now
        issue.message = values["message"]
    for fingerprint, issue in existing.items():
        if fingerprint not in found and issue.status == "open":
            issue.status, issue.resolved_at = "resolved", now
    session.add(QualityRun(scanned_at=now, open_issues=len(found)))
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "A scan ran concurrently. Refresh the quality results") from exc
    return {"open": len(found), "scanned_at": now}


@router.post("/scan", dependencies=[Depends(operator)])
def run_scan(session: Db):
    return scan_quality(session)


@router.get("/issues")
def list_issues(session: Db, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 50):
    return session.scalars(select(DataIssue).order_by(DataIssue.id.desc()).offset(offset).limit(limit)).all()
