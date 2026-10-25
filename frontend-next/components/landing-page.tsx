"use client";

import { useState } from "react";
import { AuthDialog } from "@/components/auth-dialog";
import { Brand } from "@/components/brand";
import { LandingFooter } from "@/components/landing-footer";
import { TerminalDemo } from "@/components/terminal-demo";
import { GITHUB_URL } from "@/lib/site-links";
import type { AuthMode, AuthResult } from "@/types/domain";

type LandingPageProps = {
  onAuthenticated: (result: AuthResult) => Promise<void>;
};

export function LandingPage({ onAuthenticated }: LandingPageProps) {
  const [authMode, setAuthMode] = useState<AuthMode | null>(null);

  return (
    <main className="landing-page" id="top">
      <header className="landing-header">
        <a className="landing-brand-link" href="#top" aria-label="ShellMate home"><Brand /></a>
        <nav className="landing-nav" aria-label="Main navigation">
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub</a>
        </nav>
      </header>

      <section className="hero-section" aria-labelledby="hero-title">
        <div className="hero-copy">
          <p className="hero-kicker">AI-assisted Linux server operations</p>
          <h1 id="hero-title" aria-label="Linux server work, with fewer unknowns.">
            <span>Linux server work,{" "}</span>
            <span>with fewer unknowns.</span>
          </h1>
          <p className="hero-description">Understand what is happening on your Linux server, ask for a task in plain language, and see the work as it happens.</p>
          <div className="hero-actions">
            <button className="button button-primary hero-cta" onClick={() => setAuthMode("login")}>Open ShellMate <span aria-hidden="true">↗</span></button>
            <button className="button button-outline hero-secondary" onClick={() => setAuthMode("register")}>Create an account</button>
          </div>
        </div>
        <div className="hero-visual">
          <span className="terminal-glow" aria-hidden="true" />
          <TerminalDemo />
        </div>
      </section>

      <LandingFooter />

      {authMode && <AuthDialog initialMode={authMode} onClose={() => setAuthMode(null)} onAuthenticated={onAuthenticated} />}
    </main>
  );
}
