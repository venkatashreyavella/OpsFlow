from datetime import date
from enum import Enum

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from .models import AuditLog, Client, Document, DocumentVersion, Employee, Order, OrderItem, Product, Shipment


AUDITED = (Client, Product, Order, OrderItem, Shipment, Employee, Document, DocumentVersion)
HIDDEN_FIELDS = {"password_hash", "storage_key"}


def value_for_log(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    return value


@event.listens_for(Session, "after_flush")
def audit_changes(session, _context):
    for action, objects in (("created", session.new), ("updated", session.dirty), ("deleted", session.deleted)):
        for record in list(objects):
            if not isinstance(record, AUDITED):
                continue
            state = inspect(record)
            changes = {}
            for column in state.mapper.columns:
                name = column.key
                if name in HIDDEN_FIELDS:
                    continue
                history = state.attrs[name].history
                if action == "updated" and not history.has_changes():
                    continue
                before = value_for_log(history.deleted[0]) if history.deleted else None
                after = value_for_log(getattr(record, name))
                changes[name] = {"before": before, "after": None if action == "deleted" else after}
            if isinstance(record, Employee) and state.attrs.password_hash.history.has_changes():
                changes["password"] = {"changed": True}
            if changes:
                identity = "/".join(str(getattr(record, column.key)) for column in state.mapper.primary_key)
                session.add(AuditLog(
                    actor_id=session.info.get("actor_id"), action=action,
                    entity_type=record.__tablename__, entity_id=identity, changes=changes,
                ))
