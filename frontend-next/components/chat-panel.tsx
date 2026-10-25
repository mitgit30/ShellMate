"use client";

import { useEffect, useRef } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { ChatMessageItem } from "@/components/chat-message";
import type { ChatMessage, ChatSession, Server } from "@/types/domain";

type ChatPanelProps = {
  server: Server;
  activeSession: ChatSession | null;
  messages: ChatMessage[];
  draft: string;
  busy: boolean;
  activity: string;
  inlineNotice?: { message: string; type: "error" | "success" };
  onDismissNotice?: () => void;
  onDeleteChat: () => void;
  onDisconnect: () => void;
  onDraftChange: (draft: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onUseSuggestion: (prompt: string) => void;
  onRetry: (prompt: string, mayRepeatCommand: boolean) => void;
};

function shortTitle(title: string) {
  const normalized = title.trim() || "New chat";
  return normalized.length > 40 ? normalized.slice(0, 39).trimEnd() + "…" : normalized;
}

export function ChatPanel({
  server,
  activeSession,
  messages,
  draft,
  busy,
  activity,
  inlineNotice,
  onDismissNotice,
  onDeleteChat,
  onDisconnect,
  onDraftChange,
  onSubmit,
  onUseSuggestion,
  onRetry,
}: ChatPanelProps) {
  const messageListRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  useEffect(() => {
    const list = messageListRef.current;
    if (list && stickToBottom.current) list.scrollTop = list.scrollHeight;
  }, [messages, activity]);

  useEffect(() => {
    stickToBottom.current = true;
    const list = messageListRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [activeSession?.session_id]);

  function trackScrollPosition() {
    const list = messageListRef.current;
    if (!list) return;
    stickToBottom.current = list.scrollHeight - list.scrollTop - list.clientHeight < 100;
  }

  function submitOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  const sessionTitle = shortTitle(activeSession?.title ?? "New chat");

  return (
    <section className="chat-view" aria-label="Server chat">
      <header className="chat-server-bar">
        <div className="chat-server-identity">
          <span className="live-dot" aria-hidden="true" />
          <div className="chat-server-copy">
            <h1 title={server.name}>{server.name}</h1>
            <p title={server.username + "@" + server.host + ":" + server.port}>
              {server.username}@{server.host}:{server.port}
            </p>
          </div>
        </div>

        <div className="chat-session-heading">
          <span className="chat-session-label">Current chat</span>
          <span className="chat-session-title" title={activeSession?.title || "New chat"}>{sessionTitle}</span>
          <details className="chat-actions-menu">
            <summary aria-label="Chat actions" title="Chat actions"><span aria-hidden="true">⋮</span></summary>
            <div className="chat-actions-popover">
              <button
                type="button"
                className="chat-delete-action"
                onClick={(event) => {
                  event.currentTarget.closest("details")?.removeAttribute("open");
                  onDeleteChat();
                }}
                disabled={busy || !activeSession}
              >
                Delete chat
              </button>
            </div>
          </details>
        </div>

        <button type="button" className="button disconnect-button" onClick={onDisconnect}>Disconnect</button>
      </header>

      <div className="chat-thread">
        {inlineNotice && (
          <div className={`chat-inline-notice chat-inline-${inlineNotice.type}`} role={inlineNotice.type === "error" ? "alert" : "status"}>
            <span>{inlineNotice.message}</span>
            {onDismissNotice && <button type="button" onClick={onDismissNotice} aria-label="Dismiss message">×</button>}
          </div>
        )}

        <div className="chat-message-list" ref={messageListRef} onScroll={trackScrollPosition} aria-live="polite">
          {messages.length === 0 ? (
            <div className="chat-empty">
              <div className="chat-empty-mark"><span className="brand-mark" aria-hidden="true">&gt;_</span></div>
              <div className="eyebrow"><span className="eyebrow-line" />Shellmate assistant</div>
              <h2>What would you like<br />to work on?</h2>
              <p>Ask about this server, investigate an issue, or start a guided deployment.</p>
              <div className="suggestion-row">
                <button type="button" onClick={() => onUseSuggestion("Check the current CPU, memory, and disk usage")}>Check server health <span>→</span></button>
                <button type="button" onClick={() => onUseSuggestion("What services are currently running?")}>Review running services <span>→</span></button>
              </div>
            </div>
          ) : (
            messages.map((message, index) => {
              const retryText = message.role === "assistant"
                ? [...messages.slice(0, index)].reverse().find((item) => item.role === "user")?.content
                : undefined;
              return (
                <ChatMessageItem
                  key={message.id ?? (message.createdAt || "message") + "-" + index}
                  message={message}
                  retryText={retryText}
                  busy={busy}
                  onRetry={onRetry}
                />
              );
            })
          )}
          {activity && <div className="chat-activity"><span className="activity-spinner" />{activity}</div>}
        </div>

        <div className="chat-composer-wrap">
          <form className="chat-composer" onSubmit={onSubmit}>
            <textarea value={draft} onChange={(event) => onDraftChange(event.target.value)} placeholder="Ask Shellmate about your server…" rows={1} disabled={busy || !activeSession} onKeyDown={submitOnEnter} aria-label="Message Shellmate" />
            <div className="chat-composer-footer">
              <span><kbd>Enter</kbd> to send <span className="composer-separator">·</span> <kbd>Shift + Enter</kbd> for a new line</span>
              <button className="send-button" type="submit" aria-label="Send message" disabled={busy || !activeSession || !draft.trim()}>{busy ? <span className="send-spinner" /> : "↑"}</button>
            </div>
          </form>
          <p className="chat-disclaimer">Shellmate can make mistakes. Review important commands and changes on your server.</p>
        </div>
      </div>
    </section>
  );
}
