import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDownLeft,
  ArrowRight,
  ArrowUpRight,
  Box,
  Check,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clock3,
  Code2,
  Layers3,
  LoaderCircle,
  Package,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Truck,
  Users,
  X,
  BarChart3,
  FileText,
  ShieldCheck,
  History,
  Download,
} from "lucide-react";
import {
  downloadFile,
  formatDate,
  orderNumber,
  readAll,
  request,
  today,
} from "./api.js";
import RecordDialog from "./forms.jsx";
import { PasswordDialog, useAuth } from "./auth.jsx";
import WorkspaceModules from "./modules.jsx";

const pages = {
  dashboard: {
    title: "Operations dashboard",
    description:
      "Order volume, delivery performance, and data quality in one place.",
    icon: BarChart3,
    external: true,
  },
  orders: {
    title: "Order management",
    description: "From first request to completion. Keep every order moving.",
    icon: Layers3,
    singular: "order",
  },
  shipments: {
    title: "Shipment tracking",
    description: "Follow every dispatch and stay ahead of delivery delays.",
    icon: Truck,
    singular: "shipment",
  },
  clients: {
    title: "Your clients",
    description: "The people and companies behind your operations.",
    icon: Users,
    singular: "client",
  },
  products: {
    title: "Product catalog",
    description: "A reliable product reference for every order you create.",
    icon: Package,
    singular: "product",
  },
  documents: {
    title: "Document library",
    description: "Order documents with downloadable version history.",
    icon: FileText,
    external: true,
  },
  quality: {
    title: "Data quality",
    description:
      "Find incomplete records, duplicate orders, and workflow inconsistencies.",
    icon: ShieldCheck,
    external: true,
  },
  employees: {
    title: "Employee access",
    description: "Manage employee accounts and workspace permissions.",
    icon: Users,
    external: true,
    adminOnly: true,
  },
  audit: {
    title: "Audit and system health",
    description:
      "Review business changes and investigate unsuccessful requests.",
    icon: History,
    external: true,
    adminOnly: true,
  },
};
const labels = {
  pending: "Pending",
  processing: "Processing",
  completed: "Completed",
  in_transit: "In transit",
  delayed: "Delayed",
  scheduled: "Scheduled",
  delivered: "Delivered",
};
const emptyData = { orders: [], shipments: [], clients: [], products: [] };

function currentPage() {
  const name = window.location.hash.slice(1);
  return pages[name] ? name : "dashboard";
}

function Badge({ value }) {
  return (
    <span className={`badge ${value}`}>
      <span className="status-dot" />
      {labels[value] || value}
    </span>
  );
}

function Metric({ label, value, caption, icon: Icon, tone = "purple" }) {
  return (
    <div className="metric">
      <div className="metric-top">
        <span>{label}</span>
        <span className={`metric-icon ${tone}`}>
          <Icon size={18} />
        </span>
      </div>
      <strong>{value}</strong>
      <span className="metric-caption">{caption}</span>
    </div>
  );
}

function RowActions({ label, onEdit, onDelete, disabled }) {
  const { employee } = useAuth();
  if (employee.role === "viewer") return null;
  return (
    <div className="row-actions">
      <button
        className="icon-button"
        title={`Edit ${label}`}
        aria-label={`Edit ${label}`}
        onClick={onEdit}
        disabled={disabled}
      >
        <Pencil size={16} />
      </button>
      <button
        className="icon-button danger"
        title={`Delete ${label}`}
        aria-label={`Delete ${label}`}
        onClick={onDelete}
        disabled={disabled}
      >
        <Trash2 size={16} />
      </button>
    </div>
  );
}

