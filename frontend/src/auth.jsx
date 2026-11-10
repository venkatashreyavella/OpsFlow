import { createContext, useContext, useEffect, useState } from "react";
import { Layers3, LoaderCircle, LockKeyhole } from "lucide-react";
import { request, setCsrfToken } from "./api.js";
import { Field, Modal } from "./forms.jsx";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function PasswordDialog({ onClose }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const payload = Object.fromEntries(new FormData(event.currentTarget));
    try {
      await request("/auth/password", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      window.dispatchEvent(new Event("opsflow:unauthorized"));
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }
  return (
    <Modal
      title="Change your password"
      subtitle="Changing your password signs out all your sessions."
      busy={busy}
      onClose={onClose}
    >
      <form onSubmit={save}>
        <fieldset disabled={busy}>
          <Field label="Current password">
            <input
              type="password"
              name="current_password"
              required
              autoComplete="current-password"
            />
          </Field>
          <Field label="New password">
            <input
              type="password"
              name="new_password"
              required
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
            />
          </Field>
        </fieldset>
        {error && (
          <div role="alert" className="form-error">
            {error}
          </div>
        )}
        <div className="form-actions">
          <button
            type="button"
            disabled={busy}
            className="button secondary"
            onClick={onClose}
          >
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            Save password
          </button>
        </div>
      </form>
    </Modal>
  );
}

export default function AuthProvider({ children }) {
  const [employee, setEmployee] = useState(null);
  const [setup, setSetup] = useState(false);
  const [setupTokenRequired, setSetupTokenRequired] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const status = await request("/auth/status");
        if (!active) return;
        setSetup(status.setup_required);
        setSetupTokenRequired(status.setup_token_required);
        if (!status.setup_required) {
          const result = await request("/auth/me");
          if (active) {
            setCsrfToken(result.csrf);
            setEmployee(result.employee);
          }
        }
      } catch (err) {
        if (active && err.status !== 401) setError(err.message);
      } finally {
        if (active) setLoading(false);
      }
    }
    function expired() {
      setCsrfToken("");
      setEmployee(null);
      setError("Your session ended. Please sign in again.");
    }
    load();
    window.addEventListener("opsflow:unauthorized", expired);
    return () => {
      active = false;
      window.removeEventListener("opsflow:unauthorized", expired);
    };
  }, []);

  async function authenticate(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const payload = Object.fromEntries(new FormData(event.currentTarget));
    try {
      const result = await request(setup ? "/auth/setup" : "/auth/login", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setCsrfToken(result.csrf);
      setEmployee(result.employee);
      setSetup(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    await request("/auth/logout", { method: "POST" });
    setCsrfToken("");
    setEmployee(null);
  }

  if (loading)
    return (
      <div className="auth-shell">
        <LoaderCircle className="spin" />
        <p>Opening your workspace…</p>
      </div>
    );
  if (employee)
    return (
      <AuthContext.Provider value={{ employee, logout }}>
        {children}
      </AuthContext.Provider>
    );
  return (
    <div className="auth-shell">
      <section className="auth-card">
        <div className="auth-brand">
          <Layers3 />
          opsflow.
        </div>
        <span className="auth-symbol">
          <LockKeyhole size={25} />
        </span>
        <h1>{setup ? "Set up your workspace" : "Welcome back"}</h1>
        <p>
          {setup
            ? "Create the first administrator account to start managing your operations."
            : "Sign in to your operations workspace."}
        </p>
        <form onSubmit={authenticate}>
          <fieldset disabled={busy}>
            {setup && (
              <label className="field">
                <span>Your name</span>
                <input
                  name="name"
                  required
                  maxLength={200}
                  autoComplete="name"
                />
              </label>
            )}
            <label className="field">
              <span>Email</span>
              <input
                name="email"
                type="email"
                required
                autoComplete="username"
                maxLength={254}
              />
            </label>
            <label className="field">
              <span>Password</span>
              <input
                name="password"
                type="password"
                required
                minLength={setup ? 12 : 1}
                maxLength={128}
                autoComplete={setup ? "new-password" : "current-password"}
              />
            </label>
            {setup && (
              <p className="field-hint">
                Use at least 12 characters. You can add employees after setup.
              </p>
            )}
            {setup && setupTokenRequired && (
              <>
                <label className="field">
                  <span>Workspace setup code</span>
                  <input name="setup_token" type="password" required maxLength={256} autoComplete="off" />
                </label>
                <p className="field-hint">
                  Use the OPSFLOW_SETUP_TOKEN value from your hosting dashboard.
                </p>
              </>
            )}
            {error && (
              <div className="form-error" role="alert">
                {error}
              </div>
            )}
            <button className="button primary" disabled={busy}>
              {busy
                ? "Please wait…"
                : setup
                  ? "Create administrator"
                  : "Sign in"}
            </button>
          </fieldset>
        </form>
      </section>
    </div>
  );
}
