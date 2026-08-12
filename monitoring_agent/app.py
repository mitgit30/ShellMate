from functools import lru_cache
from datetime import datetime

import httpx
import streamlit as st
from pydantic_settings import BaseSettings, SettingsConfigDict


class MonitorSettings(BaseSettings):
    api_base_url: str = "http://localhost:8000/api/v1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> MonitorSettings:
    return MonitorSettings()


def authenticate(email: str, password: str) -> None:
    response = httpx.post(
        f"{get_settings().api_base_url}/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    st.session_state.access_token = payload["access_token"]
    st.session_state.monitor_email = payload["email"]


def api_get(path: str) -> dict | list:
    response = httpx.get(
        f"{get_settings().api_base_url}{path}",
        headers={"Authorization": f"Bearer {st.session_state.access_token}"},
        timeout=30,
    )
    if response.status_code == 401:
        st.session_state.pop("access_token", None)
        st.rerun()
    response.raise_for_status()
    return response.json()


def restore_handoff_auth() -> None:
    token = st.query_params.get("access_token")
    server_id = st.query_params.get("server_id")
    if token:
        st.session_state.access_token = token
        st.session_state.monitor_server_id = server_id
        st.query_params.clear()


def render_login() -> None:
    st.title("ShellMate Agent Monitor")
    st.write("Sign in to view your agent tasks and deployment progress.")
    with st.form("monitor-login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", type="primary")
    if submitted:
        try:
            authenticate(email, password)
            st.rerun()
        except httpx.HTTPStatusError as exc:
            st.error(exc.response.json().get("detail", "Login failed."))
        except httpx.HTTPError as exc:
            st.error(f"Backend is unreachable: {exc}")


def _status_badge(status: str) -> str:
    return {
        "running": "🟡 Running",
        "completed": "🟢 Completed",
        "failed": "🔴 Failed",
    }.get(status, status.title())


def _format_time(value: str | None) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d %b %Y, %I:%M %p")
    except ValueError:
        return value


def render_dashboard() -> None:
    st.markdown(
        """
        <style>
        .monitor-caption { color: #8b949e; font-size: 0.9rem; }
        .monitor-section { margin-top: 1.2rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    server_id = st.session_state.get("monitor_server_id")
    task_path = "/monitor/tasks"
    if server_id:
        task_path += f"?server_id={server_id}"
    try:
        tasks = api_get(task_path)
    except httpx.HTTPError as exc:
        st.error(f"Could not load monitoring data: {exc}")
        return

    refresh_column, filter_column = st.columns([1, 3])
    with refresh_column:
        if st.button("Refresh", use_container_width=True):
            st.rerun()
    with filter_column:
        st.markdown(
            "<p class='monitor-caption'>Refresh manually when you want the latest agent activity.</p>",
            unsafe_allow_html=True,
        )

    if not tasks:
        st.info("No agent tasks have been recorded for this server yet.")
        return

    labels = {
        task["task_id"]: f"{_status_badge(task['status'])}  {_format_time(task.get('started_at'))}  ·  {task['user_request'][:70]}"
        for task in tasks
    }
    selected_task_id = st.selectbox(
        "Select a task",
        options=list(labels),
        format_func=lambda task_id: labels[task_id],
        key="monitor-task-selector",
    )
    try:
        details = api_get(f"/monitor/tasks/{selected_task_id}")
    except httpx.HTTPError as exc:
        st.error(f"Could not load task details: {exc}")
        return
    task = details["task"]
    events = details["events"]

    st.markdown("### Task overview")
    st.info(task["user_request"])
    columns = st.columns(4)
    columns[0].metric("Status", task["status"].title())
    columns[1].metric("Server", task["server_id"])
    columns[2].metric("Active skill", task.get("current_skill") or "—")
    columns[3].metric("Deployment", task["deployment_status"].replace("_", " ").title())

    st.markdown("### Progress")
    st.write(task.get("current_step") or "Waiting for the next agent step.")
    if task.get("error_message"):
        st.error(task["error_message"])

    st.markdown("### Tools used")
    tool_events = [
        event for event in events
        if event["event_type"] in {"tool_called", "tool_event"}
    ]
    if tool_events:
        st.dataframe(
            [
                {
                    "Tool": event.get("tool_name") or "Unknown",
                    "Command": event.get("command") or "—",
                    "Iteration": event.get("iteration") or "—",
                    "Result": "Completed" if event.get("exit_status") in (None, 0) else "Failed",
                    "Time": _format_time(event.get("created_at")),
                }
                for event in tool_events
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No tools have been used for this task yet.")

    with st.expander("Technical event timeline", expanded=False):
        st.dataframe(
            [
                {
                    "Event": event["event_type"],
                    "Detail": event.get("detail") or event.get("step") or "",
                    "Result": (
                        "Completed"
                        if event.get("exit_status") in (None, 0)
                        else "Failed"
                        if event.get("exit_status") is not None
                        else "—"
                    ),
                    "Time": _format_time(event.get("created_at")),
                }
                for event in events
                if event["event_type"] != "token"
            ],
            use_container_width=True,
            hide_index=True,
        )


def main() -> None:
    st.set_page_config(page_title="ShellMate Agent Monitor", page_icon="📊", layout="wide")
    restore_handoff_auth()
    if "access_token" not in st.session_state:
        render_login()
        return

    header, logout_column = st.columns([5, 1])
    with header:
        st.title("ShellMate Agent Monitor")
        server_label = st.session_state.get("monitor_server_id") or "All connected servers"
        st.caption(f"Monitoring: {server_label} · Signed in as {st.session_state.get('monitor_email', 'user')}")
    with logout_column:
        if st.button("Logout", use_container_width=True):
            st.session_state.pop("access_token", None)
            st.session_state.pop("monitor_email", None)
            st.rerun()
    render_dashboard()


if __name__ == "__main__":
    main()
