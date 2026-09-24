"""E-08..E-13 /v1/conversations (docs/02_api_spec.md section 7.1)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import JSONResponse

from app.api.auth import recommend_rate_limit, require_scopes
from app.api.deps import get_conversation_service, get_current_user
from app.api.idempotency import IdempotentRoute
from app.api.v1.responses import accepted_response, json_response
from app.core.ids import current_correlation_id, current_request_id, new_id
from app.core.security import Scope
from app.schemas.v1.conversations import (
    ConversationCreate,
    ConversationPage,
    ConversationResponse,
    MessageCreate,
    MessagePage,
    MessageResponse,
)
from app.schemas.v1.travel import JobAccepted
from app.services.conversation_service import ConversationService
from app.services.ports import UserRef
from app.services.recommendation_service import Accepted

router = APIRouter(prefix="/conversations", tags=["conversations"], route_class=IdempotentRoute)

_READ = [Depends(require_scopes(Scope.TRAVEL_READ))]
# Creating conversations and messages shares the recommendation limit (P-32).
_WRITE = [Depends(require_scopes(Scope.TRAVEL_WRITE)), Depends(recommend_rate_limit)]

CursorQuery = Query(default=None, max_length=200)


@router.post(
    "",
    summary="Start a conversation",
    status_code=201,
    response_model=ConversationResponse,
    dependencies=_WRITE,
)
async def create_conversation(
    body: ConversationCreate,
    response: Response,
    accept_language: str | None = Header(default=None, max_length=200),
    user: UserRef = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> JSONResponse:
    created = await service.create(
        user, title=body.title, language=body.language, accept_language=accept_language
    )
    return json_response(
        ConversationResponse.from_record(created),
        201,
        response,
        location=f"/v1/conversations/{created.id}",
    )


@router.get("", summary="List conversations", response_model=ConversationPage, dependencies=_READ)
async def list_conversations(
    limit: int | None = Query(default=None),
    cursor: str | None = CursorQuery,
    user: UserRef = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationPage:
    page = await service.list(user, limit=limit, cursor=cursor)
    return ConversationPage(
        items=[ConversationResponse.from_record(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{conversation_id}",
    summary="Get a conversation",
    response_model=ConversationResponse,
    dependencies=_READ,
)
async def get_conversation(
    conversation_id: UUID,
    user: UserRef = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationResponse:
    return ConversationResponse.from_record(await service.get(user, conversation_id))


@router.delete(
    "/{conversation_id}",
    summary="Delete a conversation and its messages",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(require_scopes(Scope.TRAVEL_WRITE))],
)
async def delete_conversation(
    conversation_id: UUID,
    user: UserRef = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> Response:
    await service.delete(user, conversation_id)
    return Response(status_code=204)


@router.get(
    "/{conversation_id}/messages",
    summary="Messages, newest first",
    response_model=MessagePage,
    dependencies=_READ,
)
async def list_messages(
    conversation_id: UUID,
    limit: int | None = Query(default=None),
    cursor: str | None = CursorQuery,
    user: UserRef = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> MessagePage:
    page = await service.messages(user, conversation_id, limit=limit, cursor=cursor)
    return MessagePage(
        items=[MessageResponse.from_record(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.post(
    "/{conversation_id}/messages",
    summary="Ask a (follow-up) question",
    response_model=MessageResponse,
    responses={202: {"model": JobAccepted, "description": "Still running; follow the job"}},
    dependencies=_WRITE,
)
async def post_message(
    conversation_id: UUID,
    body: MessageCreate,
    response: Response,
    accept_language: str | None = Header(default=None, max_length=200),
    user: UserRef = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> JSONResponse:
    outcome = await service.post_message(
        user,
        conversation_id,
        content=body.content,
        overrides=body.overrides.to_domain(),
        stream=body.stream,
        accept_language=accept_language,
        correlation_id=current_correlation_id() or current_request_id() or str(new_id()),
    )
    if isinstance(outcome, Accepted):
        return accepted_response(outcome, response)
    return json_response(MessageResponse.from_record(outcome.message), 200, response)
