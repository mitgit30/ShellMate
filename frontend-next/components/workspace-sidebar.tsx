"use client";

import { Brand } from "@/components/brand";
import type { ChatSession, CurrentUser, Server } from "@/types/domain";

type WorkspaceSidebarProps = {
  user: CurrentUser;
  servers: Server[];
  connectedServer: Server | null;
  sessions: ChatSession[];
  activeSession: ChatSession | null;
  loadingServers: boolean;
  busy: boolean;
  onRegisterServer: () => void;
  onConnectServer: (server: Server) => void;
  onSelectSession: (session: ChatSession) => void;
  onNewChat: () => void;
  onLogout: () => void;
};

export function WorkspaceSidebar({
  user,
  servers,
  connectedServer,
  sessions,
  activeSession,
  loadingServers,
  busy,
  onRegisterServer,
  onConnectServer,
  onSelectSession,
  onNewChat,
  onLogout,
}: WorkspaceSidebarProps) {
  function openMonitor(event: React.MouseEvent<HTMLAnchorElement>) {
    if (!connectedServer) {
      event.preventDefault();
      return;
    }

    event.preventDefault();
    const monitorUrl = new URL("/monitor", window.location.origin);
    monitorUrl.searchParams.set("server_id", connectedServer.id);

    let monitorWindow: Window | null = null;
    let handshakeTimeout = 0;
    const handleReady = (message: MessageEvent) => {
      if (
        message.origin !== window.location.origin
        || message.source !== monitorWindow
        || message.data?.type !== "shellmate-monitor-ready"
      ) return;

      monitorWindow?.postMessage({
        type: "shellmate-monitor-auth",
        token: user.token,
        email: user.email,
        serverId: connectedServer.id,
      }, window.location.origin);
      window.removeEventListener("message", handleReady);
      window.clearTimeout(handshakeTimeout);
    };

    window.addEventListener("message", handleReady);
    monitorWindow = window.open(monitorUrl.toString(), "_blank");
    if (!monitorWindow) {
      window.removeEventListener("message", handleReady);
      window.alert("Allow pop-ups to open the agent monitor in a new tab.");
      return;
    }

    handshakeTimeout = window.setTimeout(
      () => window.removeEventListener("message", handleReady),
      10_000,
    );
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-brand"><Brand compact /><span className="workspace-label">Workspace</span></div>
      <div className="sidebar-section-heading"><span>Your servers</span><button className="icon-button add-server" onClick={onRegisterServer} aria-label="Register server">+</button></div>
      <div className="server-list">
        {loadingServers && <p className="sidebar-muted">Loading servers…</p>}
        {!loadingServers && servers.length === 0 && <div className="sidebar-empty"><p>No servers yet</p><button onClick={onRegisterServer}>Register your first server</button></div>}
        {servers.map((server) => (
          <button key={server.id} className={`server-item ${connectedServer?.id === server.id ? "server-item-active" : ""}`} onClick={() => onConnectServer(server)} disabled={busy} aria-pressed={connectedServer?.id === server.id}>
            <span className={`server-status ${connectedServer?.id === server.id ? "status-online" : ""}`} />
            <span className="server-item-copy"><strong>{server.name}</strong><small>{server.host}</small></span>
            <span className="server-chevron">›</span>
          </button>
        ))}
      </div>
      {connectedServer && <div className="sidebar-chats">
        <div className="sidebar-section-heading sidebar-chat-heading">
          <span title={`Chats · ${connectedServer.name}`}>Chats · {connectedServer.name}</span>
          <button className="icon-button add-server" onClick={onNewChat} disabled={busy} aria-label="New chat" title="New chat">+</button>
        </div>
        {sessions.map((session) => (
          <button key={session.session_id} className={`chat-nav-item ${activeSession?.session_id === session.session_id ? "chat-nav-active" : ""}`} onClick={() => onSelectSession(session)} disabled={busy} aria-current={activeSession?.session_id === session.session_id ? "page" : undefined}>
            {session.title || "New chat"}
          </button>
        ))}
      </div>}
      <div className="sidebar-bottom">
        <a className="monitor-link" href={connectedServer ? `/monitor?server_id=${encodeURIComponent(connectedServer.id)}` : "#"} aria-disabled={!connectedServer} onClick={openMonitor}>
          <span className="monitor-icon">◉</span> Agent monitor <span className="external-arrow">↗</span>
        </a>
        <div className="account-row">
          <span className="account-avatar">{user.email.slice(0, 1).toUpperCase()}</span>
          <span className="account-copy"><strong>{user.email}</strong><small>Signed in</small></span>
          <button className="icon-button logout-button" onClick={onLogout} aria-label="Sign out" title="Sign out">⇥</button>
        </div>
      </div>
    </aside>
  );
}
