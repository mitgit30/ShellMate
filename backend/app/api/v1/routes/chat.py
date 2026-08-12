import logging
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.app.api.dependencies import chat_analytics_service, chat_history_service, model_client, monitor_service, server_ops_agent, server_service
from backend.app.core.auth import get_current_user
from backend.app.repositories.user_repository import User
from backend.app.core.error_handling import log_exception, public_error_message, status_code_for_exception
from backend.app.core.exceptions import SSHConnectionError, ServerNotFoundError
from backend.app.schemas.chat import ChatHistoryMessage, ChatRequest, ChatResponse, ChatSessionCreate, ChatSessionSummary, ChatToolEvent
from src.runtime.models import AgentEvent
from backend.app.services.chat_analytics_service import is_chat_count_request, requested_chat_window

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


def chat_count_reply(user_id: str, message: str) -> str | None:
    if not is_chat_count_request(message):
        return None
    days = requested_chat_window(message) or 1
    count = chat_analytics_service.count_user_messages(user_id, days)
    unit = "chat" if count == 1 else "chats"
    return f"You had {count} {unit} with ShellMate in the last {days} days."


def restore_chat_session(payload: ChatRequest, user_id: str) -> None:
    chat_history_service.ensure_session(user_id, payload.session_id, payload.server_id)
    history = chat_history_service.list_messages(user_id, payload.session_id, payload.server_id)
    server_ops_agent.restore_session(payload.session_id, payload.server_id, history)


def update_chat_title(user_id: str, payload: ChatRequest) -> None:
    session = chat_history_service.get_session(user_id, payload.session_id, payload.server_id)
    if session["title"] != "New chat":
        return
    fallback = " ".join(payload.message.split())[:60].rstrip(" .,!?;:") or "New chat"
    title = fallback
    try:
        response = model_client.chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a chat-title generator. Suggest a short title for the user's message. "
                        "Use only the message as context. Do not answer the message, do not explain anything, "
                        "and do not say that you lack access or information. "
                        "Return exactly one descriptive title of 3 to 6 words, plain text only, "
                        "without quotes, punctuation, emojis, or a trailing period."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Suggest a title for this message only:\n{payload.message[:500]}",
                },
            ],
            tools=[],
        )
        generated = str(response.get("message", {}).get("content", "")).strip().strip('"')
        if generated:
            title = " ".join(generated.split()).strip(" .,!?:;\"'")[:80]
    except Exception:
        logger.exception("chat_title_generation_failed session_id=%s", payload.session_id)
    chat_history_service.set_title(user_id, payload.session_id, payload.server_id, title)


@router.post("", response_model=ChatResponse, status_code=status.HTTP_200_OK)
def chat(payload: ChatRequest, user: User = Depends(get_current_user)) -> ChatResponse:
    server_service.get_server_record(payload.server_id, user.id)
    analytics_reply = chat_count_reply(user.id, payload.message)
    if analytics_reply is not None:
        return ChatResponse(session_id=payload.session_id, server_id=payload.server_id, reply=analytics_reply)
    restore_chat_session(payload, user.id)
    task_id = monitor_service.start_task(user.id, payload.session_id, payload.server_id, payload.message)
    try:
        reply_parts: list[str] = []
        tool_events: list[ChatToolEvent] = []
        for event in server_ops_agent.stream_turn(
            session_id=payload.session_id,
            server_id=payload.server_id,
            user_message=payload.message,
        ):
            monitor_service.record_event(task_id, event.as_payload())
            if event.type == "token":
                reply_parts.append(event.content or "")
            elif event.type == "tool_event":
                tool_events.append(ChatToolEvent(
                    tool_name=event.tool_name or "",
                    command=event.command or "",
                    exit_status=event.exit_status or 0,
                ))
        monitor_service.complete_task(task_id)
        reply = "".join(reply_parts).strip()
        chat_history_service.append(user.id, payload.session_id, payload.server_id, "user", payload.message)
        chat_history_service.append(user.id, payload.session_id, payload.server_id, "assistant", reply)
        update_chat_title(user.id, payload)
    except (ServerNotFoundError, SSHConnectionError, ValueError, RuntimeError) as exc:
        monitor_service.fail_task(task_id, public_error_message(exc))
        raise HTTPException(status_code=status_code_for_exception(exc), detail=public_error_message(exc)) from exc
    except Exception as exc:
        monitor_service.fail_task(task_id, public_error_message(exc))
        log_exception(logger, "chat request", exc, {"session_id": payload.session_id, "server_id": payload.server_id})
        raise HTTPException(status_code=500, detail=public_error_message(exc)) from exc

    return ChatResponse(
        session_id=payload.session_id,
        server_id=payload.server_id,
        reply=reply,
        tool_events=tool_events,
    )


