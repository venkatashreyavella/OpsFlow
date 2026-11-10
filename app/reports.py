from collections import Counter
import csv
from html import escape
import io
import json
from pathlib import Path
from typing import Annotated
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .auth import Db, administrator, current_employee
from .models import AuditLog, Client, DataIssue, Document, Order, Product, Shipment, SystemEvent, QualityRun
from .schemas import ShipmentRead


router = APIRouter(tags=["Reporting"], dependencies=[Depends(current_employee)])


@router.get("/audit", dependencies=[Depends(administrator)])
def audit_log(session: Db, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 50):
    return session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).offset(offset).limit(limit)).all()


@router.get("/system/events", dependencies=[Depends(administrator)])
def system_events(session: Db, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 50):
    return session.scalars(select(SystemEvent).order_by(SystemEvent.id.desc()).offset(offset).limit(limit)).all()


@router.get("/reports/summary")
def summary(session: Db):
    orders = session.scalars(select(Order)).all()
    shipments = session.scalars(select(Shipment)).all()
    clients = {client.id: client.name for client in session.scalars(select(Client))}
    issues = session.scalars(select(DataIssue)).all()
    states = Counter(order.status.value for order in orders)
    directions = Counter(order.direction.value for order in orders)
    shipment_states = Counter(ShipmentRead.model_validate(shipment).status for shipment in shipments)
    months = Counter(order.order_date.strftime("%Y-%m") for order in orders)
    client_counts = Counter(order.client_id for order in orders)
    delivered = [shipment for shipment in shipments if shipment.delivered_date]
    on_time = sum(shipment.delivered_date <= shipment.expected_delivery_date for shipment in delivered)
    return {
        "orders": len(orders), "statuses": states, "directions": directions,
        "shipments": len(shipments), "shipment_statuses": shipment_states,
        "open_issues": sum(issue.status == "open" for issue in issues),
        "last_scan": session.scalar(select(QualityRun.scanned_at).order_by(QualityRun.id.desc()).limit(1)),
        "on_time_percentage": round(on_time * 100 / len(delivered), 1) if delivered else None,
        "monthly": [{"month": month, "orders": count} for month, count in sorted(months.items())],
        "by_client": [{"client": clients.get(identifier, "Missing client"), "orders": count} for identifier, count in client_counts.most_common()],
        "issues_by_code": Counter(issue.code for issue in issues if issue.status == "open"),
    }


def export_tables(session: Db) -> dict:
    orders = session.scalars(select(Order).options(selectinload(Order.items))).all()
    shipments = session.scalars(select(Shipment)).all()
    return {
        "orders": (["id", "client_id", "direction", "status", "order_date", "quantity"], [
            [order.id, order.client_id, order.direction.value, order.status.value, order.order_date, sum(item.quantity for item in order.items)] for order in orders
        ]),
        "order_items": (["order_id", "product_id", "quantity"], [[order.id, item.product_id, item.quantity] for order in orders for item in order.items]),
        "clients": (["id", "name", "email", "phone"], [[client.id, client.name, client.email, client.phone] for client in session.scalars(select(Client))]),
        "products": (["id", "sku", "name"], [[product.id, product.sku, product.name] for product in session.scalars(select(Product))]),
        "shipments": (["id", "order_id", "courier", "tracking_number", "dispatch_date", "expected_delivery_date", "delivered_date", "status"], [
            [shipment.id, shipment.order_id, shipment.courier, shipment.tracking_number, shipment.dispatch_date, shipment.expected_delivery_date, shipment.delivered_date, ShipmentRead.model_validate(shipment).status] for shipment in shipments
        ]),
        "data_issues": (["id", "code", "severity", "entity_type", "entity_id", "message", "status"], [
            [issue.id, issue.code, issue.severity, issue.entity_type, issue.entity_id, issue.message, issue.status] for issue in session.scalars(select(DataIssue))
        ]),
    }


def csv_bytes(headers, rows) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        # Keep spreadsheet programs from interpreting user-entered text as formulas.
        safe = ["'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value for value in row]
        writer.writerow(safe)
    return output.getvalue().encode("utf-8-sig")


@router.get("/reports/export/{dataset}.csv")
def export_csv(dataset: str, session: Db):
    tables = export_tables(session)
    if dataset not in tables:
        raise HTTPException(404, "Report dataset not found")
    return Response(csv_bytes(*tables[dataset]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="opsflow-{dataset}.csv"', "Cache-Control": "no-store"})


@router.get("/reports/powerbi.zip")
def powerbi_bundle(session: Db):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, (headers, rows) in export_tables(session).items():
            archive.writestr(f"{name}.csv", csv_bytes(headers, rows))
        report_dir = Path(__file__).resolve().parent.parent / "reports"
        for name in ("POWER_BI.md", "measures.dax"):
            archive.writestr(name, (report_dir / name).read_bytes())
    return Response(output.getvalue(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="opsflow-powerbi.zip"', "Cache-Control": "no-store"})


@router.get("/reports/orders/{order_id}")
def order_report(order_id: int, session: Db):
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    client = session.get(Client, order.client_id)
    products = {product.id: product for product in session.scalars(select(Product))}
    shipment = session.scalar(select(Shipment).where(Shipment.order_id == order.id))
    rows = "".join(f"<tr><td>{escape(products[item.product_id].sku)}</td><td>{escape(products[item.product_id].name)}</td><td>{item.quantity}</td></tr>" for item in order.items)
    shipment_html = "Shipment has not been recorded."
    if shipment:
        shipment_html = f"{escape(shipment.courier)} · {escape(shipment.tracking_number)}<br>Dispatch {shipment.dispatch_date} · Expected {shipment.expected_delivery_date}<br>Delivered {shipment.delivered_date or 'Awaiting delivery'}"
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>OpsFlow order {order.id}</title>
    <style>body{{font:15px/1.8 system-ui;color:#283248;max-width:850px;margin:60px auto;padding:24px}}h1{{color:#6550d7}}small{{color:#68758c}}table{{width:100%;border-collapse:collapse;margin:30px 0}}th,td{{text-align:left;border-bottom:1px solid #ddd;padding:12px}}th{{background:#f4f2fc}}section{{margin-top:30px}}@media print{{body{{margin:0}}}}</style>
    <header><h1>OpsFlow</h1><small>ORDER REPORT</small><h2>ORD-{order.id:04d}</h2></header>
    <section><strong>{escape(client.name if client else 'Missing client')}</strong><br>{escape(client.email if client else '')}<br>Order date {order.order_date}<br>{order.direction.value.title()} · {order.status.value.title()}</section>
    <table><thead><tr><th>SKU</th><th>Product</th><th>Quantity</th></tr></thead><tbody>{rows}</tbody></table>
    <p><strong>Total units {sum(item.quantity for item in order.items)}</strong></p><section><h3>Shipment</h3>{shipment_html}</section>
    <footer><hr><small>Generated from the OpsFlow operations database. Use your browser's Print command to save a PDF copy.</small></footer></html>'''
    return Response(html, media_type="text/html", headers={"Content-Disposition": f'attachment; filename="opsflow-order-{order.id}.html"', "Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})
