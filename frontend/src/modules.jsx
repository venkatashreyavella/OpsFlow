import { useEffect, useState } from "react";
import {
  Archive,
  BarChart3,
  Download,
  FileText,
  LoaderCircle,
  Plus,
  RefreshCw,
  ShieldCheck,
  Upload,
  Users,
} from "lucide-react";
import {
  downloadFile,
  formatDate,
  orderNumber,
  readAll,
  request,
} from "./api.js";
import { useAuth } from "./auth.jsx";
import { Field, Modal } from "./forms.jsx";

export function timestamp(value) {
  return value
    ? new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Dubai",
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value * 1000))
    : "Not scanned yet";
}

function DialogForm({ title, children, onClose, onSubmit, busy, error }) {
  return (
    <Modal
      title={title}
      subtitle="Keep your operations workspace up to date."
      onClose={onClose}
      busy={busy}
    >
      <form onSubmit={onSubmit}>
        <fieldset disabled={busy}>{children}</fieldset>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        <div className="form-actions">
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={onClose}
          >
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Bars({ rows, labelKey, title }) {
  const maximum = Math.max(1, ...rows.map((row) => row.orders));
  return (
    <section className="chart-card">
      <h2>{title}</h2>
      {rows.length ? (
        rows.map((row) => (
          <div className="bar-row" key={row[labelKey]}>
            <span>{row[labelKey]}</span>
            <div className="bar-track">
              <div style={{ width: `${(row.orders / maximum) * 100}%` }} />
            </div>
            <strong>{row.orders}</strong>
          </div>
        ))
      ) : (
        <p className="module-muted">Create orders to see this report.</p>
      )}
    </section>
  );
}

function Dashboard({ summary, onDownload }) {
  return (
    <>
      <div className="module-actions">
        <p className="module-muted">
          Reports use all records in your operations database.
        </p>
        <button
          className="button secondary"
          onClick={() =>
            onDownload("/reports/powerbi.zip", "opsflow-powerbi.zip")
          }
        >
          <Download size={16} />
          Power BI data pack
        </button>
      </div>
      <div className="metrics">
        {[
          ["Total orders", summary.orders],
          ["Incoming", summary.directions.incoming || 0],
          ["Outgoing", summary.directions.outgoing || 0],
          ["Completed", summary.statuses.completed || 0],
          ["Pending", summary.statuses.pending || 0],
          ["Processing", summary.statuses.processing || 0],
          ["Delayed shipments", summary.shipment_statuses.delayed || 0],
          [
            "On-time deliveries",
            summary.on_time_percentage === null
              ? "—"
              : `${summary.on_time_percentage}%`,
          ],
        ].map(([label, value]) => (
          <div className="metric" key={label}>
            <div className="metric-top">
              {label}
              <BarChart3 size={17} />
            </div>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <div className="chart-grid">
        <Bars
          rows={summary.monthly}
          labelKey="month"
          title="Monthly order volume"
        />
        <Bars
          rows={summary.by_client}
          labelKey="client"
          title="Orders by client"
        />
      </div>
      <section className="chart-card">
        <h2>Data quality</h2>
        <p>{summary.open_issues} open issues from the last scan.</p>
        <p className="module-muted">
          Last scan {timestamp(summary.last_scan)}. Run a scan in Data quality
          to refresh the results.
        </p>
        <a className="text-button" href="#quality">
          Review data quality →
        </a>
      </section>
      <section className="chart-card">
        <h2>Download reports</h2>
        <div className="module-actions">
          {[
            "orders",
            "order_items",
            "shipments",
            "clients",
            "products",
            "data_issues",
          ].map((dataset) => (
            <button
              key={dataset}
              className="button secondary"
              onClick={() =>
                onDownload(
                  `/reports/export/${dataset}.csv`,
                  `opsflow-${dataset}.csv`,
                )
              }
            >
              <Download size={14} />
              {dataset.replaceAll("_", " ")}
            </button>
          ))}
        </div>
      </section>
    </>
  );
}

function DocumentCard({
  document,
  data,
  canWrite,
  onUpload,
  onArchive,
  onDownload,
}) {
  const [version, setVersion] = useState(
    String(document.versions.at(-1)?.version || 1),
  );
  const selected =
    document.versions.find((item) => String(item.version) === version) ||
    document.versions.at(-1);
  return (
    <article className="document-card">
      <div className="document-heading">
        <span className="empty-icon">
          <FileText size={22} />
        </span>
        <div>
          <h3>{document.name}</h3>
          <p>
            {document.category.replaceAll("_", " ")} ·{" "}
            {document.order_id
              ? orderNumber(document.order_id)
              : "Company document"}
          </p>
        </div>
      </div>
      <p className="module-muted">
        {selected?.original_name} ·{" "}
        {Math.ceil((selected?.size_bytes || 0) / 1024)} KB
      </p>
      <label className="field">
        <span>Document version</span>
        <select
          value={selected?.version || ""}
          onChange={(event) => setVersion(event.target.value)}
        >
          {document.versions.map((item) => (
            <option key={item.id} value={item.version}>
              Version {item.version} · {timestamp(item.created_at)}
            </option>
          ))}
        </select>
      </label>
      <div className="module-actions">
        <button
          className="button secondary"
          onClick={() =>
            onDownload(
              `/documents/${document.id}/download?version=${selected.version}`,
              selected.original_name,
            )
          }
        >
          <Download size={14} />
          Download
        </button>
        {canWrite && !document.archived && (
          <button
            className="button secondary"
            onClick={() => onUpload(document)}
          >
            <Upload size={14} />
            New version
          </button>
        )}
        {canWrite && (
          <button className="text-button" onClick={() => onArchive(document)}>
            <Archive size={14} />
            {document.archived ? "Restore" : "Archive"}
          </button>
        )}
      </div>
    </article>
  );
}

export default function WorkspaceModules({ page, data, onSaved, onFix }) {
  const { employee } = useAuth();
  const canWrite = employee.role !== "viewer";
  const [records, setRecords] = useState([]);
  const [events, setEvents] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [archived, setArchived] = useState(false);
  const [showResolved, setShowResolved] = useState(false);
  const [dialog, setDialog] = useState(null);
  const [formError, setFormError] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    async function load() {
      try {
        if (page === "dashboard") {
          const result = await request("/reports/summary");
          if (active) setSummary(result);
        } else {
          const endpoints = {
            documents: `/documents?archived=${archived}`,
            quality: "/quality/issues",
            employees: "/employees",
            audit: "/audit",
          };
          const result = await readAll(endpoints[page]);
          if (active) setRecords(result);
          if (page === "audit") {
            const logs = await readAll("/system/events");
            if (active) setEvents(logs);
          }
        }
      } catch (err) {
        if (active) setError(err.message);
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [page, archived, reload]);

  function openDialog(value) {
    setFormError("");
    setDialog(value);
  }
  async function download(path, filename) {
    try {
      await downloadFile(path, filename);
    } catch (err) {
      setError(err.message);
    }
  }
  async function runScan() {
    setBusy(true);
    setError("");
    try {
      const result = await request("/quality/scan", { method: "POST" });
      setReload((value) => value + 1);
      onSaved(`Scan complete. ${result.open} open issues.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  async function archive(document) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await request(
        `/documents/${document.id}/archive?archived=${!document.archived}`,
        { method: "PATCH" },
      );
      setReload((value) => value + 1);
      onSaved(
        document.archived
          ? "Document restored."
          : "Document archived. Versions are retained.",
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setFormError("");
    const form = new FormData(event.currentTarget);
    try {
      if (page === "documents") {
        if (!form.get("order_id")) form.delete("order_id");
        await request(
          dialog.record
            ? `/documents/${dialog.record.id}/versions`
            : "/documents",
          { method: "POST", body: form },
        );
      } else {
        const payload = Object.fromEntries(form);
        if (dialog.record) {
          payload.active = payload.active === "true";
          if (!payload.password) delete payload.password;
        }
        await request(
          dialog.record ? `/employees/${dialog.record.id}` : "/employees",
          {
            method: dialog.record ? "PUT" : "POST",
            body: JSON.stringify(payload),
          },
        );
      }
      setDialog(null);
      setReload((value) => value + 1);
      onSaved(page === "documents" ? "Document saved." : "Employee saved.");
    } catch (err) {
      setFormError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const filtered = records.filter((record) => {
    if (page === "quality" && (record.status === "resolved") !== showResolved)
      return false;
    return JSON.stringify(record)
      .toLowerCase()
      .includes(search.toLowerCase().trim());
  });

  return (
    <div className="module-page">
      <div className="module-actions">
        {page !== "dashboard" && (
          <label className="search">
            <span className="sr-only">Search records</span>
            <input
              aria-label="Search records"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search records…"
            />
          </label>
        )}
        {page === "documents" && (
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={archived}
              onChange={(event) => setArchived(event.target.checked)}
            />
            Archived documents
          </label>
        )}
        {page === "quality" && (
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={showResolved}
              onChange={(event) => setShowResolved(event.target.checked)}
            />
            Resolved issues
          </label>
        )}
        <button
          className="button secondary"
          disabled={loading || busy}
          onClick={() => setReload((value) => value + 1)}
        >
          <RefreshCw size={14} />
          Refresh
        </button>
        {canWrite && page === "quality" && (
          <button
            className="button primary"
            disabled={busy || loading}
            onClick={runScan}
          >
            <ShieldCheck size={16} />
            {busy ? "Scanning…" : "Run data scan"}
          </button>
        )}
        {canWrite && page === "documents" && (
          <button
            className="button primary"
            disabled={busy}
            onClick={() => openDialog({})}
          >
            <Upload size={16} />
            Upload document
          </button>
        )}
        {page === "employees" && (
          <button className="button primary" onClick={() => openDialog({})}>
            <Plus size={16} />
            Add employee
          </button>
        )}
      </div>
      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
      {loading ? (
        <div className="empty-state">
          <LoaderCircle className="spin" />
          <p>Loading records…</p>
        </div>
      ) : (
        <>
          {page === "dashboard" && summary && (
            <Dashboard summary={summary} onDownload={download} />
          )}
          {page === "documents" && (
            <div className="document-grid">
              {filtered.map((document) => (
                <DocumentCard
                  key={`${document.id}-${document.versions.length}`}
                  document={document}
                  data={data}
                  canWrite={canWrite && !busy}
                  onUpload={(record) => openDialog({ record })}
                  onArchive={archive}
                  onDownload={download}
                />
              ))}
            </div>
          )}
          {page === "quality" && (
            <>
              <p className="module-muted">
                {filtered.length} {showResolved ? "resolved" : "open"} issues.
                Correct the underlying record, then run another scan. Duplicate
                matches are flagged for review.
              </p>
              <div className="issue-list">
                {filtered.map((issue) => (
                  <article className="issue-card" key={issue.id}>
                    <span
                      className={`badge ${issue.severity === "error" ? "delayed" : "pending"}`}
                    >
                      {issue.severity}
                    </span>
                    <div>
                      <h3>{issue.code.replaceAll("_", " ")}</h3>
                      <p>{issue.message}</p>
                      <small>
                        {issue.entity_type} #{issue.entity_id} · Last seen{" "}
                        {timestamp(issue.last_seen)}
                      </small>
                    </div>
                    <button
                      className="button secondary"
                      onClick={() => onFix(issue)}
                    >
                      {canWrite ? "Review record" : "View records"}
                    </button>
                  </article>
                ))}
              </div>
            </>
          )}
          {page === "employees" && (
            <div className="records-panel table-scroll">
              <table aria-label="Employees">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((record) => (
                    <tr key={record.id}>
                      <td>{record.name}</td>
                      <td>{record.email}</td>
                      <td>{record.role}</td>
                      <td>{record.active ? "Active" : "Inactive"}</td>
                      <td>
                        <button
                          className="text-button"
                          onClick={() => openDialog({ record })}
                        >
                          Edit access
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {page === "audit" && (
            <>
              <section className="records-panel table-scroll">
                <table aria-label="Audit history">
                  <thead>
                    <tr>
                      <th>Time (Dubai)</th>
                      <th>Employee</th>
                      <th>Action</th>
                      <th>Record</th>
                      <th>Changes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((record) => (
                      <tr key={record.id}>
                        <td>{timestamp(record.created_at)}</td>
                        <td>
                          {record.actor_id
                            ? `Employee #${record.actor_id}`
                            : "Setup / system"}
                        </td>
                        <td>{record.action}</td>
                        <td>
                          {record.entity_type} #{record.entity_id}
                        </td>
                        <td>
                          <details>
                            <summary>View changes</summary>
                            <pre>{JSON.stringify(record.changes, null, 2)}</pre>
                          </details>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
              <section className="chart-card">
                <h2>API and security events</h2>
                <p className="module-muted">
                  Failed requests and access attempts are recorded without
                  request bodies or passwords.
                </p>
                <div className="table-scroll">
                  <table aria-label="System events">
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Request</th>
                        <th>Status</th>
                        <th>Message</th>
                      </tr>
                    </thead>
                    <tbody>
                      {events.map((event) => (
                        <tr key={event.id}>
                          <td>{timestamp(event.created_at)}</td>
                          <td>
                            {event.method} {event.path}
                          </td>
                          <td>{event.status_code}</td>
                          <td>{event.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
          {page !== "dashboard" && !filtered.length && (
            <div className="empty-state">
              <FileText size={28} />
              <h3>No matching records</h3>
              <p>
                {page === "quality"
                  ? "Run a scan to check your orders, shipments, clients, products, and document storage."
                  : "Add a record or adjust your search."}
              </p>
            </div>
          )}
        </>
      )}
      {dialog && (
        <DialogForm
          title={
            page === "documents"
              ? dialog.record
                ? "Upload a new version"
                : "Upload document"
              : dialog.record
                ? "Edit employee"
                : "Add employee"
          }
          onClose={() => setDialog(null)}
          onSubmit={save}
          busy={busy}
          error={formError}
        >
          {page === "documents" ? (
            <>
              {!dialog.record && (
                <>
                  <Field label="Document name">
                    <input name="name" required maxLength={200} />
                  </Field>
                  <Field label="Category">
                    <select name="category">
                      <option value="invoice">Invoice</option>
                      <option value="purchase_order">Purchase order</option>
                      <option value="delivery">Delivery document</option>
                      <option value="other">Other</option>
                    </select>
                  </Field>
                  <Field label="Order (optional)">
                    <select name="order_id">
                      <option value="">Company document</option>
                      {data.orders.map((order) => (
                        <option key={order.id} value={order.id}>
                          {orderNumber(order.id)}
                        </option>
                      ))}
                    </select>
                  </Field>
                </>
              )}
              <Field label="File">
                <input
                  name="file"
                  type="file"
                  required
                  accept=".pdf,.docx,.png,.jpg,.jpeg,.txt,.csv"
                />
              </Field>
              <p className="field-hint">
                Up to 10 MB. PDF, DOCX, PNG, JPEG, UTF-8 TXT, or CSV.
              </p>
            </>
          ) : (
            <>
              <Field label="Name">
                <input
                  name="name"
                  required
                  maxLength={200}
                  defaultValue={dialog.record?.name || ""}
                />
              </Field>
              <Field label="Email">
                <input
                  name="email"
                  type="email"
                  required
                  defaultValue={dialog.record?.email || ""}
                />
              </Field>
              <Field label="Role">
                <select
                  name="role"
                  defaultValue={dialog.record?.role || "operator"}
                >
                  <option value="admin">Administrator</option>
                  <option value="operator">Operations employee</option>
                  <option value="viewer">Read-only viewer</option>
                </select>
              </Field>
              {dialog.record && (
                <Field label="Access">
                  <select
                    name="active"
                    defaultValue={String(dialog.record.active)}
                  >
                    <option value="true">Active</option>
                    <option value="false">Inactive</option>
                  </select>
                </Field>
              )}
              <Field
                label={
                  dialog.record
                    ? "New password (leave blank to keep current)"
                    : "Initial password"
                }
              >
                <input
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  required={!dialog.record}
                  minLength={12}
                  maxLength={128}
                />
              </Field>
            </>
          )}
        </DialogForm>
      )}
    </div>
  );
}