@router.get("/history", response_model=list[ChatHistoryMessage])
def chat_history(
    session_id: str,
    server_id: str,
    user: User = Depends(get_current_user),
) -> list[ChatHistoryMessage]:
    server_service.get_server_record(server_id, user.id)
    return [
        ChatHistoryMessage(**message)
        for message in chat_history_service.list_messages(user.id, session_id, server_id)
    ]


@router.get("/sessions", response_model=list[ChatSessionSummary])
def chat_sessions(server_id: str, user: User = Depends(get_current_user)) -> list[ChatSessionSummary]:
    server_service.get_server_record(server_id, user.id)
    return [
        ChatSessionSummary(**session)
        for session in chat_history_service.list_sessions(user.id, server_id)
    ]


@router.post("/sessions", response_model=ChatSessionSummary, status_code=status.HTTP_201_CREATED)
def create_chat_session(
    payload: ChatSessionCreate,
    user: User = Depends(get_current_user),
) -> ChatSessionSummary:
    server_service.get_server_record(payload.server_id, user.id)
    return ChatSessionSummary(
        **chat_history_service.create_session(user.id, payload.server_id, payload.title)
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat_session(
    session_id: str,
    server_id: str,
    user: User = Depends(get_current_user),
) -> None:
    server_service.get_server_record(server_id, user.id)
    if not chat_history_service.delete_session(user.id, session_id, server_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session was not found.")


@router.post("/stream", status_code=status.HTTP_200_OK)
def chat_stream(payload: ChatRequest, user: User = Depends(get_current_user)) -> StreamingResponse:
    server_service.get_server_record(payload.server_id, user.id)
    analytics_reply = chat_count_reply(user.id, payload.message)
    if analytics_reply is not None:
        def analytics_events():
            yield json.dumps(AgentEvent(type="token", content=analytics_reply).as_payload()) + "\n"
            yield json.dumps(AgentEvent(type="done").as_payload()) + "\n"
        return StreamingResponse(analytics_events(), media_type="application/x-ndjson")
    restore_chat_session(payload, user.id)
    task_id = monitor_service.start_task(user.id, payload.session_id, payload.server_id, payload.message)
    def event_stream():
        reply_parts: list[str] = []
        try:
            for event in server_ops_agent.stream_turn(
                session_id=payload.session_id,
                server_id=payload.server_id,
                user_message=payload.message,
            ):
                monitor_service.record_event(task_id, event.as_payload())
                if event.type == "token":
                    reply_parts.append(event.content or "")
                yield json.dumps(event.as_payload()) + "\n"
        except (ServerNotFoundError, SSHConnectionError, ValueError, RuntimeError) as exc:
            monitor_service.fail_task(task_id, public_error_message(exc))
            yield json.dumps(AgentEvent(type="error", detail=public_error_message(exc), status_code=status_code_for_exception(exc)).as_payload()) + "\n"
        except Exception as exc:
            monitor_service.fail_task(task_id, public_error_message(exc))
            log_exception(logger, "chat stream", exc, {"session_id": payload.session_id, "server_id": payload.server_id})
            yield json.dumps(AgentEvent(type="error", detail=public_error_message(exc), status_code=status_code_for_exception(exc)).as_payload()) + "\n"
        else:
            monitor_service.complete_task(task_id)
            reply = "".join(reply_parts).strip()
            chat_history_service.append(user.id, payload.session_id, payload.server_id, "user", payload.message)
            chat_history_service.append(user.id, payload.session_id, payload.server_id, "assistant", reply)
            update_chat_title(user.id, payload)

    response = StreamingResponse(event_stream(), media_type="application/x-ndjson")
    response.headers["X-Agent-Task-ID"] = task_id
    return response
