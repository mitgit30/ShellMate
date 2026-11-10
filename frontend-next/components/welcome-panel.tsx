"use client";

type WelcomePanelProps = {
  email: string;
  onRegisterServer: () => void;
};

export function WelcomePanel({ email, onRegisterServer }: WelcomePanelProps) {
  return (
    <div className="welcome-workspace">
      <div className="welcome-content">
        <h1>Choose a server<br /><span></span></h1>
        <p>Choose a registered server to connect, or add one to bring your workspace online.</p>
        <div className="welcome-actions">
          <button className="button button-primary" onClick={onRegisterServer}>Register a server <span>＋</span></button>
        </div>
      </div>
    </div>
  );
}
