from fastapi import APIRouter
from haystack.dataclasses import ChatMessage

from app.agents.orchestrator_agent import orchestrator_agent
from app.api.schemas.agent import AgentAskRequest, AgentAskResponse
from app.observability import langfuse_client

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/ask", response_model=AgentAskResponse)
async def ask_agent(payload: AgentAskRequest) -> AgentAskResponse:
    trace = langfuse_client.start_trace(
        "agent.ask",
        input={"question": payload.question, "top_k": payload.top_k},
        metadata={"endpoint": "/agent/ask"},
    )
    run_span = trace.span(
        "agent.workflow.ask",
        input={"question": payload.question, "top_k": payload.top_k},
    )
    try:
        result = orchestrator_agent.run(
            messages=[ChatMessage.from_user(payload.question)]
        )
        answer = ""
        replies = result.get("replies") if isinstance(result, dict) else None
        if isinstance(replies, list) and replies:
            first = replies[0]
            answer = str(
                getattr(first, "text", "") or getattr(first, "content", "") or ""
            )
        if not answer:
            answer = str(result)

        run_span.end(
            output={
                "capability": "orchestrator",
                "fallback_used": False,
                "evidence_count": 0,
            }
        )
        trace.end(
            output={
                "capability": "orchestrator",
                "fallback_used": False,
                "evidence_count": 0,
            }
        )
    except Exception as exc:
        run_span.end(output={"error": str(exc)})
        trace.end(output={"error": str(exc)})
        raise

    return AgentAskResponse(
        answer=answer,
        selected_capability="orchestrator",
        confidence=1.0,
        fallback_used=False,
        filters={},
        evidence=[],
        execution_trace=[],
    )
