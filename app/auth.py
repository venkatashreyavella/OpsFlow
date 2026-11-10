import hashlib
import hmac
import os
import secrets
import time
from typing import Annotated, Literal
from urllib.parse import urlsplit

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import EmailStr, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_session
from .models import AuthSession, Employee, SetupClaim
from .schemas import Name, RequestBody
from .settings import COOKIE_SECURE, JWT_SECRET, SESSION_SECONDS


router = APIRouter(prefix="/auth", tags=["Authentication"])
employee_router = APIRouter(prefix="/employees", tags=["Employees"])
bearer = HTTPBearer(auto_error=False)
Db = Annotated[Session, Depends(get_session)]
Password = Annotated[str, Field(min_length=12, max_length=128)]


class Login(RequestBody):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=128)]


class EmployeeCreate(RequestBody):
    name: Name
    email: Annotated[EmailStr, Field(max_length=254)]
    password: Password
    role: Literal["admin", "operator", "viewer"] = "operator"


class WorkspaceSetup(EmployeeCreate):
    setup_token: str | None = Field(default=None, max_length=256)


class EmployeeUpdate(RequestBody):
    name: Name
    email: Annotated[EmailStr, Field(max_length=254)]
    role: Literal["admin", "operator", "viewer"]
    active: bool
    password: Password | None = None


class PasswordChange(RequestBody):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: Password


def public_employee(employee: Employee) -> dict:
    return {key: getattr(employee, key) for key in ("id", "name", "email", "role", "active", "created_at")}


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"scrypt${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


DUMMY_PASSWORD = hash_password(secrets.token_urlsafe(30))


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    allowed = {value.strip() for value in os.getenv("OPSFLOW_ALLOWED_ORIGINS", "").split(",") if value.strip()}
    if urlsplit(origin).netloc != request.headers.get("host") and origin not in allowed:
        raise HTTPException(403, "This request origin is not allowed")


def current_employee(
    request: Request,
    session: Db,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Employee:
    token = credentials.credentials if credentials else request.cookies.get("opsflow_session")
    if not token:
        raise HTTPException(401, "Sign in to continue", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], issuer="opsflow", options={"require": ["exp", "iat", "sub", "jti", "csrf"]})
        employee_id = int(claims["sub"])
        token_hash = hashlib.sha256(claims["jti"].encode()).hexdigest()
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(401, "Your session expired. Sign in again") from exc
    login_session = session.get(AuthSession, token_hash)
    employee = session.get(Employee, employee_id)
    if not login_session or login_session.employee_id != employee_id or not employee or not employee.active:
        raise HTTPException(401, "Your session is no longer active")
    if not credentials and request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_origin(request)
        csrf = request.headers.get("x-opsflow-csrf", "")
        if not hmac.compare_digest(csrf, claims["csrf"]):
            raise HTTPException(403, "Refresh the page before trying this action again")
    request.state.employee = employee
    request.state.claims = claims
    request.state.token_hash = token_hash
    session.info["actor_id"] = employee.id
    return employee


CurrentEmployee = Annotated[Employee, Depends(current_employee)]


def operator(employee: CurrentEmployee) -> Employee:
    if employee.role not in {"admin", "operator"}:
        raise HTTPException(403, "Your role allows viewing records only")
    return employee


def administrator(employee: CurrentEmployee) -> Employee:
    if employee.role != "admin":
        raise HTTPException(403, "Administrator access is required")
    return employee


def commit_employee(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "This email is already registered, or setup has already been completed") from exc


def issue_session(employee: Employee, session: Session, response: Response) -> dict:
    now = int(time.time())
    jti = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    token = jwt.encode({"sub": str(employee.id), "iat": now, "exp": now + SESSION_SECONDS, "iss": "opsflow", "jti": jti, "csrf": csrf}, JWT_SECRET, algorithm="HS256")
    session.execute(delete(AuthSession).where(AuthSession.expires_at < now))
    session.add(AuthSession(token_hash=hashlib.sha256(jti.encode()).hexdigest(), employee_id=employee.id, expires_at=now + SESSION_SECONDS))
    session.commit()
    response.set_cookie("opsflow_session", token, max_age=SESSION_SECONDS, httponly=True, secure=COOKIE_SECURE, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"employee": public_employee(employee), "csrf": csrf, "access_token": token, "token_type": "bearer"}


