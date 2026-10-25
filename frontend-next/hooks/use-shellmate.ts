"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { API_PREFIX, apiRequest } from "@/lib/api-client";
import type { AuthResult, ChatHistoryMessage, ChatMessage, ChatSession, CurrentUser, Server, StreamEvent } from "@/types/domain";

export type WorkspaceNotice = {
  message: string;
  type: "error" | "success";
};

export function useShellmate() {
  const [auth, setAuth] = useState<CurrentUser | null>(null);
  const [serverDialog, setServerDialog] = useState(false);
  const [servers, setServers] = useState<Server[]>([]);
  const [connectedServer, setConnectedServer] = useState<Server | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingServers, setLoadingServers] = useState(false);
  const [notice, setNotice] = useState<WorkspaceNotice | null>(null);
  const [activity, setActivity] = useState("");

  function showError(error: unknown, fallback: string) {
    setNotice({
      message: error instanceof Error ? error.message : fallback,
      type: "error",
    });
  }

  async function signIn(result: AuthResult) {
    setAuth({ token: result.access_token, email: result.email });
    setNotice(null);
    setLoadingServers(true);
    try {
      const loadedServers = await apiRequest<Server[]>("/servers", result.access_token);
      setServers(loadedServers);
    } catch (err) {
      showError(err, "Could not load your servers.");
    } finally {
      setLoadingServers(false);
    }
  }

  async function logout() {
    if (auth) {
      try {
        await apiRequest("/auth/logout", auth.token, { method: "POST" });
      } catch {
        // Clear the local session even if the API is unavailable.
      }
    }
    setAuth(null);
    setServers([]);
    setConnectedServer(null);
    setSessions([]);
    setActiveSession(null);
    setMessages([]);
    setNotice(null);
  }

  async function loadSessionHistory(server: Server, session: ChatSession, token: string) {
    const history = await apiRequest<ChatHistoryMessage[]>(`/chat/history?session_id=${encodeURIComponent(session.session_id)}&server_id=${encodeURIComponent(server.id)}`, token);
    setActiveSession(session);
    setMessages(history.map((message) => ({
      id: crypto.randomUUID(),
      role: message.role === "user" ? "user" : "assistant",
      content: message.content,
      createdAt: message.created_at,
      mayRepeatCommand: message.role !== "user",
    })));
  }

  async function selectSession(session: ChatSession) {
    if (!auth || !connectedServer) return;
    try {
      await loadSessionHistory(connectedServer, session, auth.token);
      setNotice(null);
    } catch (err) {
      showError(err, "Could not load this chat.");
    }
  }

  async function connectServer(server: Server) {
    if (!auth) return;
    setBusy(true);
    setNotice(null);
    setActivity(`Checking SSH access to ${server.name}…`);
    try {
      await apiRequest(`/servers/${encodeURIComponent(server.id)}/test`, auth.token, { method: "POST" });
    } catch (err) {
      setConnectedServer(null);
      setSessions([]);
      setActiveSession(null);
      setMessages([]);
      showError(err, "Could not connect to this server.");
      setActivity("");
      setBusy(false);
      return;
    }

    setConnectedServer(server);
    setSessions([]);
    setActiveSession(null);
    setMessages([]);
    setActivity("Loading this server’s chats…");
    try {
      const listed = await apiRequest<ChatSession[]>(`/chat/sessions?server_id=${encodeURIComponent(server.id)}`, auth.token);
      const nextSessions = listed.length ? listed : [await apiRequest<ChatSession>("/chat/sessions", auth.token, {
        method: "POST",
        body: JSON.stringify({ server_id: server.id, title: "New chat" }),
      })];
      setSessions(nextSessions);
      await loadSessionHistory(server, nextSessions[0], auth.token);
      setActivity("");
    } catch (err) {
      showError(err, "Could not load chats for this server.");
      setActivity("");
    } finally {
      setBusy(false);
    }
  }

  async function newChat() {
    if (!auth || !connectedServer) return;
    setBusy(true);
    try {
      const session = await apiRequest<ChatSession>("/chat/sessions", auth.token, {
        method: "POST",
        body: JSON.stringify({ server_id: connectedServer.id, title: "New chat" }),
      });
      setSessions((current) => [session, ...current]);
      setActiveSession(session);
      setMessages([]);
      setNotice(null);
    } catch (err) {
      showError(err, "Could not create a new chat.");
    } finally {
      setBusy(false);
    }
  }

  async function removeChat() {
    if (!auth || !connectedServer || !activeSession) return;
    if (!window.confirm(`Delete “${activeSession.title}”? This cannot be undone.`)) return;
    setBusy(true);
    try {
      await apiRequest(`/chat/sessions/${encodeURIComponent(activeSession.session_id)}?server_id=${encodeURIComponent(connectedServer.id)}`, auth.token, { method: "DELETE" });
      const remaining = sessions.filter((item) => item.session_id !== activeSession.session_id);
      const nextSessions = remaining.length ? remaining : [await apiRequest<ChatSession>("/chat/sessions", auth.token, {
        method: "POST",
        body: JSON.stringify({ server_id: connectedServer.id, title: "New chat" }),
      })];
      setSessions(nextSessions);
      await loadSessionHistory(connectedServer, nextSessions[0], auth.token);
    } catch (err) {
      showError(err, "Could not delete this chat.");
    } finally {
      setBusy(false);
    }
  }

  async function runMessage(message: string, mayRepeatCommand = false) {
    if (!auth || !connectedServer || !activeSession || !message || busy) return;
    if (mayRepeatCommand && !window.confirm("Retrying may run server commands a second time. Continue?")) return;

    setDraft("");
    setNotice(null);
    setBusy(true);
    setActivity("Shellmate is working…");
    const assistantId = crypto.randomUUID();
    setMessages((current) => [...current,
      { id: crypto.randomUUID(), role: "user", content: message, createdAt: new Date().toISOString() },
      { id: assistantId, role: "assistant", content: "", createdAt: new Date().toISOString() },
    ]);
    let streamFailed = false;
    try {
      const response = await fetch(`${API_PREFIX}/chat/stream`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${auth.token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ session_id: activeSession.session_id, server_id: connectedServer.id, message }),
        cache: "no-store",
      });
      if (!response.ok) {
        let detail = `Chat request failed (${response.status}).`;
        try {
          const body = await response.json();
          if (typeof body.detail === "string") detail = body.detail;
        } catch {
          // Use the HTTP status when the backend did not return JSON.
        }
        throw new Error(detail);
      }
      if (!response.body) throw new Error("The backend did not return a chat stream.");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = "";
      let streamError: string | null = null;
      let receivedDone = false;
      const updateAssistant = (update: (assistant: ChatMessage) => ChatMessage) => {
        setMessages((current) => current.map((item) => item.id === assistantId ? update(item) : item));
      };
      const processLine = (line: string) => {
        if (!line.trim()) return;
        const event = JSON.parse(line) as StreamEvent;
        if (event.type === "token" && event.content) {
          updateAssistant((assistant) => ({ ...assistant, content: assistant.content + event.content }));
        } else if (event.type === "error") {
          streamError = event.detail || "The chat request failed.";
        } else if (event.type === "tool_called") {
          updateAssistant((assistant) => ({ ...assistant, mayRepeatCommand: true }));
          setActivity("Shellmate is checking the server…");
        } else if (event.type === "tool_event") {
          updateAssistant((assistant) => ({ ...assistant, mayRepeatCommand: true }));
        } else if (event.type === "step_started" || event.type === "intent_detected") {
          setActivity(event.detail || (event.tool_name ? `Using ${event.tool_name}` : "Working on your request…"));
        } else if (event.type === "done") {
          receivedDone = true;
          setActivity("");
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        pending += decoder.decode(value ?? new Uint8Array(), { stream: !done });
        const lines = pending.split("\n");
        pending = lines.pop() ?? "";
        for (const line of lines) processLine(line);
        if (done) break;
      }
      if (pending.trim()) processLine(pending);
      if (streamError) throw new Error(streamError);
      if (!receivedDone) throw new Error("The chat connection ended before the response was complete. Please retry.");

      updateAssistant((assistant) => ({
        ...assistant,
        createdAt: new Date().toISOString(),
      }));
    } catch (err) {
      streamFailed = true;
      const detail = err instanceof Error ? err.message : "The chat request failed. Please try again.";
      setMessages((current) => current.map((item) => item.id === assistantId ? {
        ...item,
        failed: true,
        error: detail,
      } : item));
    } finally {
      setBusy(false);
      setActivity("");
    }

    if (!streamFailed) {
      try {
        const updatedSessions = await apiRequest<ChatSession[]>(`/chat/sessions?server_id=${encodeURIComponent(connectedServer.id)}`, auth.token);
        setSessions(updatedSessions);
        const updatedActive = updatedSessions.find((session) => session.session_id === activeSession.session_id);
        if (updatedActive) setActiveSession(updatedActive);
      } catch {
        // The response is already visible; a title refresh failure should not replace it.
      }
    }
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runMessage(draft.trim());
  }

  async function retryMessage(message: string, mayRepeatCommand: boolean) {
    await runMessage(message, mayRepeatCommand);
  }

  function disconnectServer() {
    setConnectedServer(null);
    setActiveSession(null);
    setMessages([]);
    setSessions([]);
    setNotice(null);
  }

  function handleServerCreated(server: Server) {
    setServers((current) => [...current, server]);
    setNotice({
      message: `${server.name} was registered. Connect to it when you’re ready.`,
      type: "success",
    });
  }

  return {
    auth,
    servers,
    connectedServer,
    sessions,
    activeSession,
    messages,
    draft,
    busy,
    loadingServers,
    notice,
    activity,
    serverDialog,
    signIn,
    logout,
    connectServer,
    selectSession,
    newChat,
    removeChat,
    sendMessage,
    retryMessage,
    disconnectServer,
    setDraft,
    clearNotice: () => setNotice(null),
    setServerDialog,
    handleServerCreated,
  };
}
