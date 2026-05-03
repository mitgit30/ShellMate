import asyncio
import json
import traceback

try:
    from websockets.asyncio.server import serve
except ImportError:
    from websockets.server import serve

from websockets.exceptions import ConnectionClosed

from backend.app.api.dependencies import server_ops_agent
from src.runtime.config import get_runtime_settings


def _next_event(iterator):
    try:
        return next(iterator)
    except StopIteration:
        return None


async def handle_connection(websocket) -> None:
    print("WebSocket client connected.")
    try:
        async for raw_message in websocket:
            try:
                payload = json.loads(raw_message)
                if payload.get("type") != "chat":
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "error",
                                "detail": "Unsupported WebSocket message type.",
                            }
                        )
                    )
                    continue

                stream = server_ops_agent.stream_turn(
                    session_id=str(payload["session_id"]),
                    server_id=str(payload["server_id"]),
                    user_message=str(payload["message"]),
                )

                while True:
                    event = await asyncio.to_thread(_next_event, stream)
                    if event is None:
                        break
                    await websocket.send(json.dumps(event))
            except Exception as exc:  # noqa: BLE001
                print("WebSocket request failed:")
                print(traceback.format_exc())
                if websocket.close_code is None:
                    await websocket.send(json.dumps({"type": "error", "detail": str(exc)}))
    except ConnectionClosed as exc:
        print(f"WebSocket client disconnected: code={exc.code}, reason={exc.reason}")


async def start_server() -> None:
    settings = get_runtime_settings()
    print(
        "Starting WebSocket gateway on "
        f"ws://{settings.websocket_host}:{settings.websocket_port}"
    )
    async with serve(handle_connection, settings.websocket_host, settings.websocket_port):
        print("WebSocket gateway is ready.")
        await asyncio.Future()


def main() -> None:
    asyncio.run(start_server())


if __name__ == "__main__":
    main()
