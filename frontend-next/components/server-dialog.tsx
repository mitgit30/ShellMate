"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { apiRequest } from "@/lib/api-client";
import type { Server } from "@/types/domain";

type ServerDialogProps = {
  token: string;
  onClose: () => void;
  onCreated: (server: Server) => void;
};

export function ServerDialog({ token, onClose, onCreated }: ServerDialogProps) {
  const [host, setHost] = useState("");
  const [serverId, setServerId] = useState("");
  const [customId, setCustomId] = useState(false);
  const [name, setName] = useState("");
  const [port, setPort] = useState("22");
  const [selectedUsername, setSelectedUsername] = useState("ubuntu");
  const [customUsername, setCustomUsername] = useState("");
  const [keyFile, setKeyFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function updateHost(value: string) {
    setHost(value);
    if (!customId) {
      const generated = value.trim() ? `srv-${value.trim().replaceAll(".", "-")}` : "";
      setServerId(generated);
      setName((current) => !current || current.startsWith("srv-") ? generated : current);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!keyFile) {
      setError("Choose the private key file for this server.");
      return;
    }
    setBusy(true);
    let uploadedKeyId: string | undefined;
    try {
      const formData = new FormData();
      formData.append("private_key", keyFile);
      const uploaded = await apiRequest<{ key_id: string }>("/keys/upload", token, {
        method: "POST",
        body: formData,
      });
      uploadedKeyId = uploaded.key_id;
      const server = await apiRequest<Server>("/servers", token, {
        method: "POST",
        body: JSON.stringify({
          id: serverId.trim(),
          name: name.trim(),
          host: host.trim(),
          port: Number(port),
          username: (selectedUsername === "Custom" ? customUsername : selectedUsername).trim(),
          key_id: uploaded.key_id,
        }),
      });
      onCreated(server);
      onClose();
    } catch (err) {
      if (uploadedKeyId) {
        try {
          await apiRequest(`/keys/${encodeURIComponent(uploadedKeyId)}`, token, { method: "DELETE" });
        } catch {
          // Keep the original registration error; key deletion is best-effort cleanup.
        }
      }
      setError(err instanceof Error ? err.message : "Server registration failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !busy) onClose();
    }}>
      <section className="auth-dialog server-dialog" role="dialog" aria-modal="true" aria-labelledby="server-dialog-title">
        <button className="icon-button dialog-close" type="button" onClick={onClose} aria-label="Close" disabled={busy}>×</button>
        <div className="dialog-eyebrow">Server access</div>
        <h2 id="server-dialog-title">Register a server</h2>
        <p className="dialog-subtitle">Add an Ubuntu or other Linux host using its SSH key.</p>
        <form className="auth-form server-form" onSubmit={submit}>
          <label htmlFor="server-host">Public IPv4 address</label>
          <input id="server-host" value={host} onChange={(event) => updateHost(event.target.value)} placeholder="54.210.123.45" required />
          <div className="form-grid">
            <div><label htmlFor="server-id">Server ID</label><input id="server-id" value={serverId} onChange={(event) => { setCustomId(true); setServerId(event.target.value); }} required /></div>
            <div><label htmlFor="server-name">Display name</label><input id="server-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Production" minLength={2} required /></div>
          </div>
          <div className="form-grid form-grid-small">
            <div><label htmlFor="server-port">SSH port</label><input id="server-port" type="number" min={1} max={65535} value={port} onChange={(event) => setPort(event.target.value)} required /></div>
            <div><label htmlFor="server-user">Username</label><select id="server-user" value={selectedUsername} onChange={(event) => setSelectedUsername(event.target.value)}><option>ubuntu</option><option>azureuser</option><option>ec2-user</option><option>debian</option><option>root</option><option>Custom</option></select></div>
          </div>
          {selectedUsername === "Custom" && <><label htmlFor="custom-user">Custom username</label><input id="custom-user" value={customUsername} onChange={(event) => setCustomUsername(event.target.value)} placeholder="Enter SSH username" required /></>}
          <label htmlFor="private-key">SSH private key (.pem)</label>
          <input id="private-key" type="file" accept=".pem,application/x-pem-file" onChange={(event) => setKeyFile(event.target.files?.[0] ?? null)} required />
          <p className="input-hint">The key is stored by the backend’s configured key storage service.</p>
          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="button button-primary auth-submit" type="submit" disabled={busy}>{busy ? "Registering…" : "Register server"}</button>
        </form>
      </section>
    </div>
  );
}
