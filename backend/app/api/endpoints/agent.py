from fastapi import APIRouter
from haystack.dataclasses import ChatMessage

from app.api.deps import CheckUserSSODep, NetAIServiceDep, RequestIDDep
from app.api.schemas.agent import AgentAskRequest, AgentAskResponse

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/ask", response_model=AgentAskResponse)
async def ask_agent(
    payload: AgentAskRequest,
    service: NetAIServiceDep,
    request_id: RequestIDDep,
    user: CheckUserSSODep,
) -> AgentAskResponse:
    run = await service.run(
        messages=[ChatMessage.from_user(payload.question)],
        conversation_id=f"agent:{request_id}",
        user_id=user.id,
        request_id=request_id,
    )
    return AgentAskResponse(
        answer=run.answer,
        selected_capability="netai",
        confidence=1.0,
        fallback_used=False,
        filters={},
        evidence=[],
        execution_trace=[
            execution.tool_name
            for execution in run.observer.tool_executions
            if execution.connector != "internal"
        ],
    )
