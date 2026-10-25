import { useState } from "react";
import { MarkdownContent } from "@/components/markdown-content";
import type { ChatMessage } from "@/types/domain";

type ChatMessageProps = {
  message: ChatMessage;
  retryText?: string;
  busy: boolean;
  onRetry: (text: string, mayRepeatCommand: boolean) => void;
};

function readableTime(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function ChatMessageItem({ message, retryText, busy, onRetry }: ChatMessageProps) {
  const [copied, setCopied] = useState(false);
  const isAssistant = message.role === "assistant";
  const copyContent = [
    message.content,
    message.error,
  ].filter(Boolean).join("\n\n");

  async function copyMessage() {
    if (!copyContent || !navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(copyContent);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <article className={"message-row message-" + message.role}>
      {isAssistant && (
        <div className="message-avatar assistant-avatar" aria-hidden="true">
          <span className="brand-mark">&gt;_</span>
        </div>
      )}
      <div className="message-content-column">
        <div className="message-content-surface">
          {message.content && (isAssistant ? <MarkdownContent content={message.content} /> : <p className="user-message-text">{message.content}</p>)}
          {!message.content && isAssistant && busy && !message.error && <p className="message-pending"><span className="typing-dots"><i /><i /><i /></span></p>}
          {message.error && (
            <div className="message-error" role="alert">
              <p>{message.error}</p>
              {retryText && <button type="button" onClick={() => onRetry(retryText, Boolean(message.mayRepeatCommand))}>Retry</button>}
            </div>
          )}
        </div>
        <div className="message-actions">
          {message.createdAt && <time className="message-time" dateTime={message.createdAt}>{readableTime(message.createdAt)}</time>}
          {copyContent && <button type="button" onClick={copyMessage}>{copied ? "Copied" : "Copy"}</button>}
          {isAssistant && retryText && !message.error && <button type="button" disabled={busy} onClick={() => onRetry(retryText, Boolean(message.mayRepeatCommand))}>Retry</button>}
        </div>
      </div>
    </article>
  );
}
