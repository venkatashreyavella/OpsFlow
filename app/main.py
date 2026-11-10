from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path as FilePath
from typing import Annotated
import logging

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, selectinload

from .database import Base, engine, get_session, initialize_database, SessionLocal
from . import audit
from .auth import CurrentEmployee, current_employee, operator, router as auth_router, employee_router
from .documents import router as document_router
from .quality import router as quality_router
from .reports import router as report_router
from .models import Client, Order, OrderDirection, OrderItem, OrderStatus, Product, Shipment, SystemEvent
from .schemas import (
    ClientCreate,
    ClientRead,
    OrderCreate,
    OrderRead,
    OrderStatusUpdate,
    ProductCreate,
    ProductRead,
    ShipmentCreate,
    ShipmentRead,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    initialize_database()
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(title="OpsFlow API", version="1.0.0", lifespan=lifespan)


def business_access(request: Request, employee: CurrentEmployee):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        operator(employee)


operations = APIRouter(dependencies=[Depends(business_access)], tags=["Operations"])
DbSession = Annotated[Session, Depends(get_session)]
OrderId = Annotated[int, Path(gt=0, le=2_147_483_647)]
Offset = Annotated[int, Query(ge=0, le=2_147_483_647)]
Limit = Annotated[int, Query(ge=1, le=100)]


def commit(session: Session, conflict_detail: str) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=conflict_detail) from exc


def record_failure(request: Request, code: int, message: str) -> None:
    try:
        with SessionLocal() as session:
            session.add(SystemEvent(
                kind="security" if code in {401, 403} else "api_failure", method=request.method,
                path=request.url.path[:300], status_code=code, message=message[:500],
            ))
            session.commit()
    except Exception:
        logging.getLogger("opsflow").exception("Unable to persist a system event")


@app.exception_handler(HTTPException)
async def handle_http_error(request: Request, exc: HTTPException):
    record_failure(request, exc.status_code, str(exc.detail))
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    record_failure(request, 422, "Request validation failed")
    errors = [{key: item[key] for key in ("loc", "msg", "type")} for item in exc.errors()]
    return JSONResponse({"detail": errors}, status_code=422)


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    logging.getLogger("opsflow").exception("Unhandled API failure", exc_info=exc)
    record_failure(request, 500, "Unexpected server error")
    return JSONResponse({"detail": "The operation failed. Refresh your records before trying again"}, status_code=500)


@app.middleware("http")
async def response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    if not request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def get_order(session: Session, order_id: int) -> Order:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/health")
def health(session: DbSession) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok"}


