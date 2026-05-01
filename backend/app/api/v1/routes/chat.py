from fastapi import APIRouter, HTTPException, status

from backend.app.api.dependencies import server_ops_agent
from backend.app.core.exceptions import SSHConnectionError, ServerNotFoundError
from backend.app.schemas.chat import ChatRequest, ChatResponse, ChatToolEvent

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse, status_code=status.HTTP_200_OK)
def chat(payload: ChatRequest) -> ChatResponse:
    try:
        result = server_ops_agent.handle_turn(
            session_id=payload.session_id,
            server_id=payload.server_id,
            user_message=payload.message,
        )
    except ServerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SSHConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

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
