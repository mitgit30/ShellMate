"use client";

import { useCallback, useEffect, useState } from "react";
import { Brand } from "@/components/brand";
import { apiRequest } from "@/lib/api-client";
import type { MonitorEvent, MonitorTask, MonitorTaskDetails } from "@/types/domain";

const TOKEN_STORAGE_KEY = "shellmate.monitor.access-token";
const EMAIL_STORAGE_KEY = "shellmate.monitor.email";
const REFRESH_INTERVAL_MS = 5_000;

type MonitorAuthMessage = {
  type: "shellmate-monitor-auth";
  token: string;
  email: string;
  serverId: string;
};

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function label(value: string | null | undefined) {
  if (!value) return "Not started";
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function taskStatusClass(status: string) {
  if (status === "completed") return "monitor-status monitor-status-completed";
  if (status === "failed") return "monitor-status monitor-status-failed";
  return "monitor-status monitor-status-running";
}

function eventDescription(event: MonitorEvent) {
  return event.detail || event.step || event.skill_id || "Agent activity recorded.";
}

function toolCalls(events: MonitorEvent[]) {
  const calls = events.filter((event) => event.event_type === "tool_called");
  return calls.map((call) => {
    const nextCall = calls.find((candidate) => candidate.event_id > call.event_id);
    const result = events.find((event) =>
      event.event_type === "tool_event"
      && event.event_id > call.event_id
      && (!nextCall || event.event_id < nextCall.event_id)
      && event.tool_name === call.tool_name
      && event.command === call.command,
    );
    return { ...call, exit_status: result?.exit_status ?? null };
  });
}

export function AgentMonitor({ initialServerId }: { initialServerId: string }) {
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [serverId, setServerId] = useState(initialServerId);
  const [handoffState, setHandoffState] = useState<"waiting" | "ready" | "unavailable">("waiting");
  const [tasks, setTasks] = useState<MonitorTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [details, setDetails] = useState<MonitorTaskDetails | null>(null);
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState("");

  useEffect(() => {
    const storedToken = sessionStorage.getItem(TOKEN_STORAGE_KEY);

    if (storedToken) {
      const restoreSession = window.setTimeout(() => {
        setToken(storedToken);
        setEmail(sessionStorage.getItem(EMAIL_STORAGE_KEY) || "");
        setHandoffState("ready");
      }, 0);
      return () => window.clearTimeout(restoreSession);
    }

    if (!window.opener) {
      const unavailableTimer = window.setTimeout(() => setHandoffState("unavailable"), 0);
      return () => window.clearTimeout(unavailableTimer);
    }

    const handleAuth = (event: MessageEvent<MonitorAuthMessage>) => {
      if (
        event.origin !== window.location.origin
        || event.source !== window.opener
        || event.data?.type !== "shellmate-monitor-auth"
        || typeof event.data.token !== "string"
        || typeof event.data.serverId !== "string"
        || (initialServerId && initialServerId !== event.data.serverId)
      ) return;

      sessionStorage.setItem(TOKEN_STORAGE_KEY, event.data.token);
      sessionStorage.setItem(EMAIL_STORAGE_KEY, event.data.email);
      setToken(event.data.token);
      setEmail(event.data.email);
      setServerId(event.data.serverId);
      setHandoffState("ready");
      window.history.replaceState(null, "", `/monitor?server_id=${encodeURIComponent(event.data.serverId)}`);
    };

    window.addEventListener("message", handleAuth);
    const announceReady = () => window.opener?.postMessage({ type: "shellmate-monitor-ready" }, window.location.origin);
    announceReady();
    const retryAnnouncement = window.setInterval(announceReady, 300);
    const handoffTimeout = window.setTimeout(() => {
      window.clearInterval(retryAnnouncement);
      window.removeEventListener("message", handleAuth);
      if (!sessionStorage.getItem(TOKEN_STORAGE_KEY)) setHandoffState("unavailable");
    }, 10_000);

    return () => {
      window.clearInterval(retryAnnouncement);
      window.clearTimeout(handoffTimeout);
      window.removeEventListener("message", handleAuth);
    };
  }, [initialServerId]);

  const refreshTasks = useCallback(async (showLoading = false) => {
    if (!token || !serverId) return;
    if (showLoading) setLoadingTasks(true);
    try {
      const query = new URLSearchParams({ server_id: serverId });
      const result = await apiRequest<MonitorTask[]>(`/monitor/tasks?${query}`, token);
      setTasks(result);
      setSelectedTaskId((current) => current && result.some((task) => task.task_id === current)
        ? current
        : result[0]?.task_id ?? "");
      setError("");
      setLastUpdated(new Date().toISOString());
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not load monitor tasks.");
    } finally {
      if (showLoading) setLoadingTasks(false);
    }
  }, [serverId, token]);

  useEffect(() => {
    if (!token || !serverId) return;
    const initialRefresh = window.setTimeout(() => void refreshTasks(true), 0);
    const interval = window.setInterval(() => void refreshTasks(), REFRESH_INTERVAL_MS);
    return () => {
      window.clearTimeout(initialRefresh);
      window.clearInterval(interval);
    };
  }, [refreshTasks, serverId, token]);

  useEffect(() => {
    if (!token || !selectedTaskId) {
      return;
    }

    let active = true;
    const refreshDetails = async (showLoading = false) => {
      if (showLoading) setLoadingDetails(true);
      try {
        const result = await apiRequest<MonitorTaskDetails>(`/monitor/tasks/${encodeURIComponent(selectedTaskId)}`, token);
        if (!active) return;
        setDetails(result);
        setError("");
        setLastUpdated(new Date().toISOString());
      } catch (requestError) {
        if (!active) return;
        setError(requestError instanceof Error ? requestError.message : "Could not load task details.");
      } finally {
        if (active && showLoading) setLoadingDetails(false);
      }
    };

    const initialRefresh = window.setTimeout(() => void refreshDetails(true), 0);
    const interval = window.setInterval(() => void refreshDetails(), REFRESH_INTERVAL_MS);
    return () => {
      active = false;
      window.clearTimeout(initialRefresh);
      window.clearInterval(interval);
    };
  }, [selectedTaskId, token]);

  const selectedDetails = details?.task.task_id === selectedTaskId ? details : null;
  const selectedTask = selectedDetails?.task ?? tasks.find((task) => task.task_id === selectedTaskId) ?? null;
  const events = selectedDetails?.events ?? [];
  const calls = toolCalls(events);
  const visibleEvents = events.filter((event) => event.event_type !== "token");

  return (
    <main className="agent-monitor-page">
      <header className="agent-monitor-header">
        <div className="agent-monitor-brand"><Brand compact /><span>Agent monitor</span></div>
        <div className="agent-monitor-header-actions">
          <span className="agent-monitor-live"><span className="live-dot" />Updates every 5 seconds</span>
          <button className="button button-outline" type="button" onClick={() => window.close()}>Close tab</button>
        </div>
      </header>

      <div className="agent-monitor-content">
        <div className="agent-monitor-context">
          <span className="agent-monitor-context-dot" />
          <span className="agent-monitor-server">{serverId ? `Server ${serverId}` : "No server selected"}</span>
          {email && <span className="agent-monitor-account">{email}</span>}
          {lastUpdated && <span className="agent-monitor-updated">Updated {formatDate(lastUpdated)}</span>}
        </div>

        {handoffState === "unavailable" && !token && (
          <section className="agent-monitor-empty-state" role="status">
            <h1>Open the monitor from ShellMate</h1>
            <p>Connect to a server, then choose Agent monitor in the workspace sidebar. Your existing sign-in will be carried into this tab.</p>
          </section>
        )}

        {handoffState === "waiting" && !token && (
          <section className="agent-monitor-empty-state" role="status">
            <span className="activity-spinner" />
            <p>Connecting this tab to your ShellMate session…</p>
          </section>
        )}

        {error && <div className="agent-monitor-error" role="alert">{error}</div>}

        {token && serverId && (
          <div className="agent-monitor-layout">
            <aside className="agent-task-list-panel" aria-label="Recent agent tasks">
              <div className="agent-task-list-heading">
                <h1>Recent tasks</h1>
                <span>{tasks.length}</span>
              </div>
              <div className="agent-task-list-scroll">
                {loadingTasks && tasks.length === 0 && <p className="agent-monitor-muted">Loading tasks…</p>}
                {!loadingTasks && tasks.length === 0 && (
                  <p className="agent-monitor-muted agent-task-list-empty">No tasks have been recorded for this server yet.</p>
                )}
                {tasks.map((task) => (
                  <button
                    className={`agent-task-item ${task.task_id === selectedTaskId ? "agent-task-item-selected" : ""}`}
                    key={task.task_id}
                    type="button"
                    onClick={() => setSelectedTaskId(task.task_id)}
                    aria-pressed={task.task_id === selectedTaskId}
                  >
                    <span className={taskStatusClass(task.status)}>{label(task.status)}</span>
                    <span className="agent-task-request">{task.user_request}</span>
                    <span className="agent-task-time">{formatDate(task.started_at)}</span>
                  </button>
                ))}
              </div>
            </aside>

            <section className="agent-task-details" aria-live="polite">
              {!selectedTask && !loadingTasks && (
                <div className="agent-monitor-empty-state"><h2>No task selected</h2><p>Agent activity for this server will appear here.</p></div>
              )}
              {selectedTask && (
                <>
                  <div className="agent-task-title-row">
                    <div>
                      <span className={taskStatusClass(selectedTask.status)}>{label(selectedTask.status)}</span>
                      <h2>{selectedTask.user_request}</h2>
                      <p className="agent-task-started">Started {formatDate(selectedTask.started_at)}</p>
                    </div>
                    <button className="button button-outline agent-refresh-button" type="button" onClick={() => { void refreshTasks(true); }} disabled={loadingTasks}>
                      {loadingTasks ? "Refreshing…" : "Refresh"}
                    </button>
                  </div>

                  {selectedTask.error_message && <div className="agent-monitor-error" role="alert">{selectedTask.error_message}</div>}

                  <div className="agent-task-metrics">
                    <article className="agent-task-metric">
                      <span>Current step</span>
                      <strong>{selectedTask.current_step || "Waiting for activity"}</strong>
                    </article>
                    <article className="agent-task-metric">
                      <span>Skill</span>
                      <strong>{label(selectedTask.current_skill)}</strong>
                    </article>
                    <article className="agent-task-metric">
                      <span>Deployment</span>
                      <strong className={`deployment-${selectedTask.deployment_status}`}>
                        {label(selectedTask.deployment_status)}
                      </strong>
                    </article>
                  </div>

                  <section className="agent-monitor-section">
                    <div className="agent-monitor-section-heading">
                      <h3>Tools used</h3>
                      <span>{calls.length}</span>
                    </div>
                    {loadingDetails && events.length === 0 && <p className="agent-monitor-muted">Loading task activity…</p>}
                    {!loadingDetails && calls.length === 0 && <p className="agent-monitor-muted">No tools have been used for this task yet.</p>}
                    {calls.length > 0 && (
                      <div className="agent-tools-table-wrap">
                        <table className="agent-tools-table">
                          <thead><tr><th>Tool</th><th>Command</th><th>Iteration</th><th>Result</th><th>Time</th></tr></thead>
                          <tbody>
                            {calls.map((call) => (
                              <tr key={call.event_id}>
                                <td>{call.tool_name || "Unknown"}</td>
                                <td><code>{call.command || "—"}</code></td>
                                <td>{call.iteration ?? "—"}</td>
                                <td>
                                  {call.exit_status === null ? "Running" : call.exit_status === 0 ? "Completed" : "Failed"}
                                </td>
                                <td>{formatDate(call.created_at)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </section>

                  <details className="agent-event-timeline">
                    <summary>Technical event timeline <span>{visibleEvents.length} events</span></summary>
                    <ol>
                      {visibleEvents.map((event) => (
                        <li key={event.event_id}>
                          <span className="agent-event-type">{label(event.event_type)}</span>
                          <span className="agent-event-description">{eventDescription(event)}</span>
                          <time dateTime={event.created_at}>{formatDate(event.created_at)}</time>
                        </li>
                      ))}
                      {visibleEvents.length === 0 && <li className="agent-monitor-muted">No events have been recorded.</li>}
                    </ol>
                  </details>
                </>
              )}
            </section>
          </div>
        )}
      </div>
    </main>
  );
}
