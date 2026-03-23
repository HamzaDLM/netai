from prometheus_client import Counter

LLM_REQUESTS_TOTAL = Counter(
    "llm_requests_total",
    "Total number of LLM requests.",
    ["provider", "model", "status"],
)

LLM_INPUT_TOKENS_TOTAL = Counter(
    "llm_input_tokens_total",
    "Total prompt/input tokens consumed by LLM calls.",
    ["provider", "model"],
)

LLM_OUTPUT_TOKENS_TOTAL = Counter(
    "llm_output_tokens_total",
    "Total completion/output tokens produced by LLM calls.",
    ["provider", "model"],
)

LLM_TOTAL_TOKENS_TOTAL = Counter(
    "llm_total_tokens_total",
    "Total tokens consumed by LLM calls.",
    ["provider", "model"],
)

LLM_COST_USD_TOTAL = Counter(
    "llm_cost_usd_total",
    "Estimated LLM token spend in USD.",
    ["provider", "model"],
)


def record_llm_request(
    *,
    provider: str,
    model: str,
    status: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    cost_usd: float = 0.0,
) -> None:
    safe_model = model or "unknown"
    LLM_REQUESTS_TOTAL.labels(
        provider=provider,
        model=safe_model,
        status=status,
    ).inc()

    if input_tokens > 0:
        LLM_INPUT_TOKENS_TOTAL.labels(provider=provider, model=safe_model).inc(
            input_tokens
        )
    if output_tokens > 0:
        LLM_OUTPUT_TOKENS_TOTAL.labels(provider=provider, model=safe_model).inc(
            output_tokens
        )
    if total_tokens > 0:
        LLM_TOTAL_TOKENS_TOTAL.labels(provider=provider, model=safe_model).inc(
            total_tokens
        )
    if cost_usd > 0:
        LLM_COST_USD_TOTAL.labels(provider=provider, model=safe_model).inc(cost_usd)
