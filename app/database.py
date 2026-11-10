import os
from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


database_url = os.getenv("DATABASE_URL", "sqlite:///./opsflow.db")
if database_url.startswith(("postgres://", "postgresql://")):
    database_url = "postgresql+psycopg://" + database_url.split("://", 1)[1]
engine = create_engine(database_url, pool_pre_ping=True)

if engine.dialect.name == "sqlite":
    # SQLite requires foreign-key enforcement to be enabled for each connection.
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys = ON")


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def initialize_database() -> None:
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(70615301)"))
        elif engine.dialect.name == "sqlite":
            connection.execute(text("BEGIN IMMEDIATE"))
        Base.metadata.create_all(connection)
        columns = {column["name"] for column in inspect(connection).get_columns("clients")}
        if "phone" not in columns:
            connection.execute(text("ALTER TABLE clients ADD COLUMN phone VARCHAR(32)"))
