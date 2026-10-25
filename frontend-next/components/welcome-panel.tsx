"use client";

type WelcomePanelProps = {
  email: string;
  onRegisterServer: () => void;
};

export function WelcomePanel({ email, onRegisterServer }: WelcomePanelProps) {
  return (
    <div className="welcome-workspace">
      <div className="welcome-content">
        <div className="eyebrow"><span className="eyebrow-line" />Your operations desk</div>
        <h1>Choose a server<br /><span>{email.split("@")[0]}.</span></h1>
        <p>Choose a registered server to connect, or add one to bring your workspace online.</p>
        <div className="welcome-actions">
          <button className="button button-primary" onClick={onRegisterServer}>Register a server <span>＋</span></button>
          <span className="welcome-hint">Your SSH key is stored securely by the backend.</span>
        </div>
      </div>
    </div>
  );
}