@router.get("/status")
def setup_status(session: Db):
    required = session.get(SetupClaim, 1) is None and session.scalar(select(func.count()).select_from(Employee)) == 0
    return {"setup_required": required, "setup_token_required": required and bool(os.getenv("OPSFLOW_SETUP_TOKEN"))}


@router.post("/setup", status_code=201)
def setup(data: WorkspaceSetup, request: Request, response: Response, session: Db):
    check_origin(request)
    if session.get(SetupClaim, 1) or session.scalar(select(func.count()).select_from(Employee)):
        raise HTTPException(409, "Administrator setup has already been completed")
    setup_token = os.getenv("OPSFLOW_SETUP_TOKEN", "")
    if setup_token and not hmac.compare_digest((data.setup_token or "").encode(), setup_token.encode()):
        raise HTTPException(403, "The workspace setup code is incorrect")
    employee = Employee(name=data.name, email=str(data.email).lower(), password_hash=hash_password(data.password), role="admin")
    session.add(SetupClaim(id=1))
    session.add(employee)
    commit_employee(session)
    return issue_session(employee, session, response)


@router.post("/login")
def login(data: Login, request: Request, response: Response, session: Db):
    check_origin(request)
    employee = session.scalar(select(Employee).where(Employee.email == str(data.email).lower()))
    valid = verify_password(data.password, employee.password_hash if employee else DUMMY_PASSWORD)
    if not valid or not employee or not employee.active:
        raise HTTPException(401, "Email or password is incorrect")
    return issue_session(employee, session, response)


@router.get("/me")
def me(request: Request, employee: CurrentEmployee):
    return {"employee": public_employee(employee), "csrf": request.state.claims["csrf"]}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, session: Db, employee: CurrentEmployee):
    session.execute(delete(AuthSession).where(AuthSession.token_hash == request.state.token_hash))
    session.commit()
    response.delete_cookie("opsflow_session", httponly=True, secure=COOKIE_SECURE, samesite="strict")


@router.post("/password", status_code=204)
def change_password(data: PasswordChange, response: Response, session: Db, employee: CurrentEmployee):
    if not verify_password(data.current_password, employee.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    employee.password_hash = hash_password(data.new_password)
    session.execute(delete(AuthSession).where(AuthSession.employee_id == employee.id))
    session.commit()
    response.delete_cookie("opsflow_session", httponly=True, secure=COOKIE_SECURE, samesite="strict")


@employee_router.get("", dependencies=[Depends(administrator)])
def list_employees(session: Db, offset: int = 0, limit: Annotated[int, Query(ge=1, le=100)] = 50):
    if offset < 0:
        raise HTTPException(422, "Offset must be positive")
    return [public_employee(employee) for employee in session.scalars(select(Employee).order_by(Employee.id).offset(offset).limit(limit))]


@employee_router.post("", status_code=201, dependencies=[Depends(administrator)])
def create_employee(data: EmployeeCreate, session: Db):
    employee = Employee(name=data.name, email=str(data.email).lower(), password_hash=hash_password(data.password), role=data.role)
    session.add(employee)
    commit_employee(session)
    return public_employee(employee)


@employee_router.put("/{employee_id}", dependencies=[Depends(administrator)])
def update_employee(employee_id: int, data: EmployeeUpdate, session: Db, actor: CurrentEmployee):
    employee = session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(404, "Employee not found")
    if employee.id == actor.id and (data.role != "admin" or not data.active):
        raise HTTPException(409, "You cannot remove your own administrator access")
    employee.name, employee.email, employee.role, employee.active = data.name, str(data.email).lower(), data.role, data.active
    if data.password:
        employee.password_hash = hash_password(data.password)
    if data.password or not data.active:
        session.execute(delete(AuthSession).where(AuthSession.employee_id == employee.id))
    commit_employee(session)
    return public_employee(employee)
