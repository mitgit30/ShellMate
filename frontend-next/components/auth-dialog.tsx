"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { apiRequest } from "@/lib/api-client";
import type { AuthMode, AuthResult } from "@/types/domain";

type AuthDialogProps = {
  initialMode: AuthMode;
  onClose: () => void;
  onAuthenticated: (result: AuthResult) => Promise<void>;
};

export function AuthDialog({ initialMode, onClose, onAuthenticated }: AuthDialogProps) {
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const result = await apiRequest<AuthResult>(`/auth/${mode}`, undefined, {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), password }),
      });
      await onAuthenticated(result);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-title">
        <button className="icon-button dialog-close" type="button" onClick={onClose} aria-label="Close">×</button>
        <div className="dialog-eyebrow">Your server workspace</div>
        <h2 id="auth-title">{mode === "login" ? "Welcome back" : "Create your account"}</h2>
        <p className="dialog-subtitle">Sign in to continue to Shellmate.</p>
        <div className="auth-tabs" role="tablist" aria-label="Account access">
          <button role="tab" aria-selected={mode === "login"} className={mode === "login" ? "selected" : ""} onClick={() => { setMode("login"); setError(""); }}>Sign in</button>
          <button role="tab" aria-selected={mode === "register"} className={mode === "register" ? "selected" : ""} onClick={() => { setMode("register"); setError(""); }}>Create account</button>
        </div>
        <form className="auth-form" onSubmit={submit}>
          <label htmlFor="auth-email">Email</label>
          <input id="auth-email" type="email" autoComplete="email" placeholder="you@example.com" value={email} onChange={(event) => setEmail(event.target.value)} required />
          <label htmlFor="auth-password">Password</label>
          <input id="auth-password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} placeholder="At least 8 characters" minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} required />
          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="button button-primary auth-submit" type="submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
        <p className="privacy-note">Your SSH keys are uploaded securely and never shown in this workspace.</p>
      </section>
    </div>
  );
}
