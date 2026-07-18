import logging
import json

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.app.api.dependencies import server_ops_agent
from backend.app.core.error_handling import log_exception, public_error_message, status_code_for_exception
from backend.app.core.exceptions import SSHConnectionError, ServerNotFoundError
from backend.app.schemas.chat import ChatRequest, ChatResponse, ChatToolEvent
from src.runtime.models import AgentEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse, status_code=status.HTTP_200_OK)
def chat(payload: ChatRequest) -> ChatResponse:
    try:
        result = server_ops_agent.handle_turn(
            session_id=payload.session_id,
            server_id=payload.server_id,
            user_message=payload.message,
        )
    except (ServerNotFoundError, SSHConnectionError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=status_code_for_exception(exc), detail=public_error_message(exc)) from exc
    except Exception as exc:
        log_exception(logger, "chat request", exc, {"session_id": payload.session_id, "server_id": payload.server_id})
        raise HTTPException(status_code=500, detail=public_error_message(exc)) from exc

    return ChatResponse(
        session_id=payload.session_id,
        server_id=payload.server_id,
        reply=result.reply,
        tool_events=[
            ChatToolEvent(
                tool_name=event.tool_name,
                command=event.command,
                exit_status=event.exit_status,
            )
            for event in result.tool_events
        ],
    )


@router.post("/stream", status_code=status.HTTP_200_OK)
def chat_stream(payload: ChatRequest) -> StreamingResponse:
    def event_stream():
        try:
            for event in server_ops_agent.stream_turn(
                session_id=payload.session_id,
                server_id=payload.server_id,
                user_message=payload.message,
            ):
                yield json.dumps(event.as_payload()) + "\n"
        except (ServerNotFoundError, SSHConnectionError, ValueError, RuntimeError) as exc:
            yield json.dumps(AgentEvent(type="error", detail=public_error_message(exc), status_code=status_code_for_exception(exc)).as_payload()) + "\n"
        except Exception as exc:
            log_exception(logger, "chat stream", exc, {"session_id": payload.session_id, "server_id": payload.server_id})
            yield json.dumps(AgentEvent(type="error", detail=public_error_message(exc), status_code=status_code_for_exception(exc)).as_payload()) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
