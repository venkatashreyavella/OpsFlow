# OpsFlow

OpsFlow combines the backend, React workspace, employee access, document management, data verification, audit history, and business reports for a simulated operations team.

## Public internet link

The public-sharing helper creates an HTTPS `trycloudflare.com` link that can be opened from computers on other networks. It serves this app from your computer. Keep the computer awake, connected to the internet, and running the sharing processes. Restarting the share can generate a different URL.

After setting up the administrator account locally and placing Cloudflare's official Windows client at `.local/tools/cloudflared.exe`, run the following from the project folder:

```powershell
.\scripts\start-public.ps1
```

The command prints the public URL. Existing OpsFlow accounts sign in normally. The public-serving process uses secure cookies and the same database and uploaded documents as the local workspace. Use this command to stop sharing:

```powershell
.\scripts\stop-public.ps1
```

The current URL is also stored in `.local/public-share.json`. Keep `.local/` out of source control. [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) are temporary links for development and demonstrations.

For independent cloud hosting, `render.yaml` prepares a Docker web service, managed PostgreSQL, and a persistent disk for documents. It also generates a private `OPSFLOW_SETUP_TOKEN` for creating the first administrator. Hosting-account connection, source-repository access, and review of the provider's charges are required before provisioning. Enter the generated setup token from the hosting dashboard on the first-run setup page. Standard `postgres://` and `postgresql://` provider connection strings are supported.

## Using the complete application

