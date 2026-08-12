from functools import lru_cache

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


@st.fragment(run_every="3s")
def render_dashboard() -> None:
    server_id = st.session_state.get("monitor_server_id")
    task_path = "/monitor/tasks"
    if server_id:
        task_path += f"?server_id={server_id}"
    tasks = api_get(task_path)
    if not tasks:
        st.info("No agent tasks have been recorded yet.")
        return

    labels = {
        task["task_id"]: f"{_status_badge(task['status'])} · {task['server_id']} · {task['started_at']}"
        for task in tasks
    }
    selected_task_id = st.selectbox(
        "Task",
        options=list(labels),
        format_func=lambda task_id: labels[task_id],
    )
    details = api_get(f"/monitor/tasks/{selected_task_id}")
    task = details["task"]
    events = details["events"]

    st.subheader("Task")
    st.write(task["user_request"])
    columns = st.columns(4)
    columns[0].metric("Status", task["status"].title())
    columns[1].metric("Server", task["server_id"])
    columns[2].metric("Skill", task.get("current_skill") or "—")
    columns[3].metric("Deployment", task["deployment_status"].replace("_", " ").title())

    st.subheader("Live progress")
    st.write(task.get("current_step") or "Waiting for the next agent step.")
    if task.get("error_message"):
        st.error(task["error_message"])

    st.subheader("Tools used")
    tool_events = [
        event for event in events
        if event["event_type"] in {"tool_called", "tool_event"}
    ]
    if tool_events:
        st.dataframe(
            [
                {
                    "Tool": event.get("tool_name") or "Unknown",
                    "Status": "Success" if event.get("exit_status") in (None, 0) else "Failed",
                    "Time": event["created_at"],
                }
                for event in tool_events
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No tools have been used for this task yet.")

    with st.expander("Event timeline"):
        st.dataframe(
            [
                {
                    "Event": event["event_type"],
                    "Detail": event.get("detail") or event.get("step") or "",
                    "Time": event["created_at"],
                }
                for event in events
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

    st.title("ShellMate Agent Monitor")
    st.caption(f"Signed in as {st.session_state.get('monitor_email', 'user')}")
    if st.button("Logout"):
        st.session_state.pop("access_token", None)
        st.session_state.pop("monitor_email", None)
        st.rerun()
    render_dashboard()


if __name__ == "__main__":
    main()
