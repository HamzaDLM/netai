import json
from dataclasses import dataclass

from haystack.utils import Secret

from app.core.config import project_settings
from app.monitoring import record_llm_request
from app.prompts.log_qa import LOG_QA_PROMPT
from app.retrieval import (
    EventRetriever,
    QdrantTemplateRetriever,
    parse_query_filters,
)


@dataclass(slots=True)
class QAResult:
    answer: str
    filters: dict
    evidence: list[dict]
    used_llm: bool


class LogQAWorkflow:
    def __init__(self) -> None:
        self.template_retriever = QdrantTemplateRetriever(
            base_url=project_settings.QDRANT_URL,
            collection=project_settings.QDRANT_COLLECTION,
        )
        self.event_retriever = EventRetriever()

    async def ask(self, question: str, top_k: int | None = None) -> QAResult:
        parsed = parse_query_filters(question)
        effective_top_k = top_k or project_settings.LOG_QA_TOP_K
        event_top_k = max(effective_top_k, project_settings.LOG_QA_EVENT_TOP_K)

        event_hits = await self.event_retriever.retrieve(
            query=question,
            ips=parsed.ips,
            hostnames=parsed.hostnames,
            top_k=event_top_k,
        )
        template_hits = await self.template_retriever.retrieve(
            query=question,
            top_k=effective_top_k,
        )

        evidence = [
            {"source": e.source, "content": e.content, "score": e.score}
            for e in [*event_hits, *template_hits]
        ]
        evidence = sorted(evidence, key=lambda e: e["score"], reverse=True)[
            :effective_top_k
        ]

        answer, used_llm = self._generate_answer(
            question=question,
            filters={"ips": parsed.ips, "hostnames": parsed.hostnames},
            evidence=evidence,
        )

        return QAResult(
            answer=answer,
            filters={"ips": parsed.ips, "hostnames": parsed.hostnames},
            evidence=evidence,
            used_llm=used_llm,
        )

    def _generate_answer(
        self, *, question: str, filters: dict, evidence: list[dict]
    ) -> tuple[str, bool]:
        if not evidence:
            return (
                "I could not find matching evidence in ClickHouse events or Qdrant templates for this query and lookback window.",
                False,
            )

        provider = project_settings.LOG_QA_PROVIDER.lower().strip()
        if provider == "gemini":
            return self._generate_with_gemini(
                question=question, filters=filters, evidence=evidence
            )
        if provider == "openai":
            return self._generate_with_openai(
                question=question, filters=filters, evidence=evidence
            )

        return (
            f"Unsupported LOG_QA_PROVIDER='{project_settings.LOG_QA_PROVIDER}'. Use 'gemini' or 'openai'.",
            False,
        )

    def _generate_with_openai(
        self, *, question: str, filters: dict, evidence: list[dict]
    ) -> tuple[str, bool]:
        provider = "openai"
        model = project_settings.LOG_QA_MODEL
        if not project_settings.OPENAI_API_KEY:
            record_llm_request(provider=provider, model=model, status="no_api_key")
            return self._format_non_llm_fallback(
                "LLM provider is OpenAI but OPENAI_API_KEY is not configured.",
                evidence,
            )

        try:
            from haystack import Pipeline
            from haystack.components.builders import PromptBuilder
            from haystack.components.generators import OpenAIGenerator
            from haystack.dataclasses import Document

            documents = [
                Document(
                    content=e["content"],
                    meta={"source": e["source"], "score": e["score"]},
                )
                for e in evidence
            ]
            pipeline = Pipeline()
            pipeline.add_component(
                "prompt_builder", PromptBuilder(template=LOG_QA_PROMPT)
            )
            pipeline.add_component(
                "llm",
                OpenAIGenerator(
                    api_key=Secret.from_token(project_settings.OPENAI_API_KEY),
                    model=project_settings.LOG_QA_MODEL,
                ),
            )
            pipeline.connect("prompt_builder", "llm")
            out = pipeline.run(
                {
                    "prompt_builder": {
                        "question": question,
                        "filters_json": json.dumps(filters),
                        "documents": documents,
                    }
                }
            )
            replies = out.get("llm", {}).get("replies", [])
            usage = self._extract_token_usage(out.get("llm", {}))
            input_tokens = usage["input_tokens"]
            output_tokens = usage["output_tokens"]
            total_tokens = usage["total_tokens"]
            cost_usd = self._estimate_cost_usd(
                provider=provider,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            record_llm_request(
                provider=provider,
                model=model,
                status="success" if replies else "empty_reply",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
            )
            if replies:
                return (str(replies[0]).strip(), True)
        except Exception as exc:
            record_llm_request(provider=provider, model=model, status="error")
            return (f"Failed to generate OpenAI answer: {exc}", False)

        return ("No OpenAI reply generated.", False)

    def _generate_with_gemini(
        self, *, question: str, filters: dict, evidence: list[dict]
    ) -> tuple[str, bool]:
        api_key = project_settings.GEMINI_API_KEY
        provider = "gemini"
        model = project_settings.LOG_QA_MODEL
        if not api_key:
            record_llm_request(provider=provider, model=model, status="no_api_key")
            return self._format_non_llm_fallback(
                "LLM provider is Gemini but GEMINI_API_KEY is not configured.",
                evidence,
            )

        try:
            from haystack.dataclasses import ChatMessage
            from haystack_integrations.components.generators.google_genai import (
                GoogleGenAIChatGenerator,
            )

            prompt = self._render_flat_prompt(
                question=question, filters=filters, evidence=evidence
            )
            generator = GoogleGenAIChatGenerator(
                api_key=Secret.from_token(api_key),
                model=project_settings.LOG_QA_MODEL,
            )
            out = generator.run(messages=[ChatMessage.from_user(prompt)])
            replies = out.get("replies", [])
            usage = self._extract_token_usage(out)
            input_tokens = usage["input_tokens"]
            output_tokens = usage["output_tokens"]
            total_tokens = usage["total_tokens"]
            cost_usd = self._estimate_cost_usd(
                provider=provider,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            record_llm_request(
                provider=provider,
                model=model,
                status="success" if replies else "empty_reply",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
            )
            if replies:
                first = replies[0]
                text = getattr(first, "text", None)
                return ((text if text else str(first)).strip(), True)
        except Exception as exc:
            record_llm_request(provider=provider, model=model, status="error")
            return (f"Failed to generate Gemini answer: {exc}", False)

        return ("No Gemini reply generated.", False)

    def _format_non_llm_fallback(
        self, title: str, evidence: list[dict]
    ) -> tuple[str, bool]:
        lines = [title, "Top evidence:"]
        for idx, ev in enumerate(evidence[:5], start=1):
            lines.append(f"{idx}. [{ev['source']}] {ev['content']}")
        return ("\n".join(lines), False)

    def _render_flat_prompt(
        self, *, question: str, filters: dict, evidence: list[dict]
    ) -> str:
        evidence_lines = "\n".join(
            [f"[{idx}] {ev['content']}" for idx, ev in enumerate(evidence, start=1)]
        )
        return (
            f"{LOG_QA_PROMPT}\n\n"
            f"Question:\n{question}\n\n"
            f"Parsed filters:\n{json.dumps(filters)}\n\n"
            f"Evidence:\n{evidence_lines}\n"
        )

    def _extract_token_usage(self, payload: dict) -> dict[str, int]:
        usage = {}
        if isinstance(payload, dict):
            direct = payload.get("usage")
            if isinstance(direct, dict):
                usage = direct
            if not usage:
                replies = payload.get("replies")
                if isinstance(replies, list):
                    for reply in replies:
                        meta = None
                        if isinstance(reply, dict):
                            meta = reply.get("meta") or reply.get("_meta")
                        else:
                            meta = getattr(reply, "meta", None) or getattr(
                                reply, "_meta", None
                            )
                        if isinstance(meta, dict) and isinstance(
                            meta.get("usage"), dict
                        ):
                            usage = meta["usage"]
                            break
            if not usage:
                meta = payload.get("meta")
                if isinstance(meta, list):
                    for item in meta:
                        if isinstance(item, dict) and isinstance(
                            item.get("usage"), dict
                        ):
                            usage = item["usage"]
                            break
                elif isinstance(meta, dict) and isinstance(meta.get("usage"), dict):
                    usage = meta["usage"]

        input_tokens = int(
            usage.get("prompt_tokens")
            or usage.get("input_tokens")
            or usage.get("prompt_token_count")
            or usage.get("inputTokenCount")
            or 0
        )
        output_tokens = int(
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or usage.get("candidates_token_count")
            or usage.get("candidatesTokenCount")
            or 0
        )
        total_tokens = int(
            usage.get("total_tokens")
            or usage.get("total_token_count")
            or (input_tokens + output_tokens)
        )

        return {
            "input_tokens": max(input_tokens, 0),
            "output_tokens": max(output_tokens, 0),
            "total_tokens": max(total_tokens, 0),
        }

    def _estimate_cost_usd(
        self, *, provider: str, input_tokens: int, output_tokens: int
    ) -> float:
        if provider == "openai":
            input_rate = project_settings.OPENAI_INPUT_COST_PER_1M_TOKENS
            output_rate = project_settings.OPENAI_OUTPUT_COST_PER_1M_TOKENS
        else:
            input_rate = project_settings.GEMINI_INPUT_COST_PER_1M_TOKENS
            output_rate = project_settings.GEMINI_OUTPUT_COST_PER_1M_TOKENS

        return (input_tokens / 1_000_000.0) * input_rate + (
            output_tokens / 1_000_000.0
        ) * output_rate