Open [OpsFlow](http://127.0.0.1:8000/). On the first visit, create the administrator account using your own email and a password of at least 12 characters. Existing business records remain in the database. The application creates new module tables and adds the optional client phone column when it starts.

The administrator can create employees under Employee access. Administrators manage access and review audit and system events. Operations employees maintain business records, upload documents, and run quality scans. Viewers can read records and download reports and documents. Deactivating an employee or resetting a password revokes their existing sessions. Every employee can change their own password from the top bar.

The workflow now covers the remaining phases together.

- The Operations dashboard shows incoming and outgoing orders, progress, delivery delays, monthly volume, client counts, and delivery performance.
- Documents supports order attachments and company documents, categories, immutable versions, downloads, archive, and restore. Accepted files are PDF, DOCX, PNG, JPEG, UTF-8 TXT, and CSV up to 10 MB. Files use generated storage keys with hashes and metadata. Archiving retains every version.
- Data quality scans contact information, product details, order items, possible duplicate orders, shipment dates, delivery/status inconsistencies, delayed shipments, and missing uploaded files. Correct a record and scan again to resolve its issue. A recurring issue is reopened.
- Audit and system health shows who changed business records and the field changes. Failed requests and access attempts are recorded separately. Passwords and uploaded file content are omitted from these logs.
- Dashboard exports include CSV datasets and a ZIP for Power BI with relationship instructions and DAX measures. Order tables also provide an HTML order report suitable for printing to PDF.

Orders progress from pending to processing to completed. Completing an order requires a recorded actual shipment delivery date. Earlier phases' orders retain their saved status; the quality scan identifies legacy inconsistencies for review.

Sessions use signed JWTs in HttpOnly cookies. Browser changes require a CSRF token supplied by the interface. The local signing key and uploaded files persist under `.local/`, which is ignored by Git. `OPSFLOW_DATA_DIR` selects a different storage directory. `OPSFLOW_JWT_SECRET` can provide a stable signing key of at least 32 characters. Set `OPSFLOW_COOKIE_SECURE=true` when serving through HTTPS.

Back up the database together with the entire storage directory. For Docker, this means both named volumes. An optional signing key set through the environment must also be retained so existing sessions remain valid.

## Docker deployment

With Docker Desktop running, use the following command from the project folder:

```powershell
docker compose up --build -d --wait
```

The complete application runs at [localhost port 18080](http://127.0.0.1:18080/). Set the `OPSFLOW_PORT` environment variable before running Compose to choose another port. Compose waits for PostgreSQL to become healthy before starting the app. The application runs as a non-root user, has its own health check, and persists uploaded files and the signing key in `opsflow_files`. PostgreSQL persists business data in `opsflow_data`. This database is separate from the default local SQLite database.

`docker compose down` stops the services and retains their volumes. The Compose credentials and loopback port bindings are for local development. An external hosting target and HTTPS configuration must be selected before public deployment.

## Tests and Power BI

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use a temporary SQLite database and storage directory. They cover authentication, cookie CSRF checks, session revocation, roles, employee administration, order validation and status rules, document versioning, downloads, archiving, quality resolution, reports, audit redaction, and migration of existing records.

Download the Power BI pack from the dashboard. [The Power BI guide](reports/POWER_BI.md) describes CSV loading, relationships, visual choices, and the included measures. A native `.pbix` file is created and saved in Power BI Desktop after importing these datasets. The built-in dashboard is ready in the browser.

All business API endpoints now require authentication. In Swagger, call `POST /auth/login`, copy the returned `access_token`, and use the Authorize button with the bearer token. The React interface handles cookie authentication and CSRF tokens automatically. `/health` and first-run authentication routes remain available without signing in.

## Run locally on Windows

From the project folder in PowerShell, with Python 3.10 or newer installed:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For PostgreSQL, start Docker Desktop and run these commands in the same PowerShell window you'll use to start the API. Compose starts an isolated PostgreSQL 17 database on port `55432` with a persistent volume and local development credentials.

```powershell
docker compose up -d --wait postgres
$env:DATABASE_URL = "postgresql+psycopg://opsflow:opsflow_dev@127.0.0.1:55432/opsflow"
```

For a quick SQLite demo, skip the Docker commands and leave `DATABASE_URL` unset. SQLite saves records to `opsflow.db` in the project folder. Each database has its own records.

Start the API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open [Swagger UI](http://127.0.0.1:8000/docs) to send requests. [Database health](http://127.0.0.1:8000/health) checks the active database connection. Use `Ctrl+C` to stop the API and `docker compose down` to stop PostgreSQL when you're done. The volume persists across restarts.

## Phase 2 interface

Install Node.js 22 or newer, then install and build the interface from the project folder:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run build
Set-Location ..
```

Start or restart the API using the command above, then open [OpsFlow](http://127.0.0.1:8000/). FastAPI serves the built interface and its API on the same port. Rebuild the frontend and restart the API after changing the interface for this mode.

1. Open **Clients** and add a simulated company and its contact email.
2. Open **Products** and add a product with a unique SKU.
3. In **Orders**, create an incoming or outgoing order. Select a client, add one or more products, and enter their quantities. Use the pencil button to edit an order, or its status menu to change its status.
4. Select **Add shipment** on an order, or use **New shipment** in the Shipments page. Record the courier, tracking number, dispatch date, and expected delivery date.
5. Edit the shipment and enter an actual delivery date when it arrives. Scheduled, in-transit, delayed, and delivered labels are calculated from the shipment dates using Dubai time. Order status is managed separately.
6. Search the tables, filter orders by direction and status, and filter shipments by status. Use the Refresh button to fetch updates made in another tab.

Each order supports one shipment in this phase. Remove its shipment before deleting the order. A shipment's order cannot be reassigned. Dispatch must be on or after the order date, and expected and actual delivery dates must be on or after dispatch. Actual delivery cannot be in the future.

For frontend development, keep the API running on port `8000` and start Vite in a second terminal:

```powershell
Set-Location frontend
npm.cmd run dev
```

Open [the development interface](http://127.0.0.1:5173/). Vite forwards `/api` requests to FastAPI, and refreshes the interface as you edit. `frontend/src/App.jsx` contains the pages, `forms.jsx` contains the dialogs, and `api.js` handles requests and paginated loading. Search and table pagination operate on the fetched workspace records.

Existing Phase 1 records are retained. Starting the updated API creates the new `shipments` table automatically. The new API endpoints include `PUT /orders/{order_id}` and create, list, read, replace, and delete operations under `/shipments`.

## Try your first order

1. In Swagger UI, open `POST /clients`, select **Try it out**, and submit `{"name":"Falcon Networks","email":"operations@falcon.example.com"}`. Copy the returned `id`.
2. Submit `{"sku":"NET-001","name":"Network switch"}` to `POST /products`. Copy the returned product `id`.
3. Submit the following to `POST /orders`, replacing the IDs with the values from steps 1 and 2. The response includes a generated order `id` and the initial `pending` status.

   ```json
   {
     "client_id": 1,
     "direction": "outgoing",
     "order_date": "2026-11-06",
     "items": [{"product_id": 1, "quantity": 20}]
   }
   ```

4. Use `PATCH /orders/{order_id}/status` with `{"status":"processing"}` to advance the order. Use `GET /orders` to filter by `direction` or `status`, or `GET /orders/{order_id}` to fetch the order directly. `DELETE /orders/{order_id}` removes the order and its line items.
5. Try a quantity of `0` to see a `422` validation error. A missing client or product returns `404`, and a duplicate client email or product SKU returns `409`.

## How the pieces fit together

- `app/main.py` defines the FastAPI endpoints. Each request gets its own SQLAlchemy session.
- `app/schemas.py` uses Pydantic to check input and define the JSON responses. An order needs at least one item, and each product can appear once per order.
- `app/models.py` maps Python classes to database tables. Foreign keys link records, a unique constraint guards each client email and product SKU, and a check constraint enforces positive quantities.
- `app/database.py` selects and connects to the database. On startup, the API creates missing tables. Schema changes will need migrations as the project grows.

```mermaid
erDiagram
    CLIENTS ||--o{ ORDERS : places
    ORDERS ||--|{ ORDER_ITEMS : contains
    PRODUCTS ||--o{ ORDER_ITEMS : appears_in
    ORDERS ||--o| SHIPMENTS : ships_as
```

An order and all its line items are committed in one transaction. The `orders` table stores the client, direction, date, and status. The `order_items` table stores each product and its quantity for that order. `pending`, `processing`, and `completed` are available for manual status updates in this phase.

When running PostgreSQL through Compose, open a SQL prompt with `docker compose exec postgres psql -U opsflow -d opsflow`. After creating an order, try joining the four tables to see its client and products:

```sql
SELECT o.id AS order_id, c.name AS client, p.sku, i.quantity
FROM orders AS o
JOIN clients AS c ON c.id = o.client_id
JOIN order_items AS i ON i.order_id = o.id
JOIN products AS p ON p.id = i.product_id
ORDER BY o.id, p.sku;
```
