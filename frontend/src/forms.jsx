import { useEffect, useRef, useState } from "react";
import { LoaderCircle, Plus, Trash2, X } from "lucide-react";
import { formatDate, orderNumber, request, today } from "./api.js";

export function Field({ label, children, ...props }) {
  return (
    <label className="field" {...props}>
      <span>{label}</span>
      {children}
    </label>
  );
}

export function Modal({ title, subtitle, children, onClose, busy }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby="modal-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
    >
      <div className="modal-heading">
        <div>
          <h2 id="modal-title">{title}</h2>
          <p>{subtitle}</p>
        </div>
        <button
          className="icon-button"
          aria-label="Close dialog"
          onClick={onClose}
          disabled={busy}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

function FormActions({ busy, onClose, label = "Save changes" }) {
  return (
    <div className="form-actions">
      <button
        type="button"
        className="button secondary"
        onClick={onClose}
        disabled={busy}
      >
        Cancel
      </button>
      <button type="submit" className="button primary" disabled={busy}>
        {busy && <LoaderCircle size={16} className="spin" />}
        {busy ? "Saving…" : label}
      </button>
    </div>
  );
}

export default function RecordDialog({ modal, data, onClose, onSaved }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const titles = {
    orders: "order",
    shipments: "shipment",
    clients: "client",
    products: "product",
  };
  const noun = titles[modal.kind];
  const editing = Boolean(modal.record);
  const deleting = modal.action === "delete";

  async function save(path, method, payload) {
    setBusy(true);
    setError("");
    try {
      await request(path, {
        method,
        body: payload ? JSON.stringify(payload) : undefined,
      });
      onSaved(
        `${noun[0].toUpperCase() + noun.slice(1)} ${deleting ? "deleted" : "saved"} successfully.`,
      );
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  const title = `${deleting ? "Delete" : editing ? "Edit" : "New"} ${noun}`;
  const subtitle = deleting
    ? "Review this action before continuing."
    : "Keep your operations records up to date.";
  let form;
  if (deleting) {
    form = (
      <form
        onSubmit={(event) => {
          event.preventDefault();
          save(`/${modal.kind}/${modal.record.id}`, "DELETE");
        }}
      >
        <p className="delete-message">
          Delete{" "}
          {modal.kind === "orders"
            ? orderNumber(modal.record.id)
            : modal.record.tracking_number}
          ?
          {modal.kind === "orders"
            ? " Its line items will also be removed. Remove any linked shipment first."
            : " The linked order will remain available."}
        </p>
        <ErrorMessage message={error} />
        <FormActions busy={busy} onClose={onClose} label={`Delete ${noun}`} />
      </form>
    );
  } else if (modal.kind === "orders") {
    form = (
      <OrderForm
        record={modal.record}
        data={data}
        save={save}
        busy={busy}
        error={error}
        onClose={onClose}
      />
    );
  } else if (modal.kind === "shipments") {
    form = (
      <ShipmentForm
        record={modal.record}
        data={data}
        save={save}
        busy={busy}
        error={error}
        onClose={onClose}
        orderId={modal.orderId}
      />
    );
  } else {
    form = (
      <CatalogForm
        kind={modal.kind}
        record={modal.record}
        save={save}
        busy={busy}
        error={error}
        onClose={onClose}
      />
    );
  }
  return (
    <Modal title={title} subtitle={subtitle} onClose={onClose} busy={busy}>
      {form}
    </Modal>
  );
}

function ErrorMessage({ message }) {
  return message ? (
    <div className="form-error" role="alert">
      {message}
    </div>
  ) : null;
}

function CatalogForm({ kind, record, save, busy, error, onClose }) {
  const isClient = kind === "clients";
  function submit(event) {
    event.preventDefault();
    const fields = Object.fromEntries(new FormData(event.currentTarget));
    save(
      record ? `/${kind}/${record.id}` : `/${kind}`,
      record ? "PUT" : "POST",
      fields,
    );
  }
  return (
    <form onSubmit={submit}>
      <fieldset disabled={busy}>
        <Field label={isClient ? "Company name" : "Product name"}>
          <input
            name="name"
            defaultValue={record?.name || ""}
            required
            maxLength={200}
            placeholder={
              isClient ? "e.g. Falcon Networks" : "e.g. Network switch"
            }
          />
        </Field>
        {isClient ? (
          <>
            <Field label="Contact email">
              <input
                name="email"
                defaultValue={record?.email || ""}
                type="email"
                required
                maxLength={254}
                placeholder="operations@company.com"
              />
            </Field>
            <Field label="Phone (optional)">
              <input
                name="phone"
                type="tel"
                maxLength={32}
                defaultValue={record?.phone || ""}
                placeholder="e.g. +971 50 123 4567"
              />
            </Field>
          </>
        ) : (
          <Field label="Product SKU">
            <input
              name="sku"
              defaultValue={record?.sku || ""}
              required
              maxLength={50}
              pattern="[A-Za-z0-9_-]+"
              title="Use letters, numbers, hyphens, or underscores"
              placeholder="e.g. NET-001"
            />
          </Field>
        )}
      </fieldset>
      <ErrorMessage message={error} />
      <FormActions
        busy={busy}
        onClose={onClose}
        label={
          record ? "Save changes" : isClient ? "Add client" : "Add product"
        }
      />
    </form>
  );
}

function newLine(item = {}) {
  return {
    key: crypto.randomUUID(),
    product_id: item.product_id || "",
    quantity: item.quantity || 1,
  };
}

function OrderForm({ record, data, save, busy, error, onClose }) {
  const [items, setItems] = useState(() =>
    record ? record.items.map(newLine) : [newLine()],
  );
  function changeLine(key, field, value) {
    setItems((current) =>
      current.map((item) =>
        item.key === key ? { ...item, [field]: value } : item,
      ),
    );
  }
  function submit(event) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const payload = {
      client_id: Number(fields.get("client_id")),
      direction: fields.get("direction"),
      order_date: fields.get("order_date"),
      items: items.map((item) => ({
        product_id: Number(item.product_id),
        quantity: Number(item.quantity),
      })),
    };
    save(
      record ? `/orders/${record.id}` : "/orders",
      record ? "PUT" : "POST",
      payload,
    );
  }
  return (
    <form onSubmit={submit}>
      <fieldset disabled={busy}>
        <Field label="Client">
          <select
            name="client_id"
            defaultValue={record?.client_id || ""}
            required
          >
            <option value="" disabled>
              Select a client
            </option>
            {data.clients.map((client) => (
              <option key={client.id} value={client.id}>
                {client.name}
              </option>
            ))}
          </select>
        </Field>
        <div className="form-grid">
          <Field label="Direction">
            <select
              name="direction"
              defaultValue={record?.direction || "outgoing"}
            >
              <option value="outgoing">Outgoing</option>
              <option value="incoming">Incoming</option>
            </select>
          </Field>
          <Field label="Order date">
            <input
              name="order_date"
              type="date"
              required
              defaultValue={record?.order_date || today()}
            />
          </Field>
        </div>
        <div className="line-heading">
          <h3>Order items</h3>
          <span>{items.length} / 100</span>
        </div>
        {items.map((item, index) => (
          <div className="item-row" key={item.key}>
            <Field label={`Product ${index + 1}`}>
              <select
                required
                value={item.product_id}
                onChange={(event) =>
                  changeLine(item.key, "product_id", event.target.value)
                }
              >
                <option value="" disabled>
                  Select a product
                </option>
                {data.products.map((product) => (
                  <option
                    key={product.id}
                    value={product.id}
                    disabled={items.some(
                      (other) =>
                        other.key !== item.key &&
                        Number(other.product_id) === product.id,
                    )}
                  >
                    {product.name} · {product.sku}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Quantity">
              <input
                type="number"
                required
                min="1"
                max="2147483647"
                step="1"
                value={item.quantity}
                onChange={(event) =>
                  changeLine(item.key, "quantity", event.target.value)
                }
              />
            </Field>
            <button
              type="button"
              className="icon-button remove-line"
              aria-label={`Remove product ${index + 1}`}
              disabled={items.length === 1}
              onClick={() =>
                setItems((current) =>
                  current.filter((line) => line.key !== item.key),
                )
              }
            >
              <Trash2 size={17} />
            </button>
          </div>
        ))}
        <button
          type="button"
          className="text-button"
          disabled={items.length >= 100 || items.length >= data.products.length}
          onClick={() => setItems((current) => [...current, newLine()])}
        >
          <Plus size={16} />
          Add another product
        </button>
      </fieldset>
      <ErrorMessage message={error} />
      <FormActions
        busy={busy}
        onClose={onClose}
        label={record ? "Save order" : "Create order"}
      />
    </form>
  );
}

function ShipmentForm({ record, data, save, busy, error, onClose, orderId }) {
  const [selectedId, setSelectedId] = useState(
    String(record?.order_id || orderId || ""),
  );
  const [dispatchDate, setDispatchDate] = useState(
    record?.dispatch_date || today(),
  );
  const order = data.orders.find(
    (candidate) => String(candidate.id) === selectedId,
  );
  const available = data.orders.filter(
    (candidate) =>
      !data.shipments.some((shipment) => shipment.order_id === candidate.id) ||
      candidate.id === record?.order_id,
  );
  function submit(event) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const payload = {
      order_id: Number(selectedId),
      courier: fields.get("courier"),
      tracking_number: fields.get("tracking_number"),
      dispatch_date: dispatchDate,
      expected_delivery_date: fields.get("expected_delivery_date"),
      delivered_date: fields.get("delivered_date") || null,
    };
    save(
      record ? `/shipments/${record.id}` : "/shipments",
      record ? "PUT" : "POST",
      payload,
    );
  }
  return (
    <form onSubmit={submit}>
      <fieldset disabled={busy}>
        <Field label="Linked order">
          <select
            required
            value={selectedId}
            disabled={Boolean(record)}
            onChange={(event) => setSelectedId(event.target.value)}
          >
            <option value="" disabled>
              Select an order
            </option>
            {available.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                {orderNumber(candidate.id)} ·{" "}
                {data.clients.find(
                  (client) => client.id === candidate.client_id,
                )?.name || `Client ${candidate.client_id}`}
              </option>
            ))}
          </select>
        </Field>
        {order && (
          <p className="field-hint">
            Order placed on {formatDate(order.order_date)}. Dispatch must be on
            or after this date.
          </p>
        )}
        <div className="form-grid">
          <Field label="Courier">
            <input
              name="courier"
              required
              maxLength={200}
              defaultValue={record?.courier || ""}
              placeholder="e.g. DHL"
            />
          </Field>
          <Field label="Tracking number">
            <input
              name="tracking_number"
              required
              maxLength={100}
              defaultValue={record?.tracking_number || ""}
              placeholder="e.g. DHL-102938"
            />
          </Field>
          <Field label="Dispatch date">
            <input
              type="date"
              required
              value={dispatchDate}
              min={order?.order_date}
              onChange={(event) => setDispatchDate(event.target.value)}
            />
          </Field>
          <Field label="Expected delivery">
            <input
              name="expected_delivery_date"
              type="date"
              required
              min={dispatchDate}
              defaultValue={record?.expected_delivery_date || ""}
            />
          </Field>
        </div>
        <Field label="Actual delivery date (optional)">
          <input
            name="delivered_date"
            type="date"
            min={dispatchDate}
            max={today()}
            defaultValue={record?.delivered_date || ""}
          />
        </Field>
        <p className="field-hint">
          Enter the actual delivery date to mark this shipment as delivered.
          Order status is managed separately.
        </p>
      </fieldset>
      <ErrorMessage message={error} />
      <FormActions
        busy={busy}
        onClose={onClose}
        label={record ? "Save shipment" : "Create shipment"}
      />
    </form>
  );
}
