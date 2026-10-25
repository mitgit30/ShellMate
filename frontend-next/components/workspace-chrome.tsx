"use client";

type WorkspaceHeaderProps = {
  serverTitle: string;
  onRegisterServer: () => void;
};

export function WorkspaceHeader({ serverTitle, onRegisterServer }: WorkspaceHeaderProps) {
  return (
    <header className="workspace-topbar">
      <div className="breadcrumb"><span>Workspace</span><span className="breadcrumb-slash">/</span><strong>{serverTitle}</strong></div>
      <div className="topbar-actions">
        <span className="secure-label"><span className="live-dot" />Private session</span>
        <button className="button button-outline top-register" onClick={onRegisterServer}>＋ <span>Register server</span></button>
      </div>
    </header>
  );
}

type NoticeBannerProps = {
  message: string;
  type: "error" | "success";
  onDismiss: () => void;
};

export function NoticeBanner({ message, type, onDismiss }: NoticeBannerProps) {
  return (
    <div className={`notice-banner notice-${type}`} role={type === "error" ? "alert" : "status"}>
      <span aria-hidden="true">{type === "error" ? "!" : "✓"}</span>{message}
      <button className="icon-button" onClick={onDismiss} aria-label="Dismiss">×</button>
    </div>
  );
}
