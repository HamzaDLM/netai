from fastapi import APIRouter

from app.api.schemas.logs import LogAskRequest, LogAskResponse
from app.observability import langfuse_client
from app.workflows.log_qa import LogQAWorkflow

router = APIRouter(prefix="/logs", tags=["logs"])
workflow = LogQAWorkflow()


@router.post("/ask", response_model=LogAskResponse)
async def ask_logs(payload: LogAskRequest) -> LogAskResponse:
    trace = langfuse_client.start_trace(
        "logs.ask",
        input={"question": payload.question, "top_k": payload.top_k},
        metadata={"endpoint": "/logs/ask"},
    )
    run_span = trace.span(
        "logs.workflow.ask",
        input={"question": payload.question, "top_k": payload.top_k},
    )
    try:
        result = await workflow.ask(payload.question, payload.top_k)
        run_span.end(
            output={
                "used_llm": result.used_llm,
                "evidence_count": len(result.evidence),
            }
        )
        trace.end(
            output={
                "used_llm": result.used_llm,
                "evidence_count": len(result.evidence),
            }
        )
    except Exception as exc:
        run_span.end(output={"error": str(exc)})
        trace.end(output={"error": str(exc)})
        raise

    return LogAskResponse(
        answer=result.answer,
        filters=result.filters,
        evidence=result.evidence,
        used_llm=result.used_llm,
    )