export default function App() {
  const { employee, logout } = useAuth();
  const canWrite = employee.role !== "viewer";
  const [passwordDialog, setPasswordDialog] = useState(false);
  const [page, setPage] = useState(currentPage);
  const [data, setData] = useState(emptyData);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [modal, setModal] = useState(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [direction, setDirection] = useState("all");
  const [pageIndex, setPageIndex] = useState(0);
  const [updating, setUpdating] = useState(null);
  const requestVersion = useRef(0);

  const refresh = useCallback(async () => {
    const version = ++requestVersion.current;
    setLoading(true);
    setError("");
    try {
      const [orders, shipments, clients, products] = await Promise.all([
        readAll("/orders"),
        readAll("/shipments"),
        readAll("/clients"),
        readAll("/products"),
      ]);
      if (version === requestVersion.current) {
        setData({ orders, shipments, clients, products });
        setLoaded(true);
      }
    } catch (err) {
      if (version === requestVersion.current) setError(err.message);
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    return () => {
      requestVersion.current += 1;
    };
  }, [refresh]);

  useEffect(() => {
    function handleHash() {
      setPage(currentPage());
      setSearch("");
      setStatus("all");
      setDirection("all");
      setPageIndex(0);
    }
    window.addEventListener("hashchange", handleHash);
    return () => window.removeEventListener("hashchange", handleHash);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 6000);
    return () => clearTimeout(timer);
  }, [toast]);

  function saved(message) {
    setModal(null);
    setToast(message);
    refresh();
  }

  async function changeStatus(order, nextStatus) {
    setUpdating(order.id);
    setError("");
    try {
      const updated = await request(`/orders/${order.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
      setData((current) => ({
        ...current,
        orders: current.orders.map((item) =>
          item.id === updated.id ? updated : item,
        ),
      }));
      setToast(`${orderNumber(order.id)} status updated.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setUpdating(null);
    }
  }

  const busy = loading || updating !== null || !loaded;
  const config = pages[page];
  const PageIcon = config.icon;
  const clientNames = new Map(
    data.clients.map((client) => [client.id, client.name]),
  );
  const productNames = new Map(
    data.products.map((product) => [product.id, product.name]),
  );
  const orderMap = new Map(data.orders.map((order) => [order.id, order]));
  const shipmentOrders = new Set(
    data.shipments.map((shipment) => shipment.order_id),
  );
  const hasOrderPrerequisites =
    data.clients.length > 0 && data.products.length > 0;
  const hasShipmentPrerequisites = data.orders.some(
    (order) => !shipmentOrders.has(order.id),
  );
  const canCreate =
    canWrite &&
    !busy &&
    (page !== "orders" || hasOrderPrerequisites) &&
    (page !== "shipments" || hasShipmentPrerequisites);
  const query = search.trim().toLowerCase();

  const filtered = (data[page] || []).filter((record) => {
    if (page === "orders") {
      const matchesFilters =
        (status === "all" || record.status === status) &&
        (direction === "all" || record.direction === direction);
      const text = [
        orderNumber(record.id),
        clientNames.get(record.client_id),
        ...record.items.map((item) => productNames.get(item.product_id)),
      ]
        .join(" ")
        .toLowerCase();
      return matchesFilters && text.includes(query);
    }
    if (page === "shipments") {
      const order = orderMap.get(record.order_id);
      const text = [
        record.tracking_number,
        record.courier,
        orderNumber(record.order_id),
        clientNames.get(order?.client_id),
      ]
        .join(" ")
        .toLowerCase();
      return (
        (status === "all" || record.status === status) && text.includes(query)
      );
    }
    return [record.name, record.email, record.sku]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
  const lastPage = Math.max(0, Math.ceil(filtered.length / 10) - 1);
  const safePage = Math.min(pageIndex, lastPage);
  const visible = filtered.slice(safePage * 10, safePage * 10 + 10);
  const orderStatuses = ["all", "pending", "processing", "completed"];
  const shipmentStatuses = [
    "all",
    "scheduled",
    "in_transit",
    "delayed",
    "delivered",
  ];
  const statuses = page === "orders" ? orderStatuses : shipmentStatuses;
  const value = (number) => (loaded ? number : "—");
  let metrics;
  if (page === "orders") {
    metrics = [
      {
        label: "Total orders",
        value: value(data.orders.length),
        caption: "Across your workspace",
        icon: Layers3,
      },
      {
        label: "Pending",
        value: value(
          data.orders.filter((order) => order.status === "pending").length,
        ),
        caption: "Ready for the next step",
        icon: Clock3,
        tone: "amber",
      },
      {
        label: "Processing",
        value: value(
          data.orders.filter((order) => order.status === "processing").length,
        ),
        caption: "Currently in progress",
        icon: RefreshCw,
        tone: "blue",
      },
      {
        label: "Completed",
        value: value(
          data.orders.filter((order) => order.status === "completed").length,
        ),
        caption: "Orders brought to a close",
        icon: CheckCheck,
        tone: "green",
      },
    ];
  } else if (page === "shipments") {
    metrics = [
      {
        label: "Total shipments",
        value: value(data.shipments.length),
        caption: "Linked to your orders",
        icon: Truck,
      },
      {
        label: "In transit",
        value: value(
          data.shipments.filter((shipment) => shipment.status === "in_transit")
            .length,
        ),
        caption: "On the way to delivery",
        icon: ArrowUpRight,
        tone: "blue",
      },
      {
        label: "Delayed",
        value: value(
          data.shipments.filter((shipment) => shipment.status === "delayed")
            .length,
        ),
        caption: "Past expected delivery",
        icon: CircleAlert,
        tone: "amber",
      },
      {
        label: "Delivered",
        value: value(
          data.shipments.filter((shipment) => shipment.status === "delivered")
            .length,
        ),
        caption: "Delivery date recorded",
        icon: CheckCheck,
        tone: "green",
      },
    ];
  }

  function openEdit(record) {
    setModal({ kind: page, record });
  }
  function openDelete(record) {
    setModal({ kind: page, record, action: "delete" });
  }

  function fixIssue(issue) {
    window.location.hash = issue.entity_type;
    const record = data[issue.entity_type]?.find(
      (item) => item.id === issue.entity_id,
    );
    if (record && canWrite) setModal({ kind: issue.entity_type, record });
  }

  async function downloadOrder(record) {
    try {
      await downloadFile(
        `/reports/orders/${record.id}`,
        `opsflow-order-${record.id}.html`,
      );
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="#orders" className="brand" aria-label="OpsFlow home">
          <span className="brand-icon">
            <Layers3 size={23} strokeWidth={2.3} />
          </span>
          opsflow<span className="brand-dot">.</span>
        </a>
        <div className="workspace">
          <span className="workspace-avatar">OF</span>
          <div>
            <strong>Operations</strong>
            <small>Local workspace</small>
          </div>
        </div>
        <p className="nav-caption">WORKSPACE</p>
        <nav aria-label="Main navigation">
          {Object.entries(pages)
            .filter(([, item]) => !item.adminOnly || employee.role === "admin")
            .map(([key, item]) => {
              const Icon = item.icon;
              return (
                <a
                  key={key}
                  href={`#${key}`}
                  aria-label={key[0].toUpperCase() + key.slice(1)}
                  className={`nav-item ${page === key ? "active" : ""}`}
                  aria-current={page === key ? "page" : undefined}
                >
                  <Icon size={19} />
                  <span>{key[0].toUpperCase() + key.slice(1)}</span>
                  {loaded && data[key] && (
                    <span className="nav-count">{data[key].length}</span>
                  )}
                </a>
              );
            })}
        </nav>
        <div className="sidebar-note">
          <Box size={22} />
          <strong>A connected workflow</strong>
          <p>Clients and products become orders. Orders become shipments.</p>
        </div>
        <a
          className="api-link"
          href={import.meta.env.DEV ? "http://127.0.0.1:8000/docs" : "/docs"}
          target="_blank"
          rel="noreferrer"
        >
          <Code2 size={17} />
          API documentation
          <ArrowUpRight size={15} />
        </a>
        <div className="sidebar-footer">
          <span className="local-dot" />
          OpsFlow · Local development
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace
            <ChevronRight size={14} />
            <strong>{page[0].toUpperCase() + page.slice(1)}</strong>
          </div>
          <div className="user-tools">
            <span className="topbar-date">
              {employee.name} · {employee.role}
            </span>
            <button
              className="text-button"
              onClick={() => setPasswordDialog(true)}
            >
              Password
            </button>
            <button
              className="text-button"
              onClick={() => logout().catch((err) => setError(err.message))}
            >
              Sign out
            </button>
          </div>
        </header>
        <main id="main-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <PageIcon size={15} />
                OPERATIONS WORKSPACE
              </div>
              <h1>{config.title}</h1>
              <p>{config.description}</p>
            </div>
            {!config.external && (
              <button
                className="button primary"
                disabled={!canCreate}
                onClick={() => setModal({ kind: page })}
              >
                <Plus size={18} />
                {page === "clients" || page === "products" ? "Add" : "New"}{" "}
                {config.singular}
              </button>
            )}
          </div>
          {error && (
            <div className="error-banner" role="alert">
              <CircleAlert size={19} />
              <span>{error}</span>
              <button
                className="text-button"
                onClick={refresh}
                disabled={loading}
              >
                Retry
              </button>
            </div>
          )}
          {config.external ? (
            <WorkspaceModules
              key={page}
              page={page}
              data={data}
              onSaved={saved}
              onFix={fixIssue}
            />
          ) : (
            <>
              {metrics && (
                <section className="metrics" aria-label={`${page} summary`}>
                  {metrics.map((metric) => (
                    <Metric key={metric.label} {...metric} />
                  ))}
                </section>
              )}
              {loaded && page === "orders" && !hasOrderPrerequisites && (
                <div className="setup-banner">
                  <span className="setup-icon">
                    <Layers3 size={22} />
                  </span>
                  <div>
                    <strong>Build your first order</strong>
                    <p>
                      Add a client and a product, then bring them together in an
                      order.
                    </p>
                  </div>
                  <a
                    href={data.clients.length ? "#products" : "#clients"}
                    className="button secondary"
                  >
                    {data.clients.length ? "Add a product" : "Add a client"}
                    <ArrowRight size={16} />
                  </a>
                </div>
              )}
              {loaded && page === "shipments" && !hasShipmentPrerequisites && (
                <div className="setup-banner">
                  <span className="setup-icon">
                    <Truck size={22} />
                  </span>
                  <div>
                    <strong>
                      {data.orders.length
                        ? "Every order has a shipment"
                        : "Start with an order"}
                    </strong>
                    <p>
                      {data.orders.length
                        ? "Update an existing shipment below, or create another order."
                        : "Create an order before recording its shipment details."}
                    </p>
                  </div>
                  <a href="#orders" className="button secondary">
                    Go to orders
                    <ArrowRight size={16} />
                  </a>
                </div>
              )}
              <section
                className="records-panel"
                aria-labelledby="records-title"
                aria-busy={loading}
              >
                <div className="panel-heading">
                  <div className="panel-title">
                    <h2 id="records-title">
                      {page === "products" ? "All products" : `All ${page}`}
                    </h2>
                    <span className="count-pill">
                      {loaded ? data[page].length : "—"}
                    </span>
                  </div>
                  <button
                    className="button subtle small"
                    onClick={refresh}
                    disabled={busy}
                  >
                    <RefreshCw size={15} className={loading ? "spin" : ""} />
                    Refresh
                  </button>
                </div>
                <div className="toolbar">
                  <label className="search">
                    <Search size={17} />
                    <span className="sr-only">Search {page}</span>
                    <input
                      placeholder={`Search ${page}…`}
                      value={search}
                      onChange={(event) => {
                        setSearch(event.target.value);
                        setPageIndex(0);
                      }}
                    />
                    {search && (
                      <button
                        className="icon-button"
                        aria-label="Clear search"
                        onClick={() => {
                          setSearch("");
                          setPageIndex(0);
                        }}
                      >
                        <X size={15} />
                      </button>
                    )}
                  </label>
                  {page === "orders" && (
                    <label className="direction-filter">
                      <span className="sr-only">Filter by direction</span>
                      <select
                        value={direction}
                        onChange={(event) => {
                          setDirection(event.target.value);
                          setPageIndex(0);
                        }}
                      >
                        <option value="all">All directions</option>
                        <option value="incoming">Incoming</option>
                        <option value="outgoing">Outgoing</option>
                      </select>
                    </label>
                  )}
                  {(page === "clients" || page === "products") && (
                    <span className="toolbar-hint">
                      Shared across your orders
                    </span>
                  )}
                </div>
                {(page === "orders" || page === "shipments") && (
                  <div className="filter-tabs" aria-label="Filter by status">
                    {statuses.map((item) => (
                      <button
                        key={item}
                        className={status === item ? "selected" : ""}
                        aria-pressed={status === item}
                        onClick={() => {
                          setStatus(item);
                          setPageIndex(0);
                        }}
                      >
                        {item === "all" ? "All statuses" : labels[item]}
                        <span>
                          {item === "all"
                            ? data[page].length
                            : data[page].filter(
                                (record) => record.status === item,
                              ).length}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
                {loading && !loaded ? (
                  <div className="empty-state">
                    <LoaderCircle className="spin" size={26} />
                    <h3>Loading your workspace</h3>
                    <p>Gathering your latest operations records.</p>
                  </div>
                ) : !loaded ? (
                  <div className="empty-state">
                    <CircleAlert size={28} />
                    <h3>Workspace unavailable</h3>
                    <p>Use Retry above to reconnect to your records.</p>
                  </div>
                ) : visible.length === 0 ? (
                  <div className="empty-state">
                    <span className="empty-icon">
                      <PageIcon size={28} />
                    </span>
                    <h3>
                      {data[page].length
                        ? "No matching records"
                        : `Your ${page} start here`}
                    </h3>
                    <p>
                      {data[page].length
                        ? "Try another search or adjust the filters."
                        : `Add your first ${config.singular} to start organizing your operations.`}
                    </p>
                    {canCreate && !data[page].length && (
                      <button
                        className="button secondary"
                        onClick={() => setModal({ kind: page })}
                      >
                        <Plus size={16} />
                        Add {config.singular}
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="table-scroll">
                    <table aria-label={config.title}>
                      <thead>
                        <tr>
                          {page === "orders" && (
                            <>
                              <th>Order / products</th>
                              <th>Client</th>
                              <th>Direction</th>
                              <th>Order date</th>
                              <th>Status</th>
                              <th className="align-right">Actions</th>
                            </>
                          )}
                          {page === "shipments" && (
                            <>
                              <th>Tracking / courier</th>
                              <th>Order / client</th>
                              <th>Dispatch</th>
                              <th>Expected delivery</th>
                              <th>Status / delivered</th>
                              <th className="align-right">Actions</th>
                            </>
                          )}
                          {page === "clients" && (
                            <>
                              <th>Company</th>
                              <th>Contact email</th>
                              <th>Orders</th>
                              <th>Actions</th>
                            </>
                          )}
                          {page === "products" && (
                            <>
                              <th>Product</th>
                              <th>SKU</th>
                              <th>Orders</th>
                              <th>Actions</th>
                            </>
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {visible.map((record) => (
                          <tr key={record.id}>
                            {page === "orders" && (
                              <>
                                <td>
                                  <button
                                    className="record-link"
                                    onClick={() => openEdit(record)}
                                    disabled={busy || !canWrite}
                                  >
                                    {orderNumber(record.id)}
                                  </button>
                                  <span className="cell-subtext">
                                    {record.items
                                      .map(
                                        (item) =>
                                          `${productNames.get(item.product_id) || `Product ${item.product_id}`} × ${item.quantity}`,
                                      )
                                      .join(", ")}
                                  </span>
                                </td>
                                <td className="client-cell">
                                  {clientNames.get(record.client_id) ||
                                    `Client ${record.client_id}`}
                                </td>
                                <td>
                                  <span
                                    className={`direction ${record.direction}`}
                                  >
                                    {record.direction === "incoming" ? (
                                      <ArrowDownLeft size={14} />
                                    ) : (
                                      <ArrowUpRight size={14} />
                                    )}
                                    {record.direction === "incoming"
                                      ? "Incoming"
                                      : "Outgoing"}
                                  </span>
                                </td>
                                <td className="date-cell">
                                  {formatDate(record.order_date)}
                                </td>
                                <td>
                                  <label
                                    className={`status-select ${record.status}`}
                                  >
                                    <span className="status-dot" />
                                    <span className="sr-only">
                                      Status for {orderNumber(record.id)}
                                    </span>
                                    <select
                                      value={record.status}
                                      disabled={busy || !canWrite}
                                      onChange={(event) =>
                                        changeStatus(record, event.target.value)
                                      }
                                    >
                                      {orderStatuses.slice(1).map((item) => (
                                        <option
                                          key={item}
                                          value={item}
                                          disabled={
                                            item !== record.status &&
                                            !(
                                              (record.status === "pending" &&
                                                item === "processing") ||
                                              (record.status === "processing" &&
                                                item === "completed")
                                            )
                                          }
                                        >
                                          {labels[item]}
                                        </option>
                                      ))}
                                    </select>
                                    {updating === record.id && (
                                      <LoaderCircle
                                        className="spin"
                                        size={13}
                                      />
                                    )}
                                  </label>
                                </td>
                                <td>
                                  <RowActions
                                    label={orderNumber(record.id)}
                                    onEdit={() => openEdit(record)}
                                    onDelete={() => openDelete(record)}
                                    disabled={busy}
                                  />
                                  <button
                                    className="shipment-shortcut"
                                    onClick={() => downloadOrder(record)}
                                  >
                                    Order report
                                    <Download size={12} />
                                  </button>
                                  {!shipmentOrders.has(record.id) &&
                                    canWrite && (
                                      <button
                                        className="shipment-shortcut"
                                        disabled={busy}
                                        onClick={() =>
                                          setModal({
                                            kind: "shipments",
                                            orderId: record.id,
                                          })
                                        }
                                      >
                                        Add shipment
                                        <ArrowRight size={12} />
                                      </button>
                                    )}
                                </td>
                              </>
                            )}
                            {page === "shipments" && (
                              <>
                                <td>
                                  <button
                                    className="record-link"
                                    disabled={busy}
                                    onClick={() => openEdit(record)}
                                  >
                                    {record.tracking_number}
                                  </button>
                                  <span className="cell-subtext">
                                    {record.courier}
                                  </span>
                                </td>
                                <td>
                                  <span className="table-strong">
                                    {orderNumber(record.order_id)}
                                  </span>
                                  <span className="cell-subtext">
                                    {clientNames.get(
                                      orderMap.get(record.order_id)?.client_id,
                                    ) || "Client unavailable"}
                                  </span>
                                </td>
                                <td className="date-cell">
                                  {formatDate(record.dispatch_date)}
                                </td>
                                <td
                                  className={`date-cell ${record.status === "delayed" ? "late-date" : ""}`}
                                >
                                  {formatDate(record.expected_delivery_date)}
                                </td>
                                <td>
                                  <Badge value={record.status} />
                                  {record.delivered_date && (
                                    <span className="cell-subtext">
                                      {formatDate(record.delivered_date)}
                                    </span>
                                  )}
                                </td>
                                <td>
                                  <RowActions
                                    label={record.tracking_number}
                                    onEdit={() => openEdit(record)}
                                    onDelete={() => openDelete(record)}
                                    disabled={busy}
                                  />
                                </td>
                              </>
                            )}
                            {page === "clients" && (
                              <>
                                <td>
                                  <div className="catalog-name">
                                    <span className="catalog-avatar">
                                      {record.name.slice(0, 2).toUpperCase()}
                                    </span>
                                    <strong>{record.name}</strong>
                                  </div>
                                </td>
                                <td>{record.email}</td>
                                <td>
                                  <span className="count-pill">
                                    {
                                      data.orders.filter(
                                        (order) =>
                                          order.client_id === record.id,
                                      ).length
                                    }
                                  </span>
                                </td>
                                <td>
                                  {canWrite && (
                                    <button
                                      className="text-button"
                                      onClick={() => openEdit(record)}
                                    >
                                      Edit
                                    </button>
                                  )}
                                </td>
                              </>
                            )}
                            {page === "products" && (
                              <>
                                <td>
                                  <div className="catalog-name">
                                    <span className="catalog-avatar product-avatar">
                                      <Package size={20} />
                                    </span>
                                    <strong>{record.name}</strong>
                                  </div>
                                </td>
                                <td>
                                  <code className="sku">{record.sku}</code>
                                </td>
                                <td>
                                  <span className="count-pill">
                                    {
                                      data.orders.filter((order) =>
                                        order.items.some(
                                          (item) =>
                                            item.product_id === record.id,
                                        ),
                                      ).length
                                    }
                                  </span>
                                </td>
                                <td>
                                  {canWrite && (
                                    <button
                                      className="text-button"
                                      onClick={() => openEdit(record)}
                                    >
                                      Edit
                                    </button>
                                  )}
                                </td>
                              </>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <div className="table-footer">
                  <span>
                    {filtered.length
                      ? `Showing ${safePage * 10 + 1}–${Math.min((safePage + 1) * 10, filtered.length)} of ${filtered.length} ${page}`
                      : `0 ${page}`}
                  </span>
                  <div className="pagination">
                    <button
                      className="icon-button"
                      aria-label="Previous page"
                      disabled={safePage === 0}
                      onClick={() => setPageIndex(safePage - 1)}
                    >
                      <ChevronLeft size={17} />
                    </button>
                    <span>
                      {safePage + 1} / {lastPage + 1}
                    </span>
                    <button
                      className="icon-button"
                      aria-label="Next page"
                      disabled={safePage === lastPage}
                      onClick={() => setPageIndex(safePage + 1)}
                    >
                      <ChevronRight size={17} />
                    </button>
                  </div>
                </div>
              </section>
            </>
          )}
          <footer className="page-footer">
            <span>
              <span className="local-dot" />
              {loading
                ? "Syncing records…"
                : error && loaded
                  ? "Refresh failed · showing previous records"
                  : loaded
                    ? "Connected to your operations database"
                    : "Waiting for connection"}
            </span>
            <span>Dates use Dubai time · UTC+4</span>
          </footer>
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          <span className="toast-icon">
            <Check size={17} />
          </span>
          {toast}
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setToast("")}
          >
            <X size={15} />
          </button>
        </div>
      )}
      {modal && (
        <RecordDialog
          modal={modal}
          data={data}
          onClose={() => setModal(null)}
          onSaved={saved}
        />
      )}
      {passwordDialog && (
        <PasswordDialog onClose={() => setPasswordDialog(false)} />
      )}
    </div>
  );
}
