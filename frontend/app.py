from functools import lru_cache

import httpx
import streamlit as st
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FrontendSettings(BaseSettings):
    api_base_url: str = Field(default="http://localhost:8000/api/v1")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> FrontendSettings:
    return FrontendSettings()


def get_api_client() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(base_url=settings.api_base_url, timeout=20.0)


def initialize_session_state() -> None:
    if "selected_server_id" not in st.session_state:
        st.session_state.selected_server_id = None
    if "connected_server_id" not in st.session_state:
        st.session_state.connected_server_id = None
    if "connected_server_name" not in st.session_state:
        st.session_state.connected_server_name = None
    if "active_view" not in st.session_state:
        st.session_state.active_view = "chat"
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []


def list_servers() -> list[dict]:
    with get_api_client() as client:
        response = client.get("/servers")
        response.raise_for_status()
        return response.json()


def create_server(
    server_id: str,
    name: str,
    host: str,
    port: int,
    username: str,
    private_key_path: str,
) -> dict:
    payload = {
        "id": server_id,
        "name": name,
        "host": host,
        "port": port,
        "username": username,
        "private_key_path": private_key_path,
    }
    with get_api_client() as client:
        response = client.post("/servers", json=payload)
        response.raise_for_status()
        return response.json()


def upload_private_key(uploaded_file) -> dict:
    files = {
        "private_key": (
            uploaded_file.name,
            uploaded_file.getvalue(),
            uploaded_file.type or "application/x-pem-file",
        )
    }
    with get_api_client() as client:
        response = client.post("/keys/upload", files=files)
        response.raise_for_status()
        return response.json()


def test_connection(server_id: str) -> dict:
    with get_api_client() as client:
        response = client.post(f"/servers/{server_id}/test")
        response.raise_for_status()
        return response.json()


def execute_command(server_id: str, command: str) -> dict:
    with get_api_client() as client:
        response = client.post(
            "/commands/execute",
            json={"server_id": server_id, "command": command},
        )
        response.raise_for_status()
        return response.json()


