from fastapi import APIRouter

from app.api.schemas.agent import AgentAskRequest, AgentAskResponse
from app.observability import langfuse_client
from app.workflows.agent_orchestrator import CapabilityRouter

router = APIRouter(prefix="/agent", tags=["agent"])
workflow = CapabilityRouter()


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
        result = await workflow.ask(payload.question, payload.top_k)
        run_span.end(
            output={
                "capability": result.selected_capability,
                "fallback_used": result.fallback_used,
                "evidence_count": len(result.evidence),
            }
        )
        trace.end(
            output={
                "capability": result.selected_capability,
                "fallback_used": result.fallback_used,
                "evidence_count": len(result.evidence),
            }
        )
    except Exception as exc:
        run_span.end(output={"error": str(exc)})
        trace.end(output={"error": str(exc)})
        raise

    return AgentAskResponse(
        answer=result.answer,
        selected_capability=result.selected_capability,
        confidence=result.confidence,
        fallback_used=result.fallback_used,
        filters=result.filters,
        evidence=result.evidence,
        execution_trace=result.execution_trace,
    )
