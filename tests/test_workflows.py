import io
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile
from urllib.parse import urlsplit


scratch = TemporaryDirectory(prefix="opsflow-tests-")
test_database_url = os.getenv("OPSFLOW_TEST_DATABASE_URL")
if test_database_url and not urlsplit(test_database_url).path.endswith("_test"):
    raise RuntimeError("The dedicated PostgreSQL test database name must end in _test")
os.environ["DATABASE_URL"] = test_database_url or "sqlite:///" + (Path(scratch.name) / "test.db").as_posix()
os.environ["OPSFLOW_DATA_DIR"] = str(Path(scratch.name) / "storage")

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import Base, SessionLocal, engine, initialize_database
from app.main import app
from app.models import AuthSession, Client, DocumentVersion, Employee, Order, SystemEvent
from app.schemas import today_in_dubai
from app.settings import UPLOAD_DIR


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(engine)
        self.api = TestClient(app)
        self.api.__enter__()
        self.password = "Test-password-123!"
        self.setup = {"name": "Test Admin", "email": "admin@example.com", "password": self.password}
        response = self.api.post("/auth/setup", json=self.setup)
        self.assertEqual(response.status_code, 201, response.text)
        self.token = response.json()["access_token"]
        self.csrf = response.json()["csrf"]
        self.api.headers["Authorization"] = f"Bearer {self.token}"

    def tearDown(self):
        self.api.__exit__(None, None, None)

    def catalog(self):
        client = self.api.post("/clients", json={"name": "Falcon Networks", "email": "falcon@example.com", "phone": "+971 50 123 4567"})
        product = self.api.post("/products", json={"name": "<Network switch>", "sku": "NET-001"})
        self.assertEqual(client.status_code, 201, client.text)
        self.assertEqual(product.status_code, 201, product.text)
        return client.json(), product.json()

    def order(self):
        client, product = self.catalog()
        body = {"client_id": client["id"], "direction": "outgoing", "order_date": today_in_dubai().isoformat(), "items": [{"product_id": product["id"], "quantity": 20}]}
        response = self.api.post("/orders", json=body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json(), body

    def employee(self, role="viewer"):
        response = self.api.post("/employees", json={"name": "Test Employee", "email": "employee@example.com", "password": self.password, "role": role})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_setup_claim_and_authentication(self):
        self.assertEqual(self.api.post("/auth/setup", json=self.setup).status_code, 409)
        self.assertFalse(self.api.get("/auth/status").json()["setup_required"])
        self.assertEqual(self.api.get("/auth/me").json()["employee"]["role"], "admin")
        with TestClient(app) as anonymous:
            self.assertEqual(anonymous.get("/orders").status_code, 401)
            self.assertEqual(anonymous.post("/auth/login", json={"email": "admin@example.com", "password": "incorrect"}).status_code, 401)
        with SessionLocal() as session:
            stored = session.scalar(select(Employee))
            self.assertNotIn(self.password, stored.password_hash)
            self.assertTrue(session.scalars(select(SystemEvent)).all())

    def test_public_setup_requires_private_code(self):
        Base.metadata.drop_all(engine)
        initialize_database()
        with patch.dict(os.environ, {"OPSFLOW_SETUP_TOKEN": "private-workspace-setup-code"}):
            status = self.api.get('/auth/status').json()
            self.assertTrue(status['setup_required'])
            self.assertTrue(status['setup_token_required'])
            self.assertNotIn('private-workspace-setup-code', str(status))
            self.assertEqual(self.api.post('/auth/setup', json=self.setup).status_code, 403)
            self.assertEqual(self.api.post('/auth/setup', json={**self.setup, 'setup_token':'wrong'}).status_code, 403)
            created = self.api.post('/auth/setup', json={**self.setup, 'setup_token':'private-workspace-setup-code'})
            self.assertEqual(created.status_code, 201, created.text)
            self.assertFalse(self.api.get('/auth/status').json()['setup_token_required'])
            self.assertEqual(self.api.post('/auth/setup', json={**self.setup, 'setup_token':'private-workspace-setup-code'}).status_code, 409)

    def test_cookie_csrf_origin_and_logout_revocation(self):
        self.api.headers.pop("Authorization")
        self.assertEqual(self.api.post("/clients", json={"name": "Blocked", "email": "blocked@example.com"}).status_code, 403)
        self.api.headers["X-OpsFlow-CSRF"] = self.csrf
        self.assertEqual(self.api.post("/clients", json={"name": "Good", "email": "good@example.com"}).status_code, 201)
        self.assertEqual(self.api.post("/auth/logout", headers={"Origin": "https://untrusted.example"}).status_code, 403)
        self.assertEqual(self.api.post("/auth/logout").status_code, 204)
        self.assertEqual(self.api.get("/orders", headers={"Authorization": f"Bearer {self.token}"}).status_code, 401)

    def test_roles_and_employee_administration(self):
        employee = self.employee()
        with TestClient(app) as viewer:
            login = viewer.post("/auth/login", json={"email": employee["email"], "password": self.password}).json()
            viewer.headers["Authorization"] = "Bearer " + login["access_token"]
            self.assertEqual(viewer.get("/orders").status_code, 200)
            self.assertEqual(viewer.post("/products", json={"name": "No", "sku": "NO"}).status_code, 403)
            self.assertEqual(viewer.get("/employees").status_code, 403)
            self.assertEqual(viewer.get("/audit").status_code, 403)
            update = {"name": employee["name"], "email": employee["email"], "role": "operator", "active": True}
            self.assertEqual(self.api.put(f"/employees/{employee['id']}", json=update).status_code, 200)
            self.assertEqual(viewer.post("/products", json={"name": "Allowed", "sku": "YES"}).status_code, 201)
            update["active"] = False
            self.assertEqual(self.api.put(f"/employees/{employee['id']}", json=update).status_code, 200)
            self.assertEqual(viewer.get("/orders").status_code, 401)
        admin_id = self.api.get("/auth/me").json()["employee"]["id"]
        self.assertEqual(self.api.put(f"/employees/{admin_id}", json={"name": "Admin", "email": "admin@example.com", "role": "viewer", "active": True}).status_code, 409)

    def test_password_change_revokes_sessions_and_redacts_audit(self):
        self.assertEqual(self.api.post("/auth/password", json={"current_password": "wrong", "new_password": "Different-password-123!"}).status_code, 400)
        self.assertEqual(self.api.post("/auth/password", json={"current_password": self.password, "new_password": "Different-password-123!"}).status_code, 204)
        self.assertEqual(self.api.get("/orders").status_code, 401)
        login = self.api.post("/auth/login", json={"email": "admin@example.com", "password": "Different-password-123!"})
        self.api.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        history = self.api.get("/audit").text
        self.assertNotIn("scrypt$", history)
        self.assertNotIn("Different-password-123!", history)

    def test_order_validation_edit_and_workflow(self):
        order, body = self.order()
        path = f"/orders/{order['id']}"
        self.assertEqual(self.api.post("/orders", json={**body, "items": [{"product_id": body["items"][0]["product_id"], "quantity": 0}]}).status_code, 422)
        self.assertEqual(self.api.post("/orders", json={**body, "items": body["items"] * 2}).status_code, 422)
        self.assertEqual(self.api.put(path, json={**body, "items": [{"product_id": 99999, "quantity": 2}]}).status_code, 404)
        self.assertEqual(self.api.get(path).json()["items"], order["items"])
        updated = {**body, "items": [{**body["items"][0], "quantity": 25}]}
        self.assertEqual(self.api.put(path, json=updated).json()["items"][0]["quantity"], 25)
        self.assertEqual(self.api.patch(path + "/status", json={"status": "completed"}).status_code, 409)
        self.assertEqual(self.api.patch(path + "/status", json={"status": "processing"}).status_code, 200)
        self.assertEqual(self.api.patch(path + "/status", json={"status": "pending"}).status_code, 409)
        self.assertEqual(self.api.patch(path + "/status", json={"status": "completed"}).status_code, 409)
        shipment = {"order_id": order["id"], "courier": "DHL", "tracking_number": "TEST-001", "dispatch_date": body["order_date"], "expected_delivery_date": body["order_date"], "delivered_date": body["order_date"]}
        self.assertEqual(self.api.post("/shipments", json=shipment).status_code, 201)
        self.assertEqual(self.api.post("/shipments", json=shipment).status_code, 409)
        self.assertEqual(self.api.patch(path + "/status", json={"status": "completed"}).status_code, 200)
        self.assertEqual(self.api.delete(path).status_code, 409)

    def test_documents_versions_download_validation_and_archive(self):
        order, _body = self.order()
        fields = {"name": "Invoice", "category": "invoice", "order_id": str(order["id"])}
        uploaded = self.api.post("/documents", data=fields, files={"file": ("../invoice.txt", b"First version", "text/plain")})
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        document = uploaded.json()
        self.assertEqual(document["versions"][0]["original_name"], "invoice.txt")
        path = f"/documents/{document['id']}"
        second = self.api.post(path + "/versions", files={"file": ("invoice.txt", b"Second version", "text/plain")})
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual([item["version"] for item in second.json()["versions"]], [1, 2])
        self.assertEqual(self.api.get(path + "/download?version=1").content, b"First version")
        self.assertEqual(self.api.get(path + "/download").content, b"Second version")
        self.assertEqual(self.api.post(path + "/versions", files={"file": ("fake.pdf", b"not a PDF", "application/pdf")}).status_code, 422)
        self.assertEqual(self.api.post(path + "/versions", files={"file": ("empty.txt", b"", "text/plain")}).status_code, 422)
        self.assertEqual(self.api.post(path + "/versions", files={"file": ("bad.exe", b"bad", "application/octet-stream")}).status_code, 422)
        self.assertEqual(len(self.api.get("/documents").json()[0]["versions"]), 2)
        self.assertEqual(self.api.patch(path + "/archive?archived=true").status_code, 200)
        self.assertEqual(self.api.get("/documents").json(), [])
        self.assertEqual(self.api.post(path + "/versions", files={"file": ("invoice.txt", b"Third", "text/plain")}).status_code, 409)
        self.assertEqual(len(self.api.get("/documents?archived=true").json()), 1)
        self.assertEqual(self.api.patch(path + "/archive?archived=false").status_code, 200)

    def test_quality_detects_resolves_and_reopens_issues(self):
        order, body = self.order()
        duplicate = self.api.post("/orders", json=body).json()
        self.assertEqual(self.api.post("/quality/scan").status_code, 200)
        issues = self.api.get("/quality/issues").json()
        self.assertEqual(len([issue for issue in issues if issue["code"] == "possible_duplicate_order" and issue["status"] == "open"]), 2)
        self.api.delete(f"/orders/{duplicate['id']}")
        self.api.post("/quality/scan")
        self.assertTrue(all(issue["status"] == "resolved" for issue in self.api.get("/quality/issues").json()))
        self.api.post("/orders", json=body)
        self.api.post("/quality/scan")
        self.assertTrue(any(issue["status"] == "open" for issue in self.api.get("/quality/issues").json()))
        self.assertIsNotNone(self.api.get("/reports/summary").json()["last_scan"])

    def test_reports_and_audit(self):
        order, _body = self.order()
        report = self.api.get(f"/reports/orders/{order['id']}")
        self.assertEqual(report.status_code, 200)
        self.assertIn("&lt;Network switch&gt;", report.text)
        self.assertNotIn("<Network switch>", report.text)
        summary = self.api.get("/reports/summary").json()
        self.assertEqual(summary["orders"], 1)
        self.assertEqual(summary["directions"]["outgoing"], 1)
        self.assertIsNone(summary["on_time_percentage"])
        export = self.api.get("/reports/export/orders.csv")
        self.assertIn("outgoing", export.text)
        archive = self.api.get("/reports/powerbi.zip")
        self.assertEqual(archive.status_code, 200, archive.text[:300] if archive.status_code != 200 else "")
        with zipfile.ZipFile(io.BytesIO(archive.content)) as package:
            self.assertIn("orders.csv", package.namelist())
            self.assertIn("measures.dax", package.namelist())
        audit = self.api.get("/audit").json()
        self.assertTrue(any(row["entity_type"] == "orders" and row["actor_id"] == 1 for row in audit))
        self.assertNotIn("password_hash", self.api.get("/employees").text)

    def test_existing_database_migration(self):
        client, _product = self.catalog()
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE clients DROP COLUMN phone")
        initialize_database()
        response = self.api.get('/clients').json()
        self.assertEqual(response[0]['id'], client['id'])
        self.assertIsNone(response[0]['phone'])
        initialize_database()
        self.assertEqual(len(self.api.get('/clients').json()), 1)

    def test_contact_validation_and_legacy_quality_repair(self):
        bad = self.api.post('/clients', json={'name':'Invalid phone', 'email':'phone@example.com', 'phone':'abc'})
        self.assertEqual(bad.status_code, 422)
        client, _product = self.catalog()
        with SessionLocal() as session:
            stored = session.get(Client, client['id'])
            stored.phone = 'legacy-invalid'
            session.commit()
        self.api.post('/quality/scan')
        self.assertTrue(any(issue['code'] == 'invalid_client_phone' and issue['status'] == 'open' for issue in self.api.get('/quality/issues').json()))
        self.assertEqual(self.api.put(f"/clients/{client['id']}", json={'name':client['name'], 'email':client['email'], 'phone':'+971 50 123 4567'}).status_code, 200)
        self.api.post('/quality/scan')
        self.assertTrue(all(issue['status'] == 'resolved' for issue in self.api.get('/quality/issues').json()))

    def test_upload_limits_storage_fault_detection_and_csv_safety(self):
        response = self.api.post('/documents', data={'name':'Storage test', 'category':'other'}, files={'file':('test.txt',b'test content','text/plain')})
        self.assertEqual(response.status_code, 201, response.text)
        document_id = response.json()['id']
        too_large = self.api.post(f'/documents/{document_id}/versions', files={'file':('large.txt', b'x' * (10 * 1024 * 1024 + 1), 'text/plain')})
        self.assertEqual(too_large.status_code, 413)
        self.assertEqual(len(self.api.get('/documents').json()[0]['versions']), 1)
        with SessionLocal() as session:
            version = session.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document_id))
            (UPLOAD_DIR / version.storage_key).unlink()
        self.assertEqual(self.api.get(f'/documents/{document_id}/download').status_code, 404)
        self.api.post('/quality/scan')
        self.assertTrue(any(issue['code'] == 'missing_document_file' and issue['status'] == 'open' for issue in self.api.get('/quality/issues').json()))
        self.api.patch(f'/documents/{document_id}/archive?archived=true')
        self.api.post('/quality/scan')
        self.assertTrue(all(issue['status'] == 'resolved' for issue in self.api.get('/quality/issues').json()))
        self.api.post('/clients', json={'name':'=2+2', 'email':'csv@example.com'})
        self.assertIn("'=2+2", self.api.get('/reports/export/clients.csv').text)


if __name__ == "__main__":
    unittest.main()