def load_styles() -> None:
    st.markdown(
        """
        <style>
        div.block-container {
            padding-top: 2rem;
        }
        .status-card {
            padding: 0.9rem 1rem;
            border: 1px solid #d6dbe1;
            border-radius: 0.8rem;
            background: #f8fafc;
            margin-bottom: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def generate_server_id(host: str) -> str:
    sanitized_host = host.strip().replace(".", "-")
    if not sanitized_host:
        return ""
    return f"srv-{sanitized_host}"


def render_server_registry() -> bool:
    username_options = ["ubuntu", "ec2-user", "azureuser", "root", "debian", "Custom"]

    with st.form("server-registration-form", clear_on_submit=True):
        host = st.text_input("Public IPv4", placeholder="54.210.123.45")
        generated_server_id = generate_server_id(host)
        server_id = st.text_input(
            "Server ID",
            value=generated_server_id,
            help="Auto-generated from the IPv4 address. You can change it if needed.",
        )
        name = st.text_input(
            "Display name",
            value=generated_server_id or "",
            help="Friendly label shown in the app.",
        )
        port = st.number_input("Port", min_value=1, max_value=65535, value=22)
        selected_username = st.selectbox("Username", options=username_options)
        username = (
            st.text_input("Custom username")
            if selected_username == "Custom"
            else selected_username
        )
        private_key_file = st.file_uploader(
            "Upload .pem file",
            type=["pem"],
            help="Upload the SSH private key used for this Linux server.",
        )
        submitted = st.form_submit_button("Register server")

    if submitted:
        try:
            if private_key_file is None:
                st.error("Upload a .pem file before registering the server.")
                return False

            uploaded_key = upload_private_key(private_key_file)
            resolved_server_id = server_id.strip() or generated_server_id
            resolved_name = name.strip() or resolved_server_id
            create_server(
                server_id=resolved_server_id,
                name=resolved_name,
                host=host.strip(),
                port=int(port),
                username=username.strip(),
                private_key_path=uploaded_key["private_key_path"],
            )
            st.success("Server registered.")
            st.session_state.active_view = "registered_servers"
            return True
        except httpx.HTTPStatusError as exc:
            st.error(f"Registration failed: {exc.response.text}")
        except httpx.HTTPError as exc:
            st.error(f"Backend is unreachable: {exc}")

    return False


def render_server_table(servers: list[dict]) -> None:
    st.subheader("Registered Servers")
    if not servers:
        st.info("No servers registered yet.")
        return

    st.dataframe(servers, use_container_width=True)


def render_connection_panel(servers: list[dict]) -> None:
    if not servers:
        st.info("Register a server first.")
        return

    server_options = {
        f"{server['name']} ({server['host']})": server["id"] for server in servers
    }
    selected_label = st.selectbox(
        "Connect to server",
        options=list(server_options.keys()),
        key="connection_check_server",
    )
    selected_server = server_options[selected_label]

    if st.button("Connect server", use_container_width=True):
        try:
            test_connection(selected_server)
            st.session_state.connected_server_id = selected_server
            st.session_state.connected_server_name = selected_label
            st.session_state.active_view = "chat"
            st.success(f"Connected to '{selected_label}'.")
        except httpx.HTTPStatusError as exc:
            st.session_state.connected_server_id = None
            st.session_state.connected_server_name = None
            st.error(f"Connection test failed: {exc.response.text}")
        except httpx.HTTPError as exc:
            st.session_state.connected_server_id = None
            st.session_state.connected_server_name = None
            st.error(f"Backend is unreachable: {exc}")


def render_chat_panel() -> None:
    st.subheader("Chat Workspace")
    connected_server_id = st.session_state.connected_server_id
    connected_server_name = st.session_state.connected_server_name

    if not connected_server_id:
        st.info("Connect to a registered server from the sidebar to unlock chat access.")
        return

    st.caption(f"Connected server: {connected_server_name}")
    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("Ask something like: uptime or df -h")
    if not prompt:
        return

    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        result = execute_command(server_id=connected_server_id, command=prompt.strip())
        assistant_reply = (
            f"Command: `{result['command']}`\n\n"
            f"Exit status: `{result['exit_status']}`\n\n"
            f"Stdout:\n```bash\n{result['stdout'] or '<empty>'}\n```\n\n"
            f"Stderr:\n```bash\n{result['stderr'] or '<empty>'}\n```"
        )
    except httpx.HTTPStatusError as exc:
        assistant_reply = f"Command failed: {exc.response.text}"
    except httpx.HTTPError as exc:
        assistant_reply = f"Backend is unreachable: {exc}"

    st.session_state.chat_messages.append(
        {"role": "assistant", "content": assistant_reply}
    )
    with st.chat_message("assistant"):
        st.markdown(assistant_reply)


def render_sidebar(servers: list[dict]) -> tuple[bool, list[dict]]:
    server_registered = False
    sidebar_servers = servers

    with st.sidebar:
        st.header("Server Manager")
        st.caption("Register servers, browse them, and connect before chatting.")

        if st.button("Chat", use_container_width=True):
            st.session_state.active_view = "chat"
        if st.button("Registered Servers", use_container_width=True):
            st.session_state.active_view = "registered_servers"

        st.divider()
        st.subheader("Register Server")
        server_registered = render_server_registry()
        if server_registered:
            try:
                sidebar_servers = list_servers()
            except httpx.HTTPError as exc:
                st.warning(f"Server saved, but refresh failed: {exc}")

        st.divider()
        st.subheader("Connection Access")
        render_connection_panel(sidebar_servers)

        connected_server_name = st.session_state.connected_server_name
        if connected_server_name:
            st.success(f"Chat enabled for {connected_server_name}")
        else:
            st.warning("Chat is locked until a server connection succeeds.")

    return server_registered, sidebar_servers


def render_main_content(servers: list[dict]) -> None:
    if st.session_state.active_view == "registered_servers":
        render_server_table(servers)
        return

    render_chat_panel()


def main() -> None:
    st.set_page_config(
        page_title="Linux Server Manager",
        page_icon=":material/terminal:",
        layout="wide",
    )
    initialize_session_state()
    load_styles()

    st.title("Chat-Based Linux Server Manager")
    st.write(
        "Register Linux hosts using a public IPv4 address, username selection,"
        " and uploaded `.pem` key, then verify SSH access and unlock chat."
    )

    try:
        servers = list_servers()
        st.markdown(
            f"<div class='status-card'>Backend connected. Registered servers: {len(servers)}</div>",
            unsafe_allow_html=True,
        )
    except httpx.HTTPError as exc:
        servers = []
        st.markdown(
            "<div class='status-card'>Backend disconnected. Start FastAPI on"
            " http://localhost:8000 before using the UI.</div>",
            unsafe_allow_html=True,
        )
        st.warning(f"API connection failed: {exc}")

    server_registered, servers = render_sidebar(servers)
    if server_registered and not servers:
        try:
            servers = list_servers()
        except httpx.HTTPError as exc:
            st.warning(f"Server saved, but refresh failed: {exc}")

    render_main_content(servers)


if __name__ == "__main__":
    main()
