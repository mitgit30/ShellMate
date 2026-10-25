"use client";

import { CONTACT_URL, DOCS_URL, GITHUB_URL } from "@/lib/site-links";

export function LandingFooter() {
  return (
    <footer className="landing-footer">
      <span>ShellMate · Linux server operations</span>
      <nav aria-label="Footer navigation">
        <a href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub</a>
        <a href={DOCS_URL} target="_blank" rel="noreferrer">Docs</a>
        <a href={CONTACT_URL} target="_blank" rel="noreferrer">Contact</a>
      </nav>
    </footer>
  );
}