@operations.post("/clients", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
def create_client(data: ClientCreate, session: DbSession) -> Client:
    client = Client(name=data.name, email=data.email.lower(), phone=data.phone)
    session.add(client)
    commit(session, "Client email already exists")
    return client


@operations.get("/clients", response_model=list[ClientRead])
def list_clients(session: DbSession, offset: Offset = 0, limit: Limit = 50):
    return session.scalars(select(Client).order_by(Client.id).offset(offset).limit(limit)).all()


@operations.put("/clients/{client_id}", response_model=ClientRead)
def replace_client(client_id: OrderId, data: ClientCreate, session: DbSession):
    client = session.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    client.name, client.email = data.name, str(data.email).lower()
    client.phone = data.phone
    commit(session, "Client email already exists")
    return client


@operations.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(data: ProductCreate, session: DbSession) -> Product:
    product = Product(name=data.name, sku=data.sku.upper())
    session.add(product)
    commit(session, "Product SKU already exists")
    return product


@operations.get("/products", response_model=list[ProductRead])
def list_products(session: DbSession, offset: Offset = 0, limit: Limit = 50):
    return session.scalars(select(Product).order_by(Product.id).offset(offset).limit(limit)).all()


@operations.put("/products/{product_id}", response_model=ProductRead)
def replace_product(product_id: OrderId, data: ProductCreate, session: DbSession):
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    product.name, product.sku = data.name, data.sku.upper()
    commit(session, "Product SKU already exists")
    return product


def validate_order_references(data: OrderCreate, session: Session) -> None:
    if session.get(Client, data.client_id) is None:
        raise HTTPException(status_code=404, detail="Client not found")

    product_ids = {item.product_id for item in data.items}
    existing_ids = set(session.scalars(select(Product.id).where(Product.id.in_(product_ids))))
    missing_ids = product_ids - existing_ids
    if missing_ids:
        ids = ", ".join(str(product_id) for product_id in sorted(missing_ids))
        raise HTTPException(status_code=404, detail=f"Products not found: {ids}")


@operations.post("/orders", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(data: OrderCreate, session: DbSession) -> Order:
    validate_order_references(data, session)
    order = Order(
        client_id=data.client_id,
        direction=data.direction,
        order_date=data.order_date,
        items=[
            OrderItem(product_id=item.product_id, quantity=item.quantity)
            for item in sorted(data.items, key=lambda item: item.product_id)
        ],
    )
    session.add(order)
    commit(session, "Order conflicts with existing data")
    return order


@operations.put("/orders/{order_id}", response_model=OrderRead)
def replace_order(order_id: OrderId, data: OrderCreate, session: DbSession) -> Order:
    order = session.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    validate_order_references(data, session)
    shipment = session.scalar(select(Shipment).where(Shipment.order_id == order_id))
    if shipment is not None and data.order_date > shipment.dispatch_date:
        raise HTTPException(status_code=422, detail="Order date cannot be after its shipment dispatch")
    order.client_id = data.client_id
    order.direction = data.direction
    order.order_date = data.order_date
    quantities = {item.product_id: item.quantity for item in data.items}
    current_ids = {item.product_id for item in order.items}
    for item in list(order.items):
        if item.product_id in quantities:
            item.quantity = quantities[item.product_id]
        else:
            order.items.remove(item)
    for product_id in quantities.keys() - current_ids:
        order.items.append(OrderItem(product_id=product_id, quantity=quantities[product_id]))
    order.items.sort(key=lambda item: item.product_id)
    commit(session, "Order conflicts with existing data")
    return order


@operations.get("/orders", response_model=list[OrderRead])
def list_orders(
    session: DbSession,
    direction: OrderDirection | None = None,
    status: OrderStatus | None = None,
    offset: Offset = 0,
    limit: Limit = 50,
):
    statement = select(Order).options(selectinload(Order.items))
    if direction is not None:
        statement = statement.where(Order.direction == direction)
    if status is not None:
        statement = statement.where(Order.status == status)
    return session.scalars(statement.order_by(Order.id.desc()).offset(offset).limit(limit)).all()


@operations.get("/orders/{order_id}", response_model=OrderRead)
def read_order(order_id: OrderId, session: DbSession) -> Order:
    return get_order(session, order_id)


@operations.patch("/orders/{order_id}/status", response_model=OrderRead)
def update_order_status(order_id: OrderId, data: OrderStatusUpdate, session: DbSession) -> Order:
    order = session.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if order is None:
        raise HTTPException(404, "Order not found")
    transitions = {
        OrderStatus.PENDING: {OrderStatus.PENDING, OrderStatus.PROCESSING},
        OrderStatus.PROCESSING: {OrderStatus.PROCESSING, OrderStatus.COMPLETED},
        OrderStatus.COMPLETED: {OrderStatus.COMPLETED},
    }
    if data.status not in transitions[order.status]:
        raise HTTPException(409, "Orders progress from pending to processing to completed")
    shipment = session.scalar(select(Shipment).where(Shipment.order_id == order_id))
    if data.status == OrderStatus.COMPLETED and (not shipment or not shipment.delivered_date):
        raise HTTPException(409, "Record the shipment's actual delivery date before completing the order")
    order.status = data.status
    commit(session, "Order status conflicts with existing data")
    return order


@operations.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(order_id: OrderId, session: DbSession) -> Response:
    session.delete(get_order(session, order_id))
    commit(session, "This order has a linked shipment or document and cannot be deleted")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def validate_shipment_order(data: ShipmentCreate, session: Session) -> None:
    order = session.scalar(select(Order).where(Order.id == data.order_id).with_for_update())
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if data.dispatch_date < order.order_date:
        raise HTTPException(status_code=422, detail="Dispatch cannot be before the order date")


@operations.post("/shipments", response_model=ShipmentRead, status_code=status.HTTP_201_CREATED)
def create_shipment(data: ShipmentCreate, session: DbSession) -> Shipment:
    validate_shipment_order(data, session)
    shipment = Shipment(**data.model_dump())
    session.add(shipment)
    commit(session, "This order already has a shipment, or the courier and tracking number already exist")
    return shipment


@operations.get("/shipments", response_model=list[ShipmentRead])
def list_shipments(session: DbSession, offset: Offset = 0, limit: Limit = 50):
    return session.scalars(select(Shipment).order_by(Shipment.id.desc()).offset(offset).limit(limit)).all()


def get_shipment(session: Session, shipment_id: int) -> Shipment:
    shipment = session.get(Shipment, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return shipment


@operations.get("/shipments/{shipment_id}", response_model=ShipmentRead)
def read_shipment(shipment_id: OrderId, session: DbSession) -> Shipment:
    return get_shipment(session, shipment_id)


@operations.put("/shipments/{shipment_id}", response_model=ShipmentRead)
def replace_shipment(shipment_id: OrderId, data: ShipmentCreate, session: DbSession) -> Shipment:
    shipment = get_shipment(session, shipment_id)
    if data.order_id != shipment.order_id:
        raise HTTPException(status_code=422, detail="A shipment cannot be moved to a different order")
    validate_shipment_order(data, session)
    for field, value in data.model_dump().items():
        setattr(shipment, field, value)
    commit(session, "The courier and tracking number already exist")
    return shipment


@operations.delete("/shipments/{shipment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shipment(shipment_id: OrderId, session: DbSession) -> Response:
    session.delete(get_shipment(session, shipment_id))
    commit(session, "Shipment is referenced by another record")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


app.include_router(auth_router)
app.include_router(employee_router)
app.include_router(operations)
app.include_router(document_router)
app.include_router(quality_router)
app.include_router(report_router)

# Mount after the API routes so existing API URLs and Swagger remain available.
frontend_dist = FilePath(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
