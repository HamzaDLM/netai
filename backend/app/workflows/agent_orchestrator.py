import json
from dataclasses import dataclass

from haystack.utils import Secret

from app.core.config import project_settings
from app.monitoring import record_llm_request
from app.workflows.log_qa import LogQAWorkflow


@dataclass(slots=True)
class AgentResult:
    answer: str
    selected_capability: str
    confidence: float
    fallback_used: bool
    filters: dict
    evidence: list[dict]
    execution_trace: list[str]


@dataclass(slots=True)
class RouteDecision:
    capability: str
    confidence: float
    reason: str
    source: str


class Capability:
    name = "base"

    async def run(self, question: str, top_k: int | None = None) -> AgentResult:
        raise NotImplementedError


class LogQACapability(Capability):
    name = "log_qa"

    def __init__(self) -> None:
        self.workflow = LogQAWorkflow()

    async def run(self, question: str, top_k: int | None = None) -> AgentResult:
        result = await self.workflow.ask(question=question, top_k=top_k)
        return AgentResult(
            answer=result.answer,
            selected_capability=self.name,
            confidence=1.0,
            fallback_used=False,
            filters=result.filters,
            evidence=result.evidence,
            execution_trace=[f"executed:{self.name}"],
        )


class ZabbixCapability(Capability):
    name = "zabbix"

    async def run(self, question: str, top_k: int | None = None) -> AgentResult:
        _ = top_k
        return AgentResult(
            answer=(
                "Zabbix capability was selected, but concrete Zabbix API integration is not wired yet. "
                "I can still answer from log evidence via log_qa if you want."
            ),
            selected_capability=self.name,
            confidence=1.0,
            fallback_used=False,
            filters={},
            evidence=[],
            execution_trace=[f"executed:{self.name}", "zabbix_api:not_implemented"],
        )


class BitbucketCapability(Capability):
    name = "bitbucket"

    async def run(self, question: str, top_k: int | None = None) -> AgentResult:
        _ = (question, top_k)
        return AgentResult(
            answer=(
                "Bitbucket capability was selected, but repository API integration is not wired yet. "
                "I can route to log_qa for infrastructure/log questions."
            ),
            selected_capability=self.name,
            confidence=1.0,
            fallback_used=False,
            filters={},
            evidence=[],
            execution_trace=[f"executed:{self.name}", "bitbucket_api:not_implemented"],
        )


class CapabilityRouter:
    _ZABBIX_KEYWORDS = {
        "zabbix",
        "trigger",
        "host status",
        "problem event",
        "monitoring alert",
    }
    _BITBUCKET_KEYWORDS = {
        "bitbucket",
        "pull request",
        "pr ",
        "repo",
        "repository",
        "branch",
        "commit",
        "pipeline",
    }
    _LOG_KEYWORDS = {
        "log",
        "syslog",
        "error",
        "trace",
        "event",
        "incident",
    }

    def __init__(self) -> None:
        self.capabilities: dict[str, Capability] = {
            "log_qa": LogQACapability(),
            "zabbix": ZabbixCapability(),
            "bitbucket": BitbucketCapability(),
        }

    async def ask(self, question: str, top_k: int | None = None) -> AgentResult:
        trace: list[str] = []
        decision = self._route_with_rules(question=question)
        trace.append(
            f"route:source={decision.source};capability={decision.capability};confidence={decision.confidence:.2f}"
        )

        threshold = project_settings.AGENT_ROUTER_CONFIDENCE_THRESHOLD
        if (
            decision.source == "rules"
            and decision.confidence < threshold
            and project_settings.AGENT_ROUTER_ENABLE_LLM
        ):
            llm_decision = await self._route_with_llm(question=question)
            if llm_decision:
                decision = llm_decision
                trace.append(
                    f"route:source={decision.source};capability={decision.capability};confidence={decision.confidence:.2f}"
                )

        fallback_used = False
        if (
            decision.capability not in self.capabilities
            or decision.confidence < threshold
        ):
            decision = RouteDecision(
                capability="log_qa",
                confidence=max(decision.confidence, 0.5),
                reason="fallback_to_default_log_qa",
                source="fallback",
            )
            fallback_used = True
            trace.append("route:fallback=log_qa")
        elif decision.capability == "zabbix" and not project_settings.ZABBIX_ENABLED:
            decision = RouteDecision(
                capability="log_qa",
                confidence=max(decision.confidence, 0.6),
                reason="zabbix_disabled_fallback_to_log_qa",
                source="fallback",
            )
            fallback_used = True
            trace.append("route:fallback=zabbix_disabled->log_qa")
        elif (
            decision.capability == "bitbucket"
            and not project_settings.BITBUCKET_ENABLED
        ):
            decision = RouteDecision(
                capability="log_qa",
                confidence=max(decision.confidence, 0.6),
                reason="bitbucket_disabled_fallback_to_log_qa",
                source="fallback",
            )
            fallback_used = True
            trace.append("route:fallback=bitbucket_disabled->log_qa")

        result = await self.capabilities[decision.capability].run(question, top_k)
        result.selected_capability = decision.capability
        result.confidence = decision.confidence
        result.fallback_used = fallback_used
        result.execution_trace = [*trace, *result.execution_trace]
        return result

    def _route_with_rules(self, *, question: str) -> RouteDecision:
        lowered = f" {question.lower().strip()} "

        zabbix_matches = sum(1 for k in self._ZABBIX_KEYWORDS if k in lowered)
        bitbucket_matches = sum(1 for k in self._BITBUCKET_KEYWORDS if k in lowered)
        log_matches = sum(1 for k in self._LOG_KEYWORDS if k in lowered)

        if zabbix_matches > max(bitbucket_matches, log_matches):
            return RouteDecision(
                capability="zabbix",
                confidence=min(0.55 + 0.1 * zabbix_matches, 0.9),
                reason="matched_zabbix_keywords",
                source="rules",
            )
        if bitbucket_matches > max(zabbix_matches, log_matches):
            return RouteDecision(
                capability="bitbucket",
                confidence=min(0.55 + 0.1 * bitbucket_matches, 0.9),
                reason="matched_bitbucket_keywords",
                source="rules",
            )
        if log_matches > 0:
            return RouteDecision(
                capability="log_qa",
                confidence=min(0.6 + 0.05 * log_matches, 0.9),
                reason="matched_log_keywords",
                source="rules",
            )
        return RouteDecision(
            capability="log_qa",
            confidence=0.4,
            reason="default_log_qa_low_confidence",
            source="rules",
        )

    async def _route_with_llm(self, *, question: str) -> RouteDecision | None:
        provider = project_settings.LOG_QA_PROVIDER.lower().strip()
        if provider == "gemini":
            return await self._route_with_gemini(question=question)
        if provider == "openai":
            return await self._route_with_openai(question=question)
        return None

    async def _route_with_openai(self, *, question: str) -> RouteDecision | None:
        provider = "openai"
        model = project_settings.AGENT_ROUTER_MODEL or project_settings.LOG_QA_MODEL
        if not project_settings.OPENAI_API_KEY:
            record_llm_request(provider=provider, model=model, status="no_api_key")
            return None

        try:
            from haystack import Pipeline
            from haystack.components.builders import PromptBuilder
            from haystack.components.generators import OpenAIGenerator

            prompt_template = (
                "Classify the question into one capability: log_qa, zabbix, bitbucket.\n"
                "Return strict JSON with keys capability, confidence, reason.\n"
                "Question: {{question}}"
            )
            pipeline = Pipeline()
            pipeline.add_component(
                "prompt_builder", PromptBuilder(template=prompt_template)
            )
            pipeline.add_component(
                "llm",
                OpenAIGenerator(
                    api_key=Secret.from_token(project_settings.OPENAI_API_KEY),
                    model=model,
                ),
            )
            pipeline.connect("prompt_builder", "llm")
            out = pipeline.run({"prompt_builder": {"question": question}})
            replies = out.get("llm", {}).get("replies", [])
            record_llm_request(
                provider=provider,
                model=model,
                status="success" if replies else "empty_reply",
            )
            if not replies:
                return None
            return self._parse_llm_decision(str(replies[0]), source="llm_openai")
        except Exception:
            record_llm_request(provider=provider, model=model, status="error")
            return None

    async def _route_with_gemini(self, *, question: str) -> RouteDecision | None:
        provider = "gemini"
        model = project_settings.AGENT_ROUTER_MODEL or project_settings.LOG_QA_MODEL
        if not project_settings.GEMINI_API_KEY:
            record_llm_request(provider=provider, model=model, status="no_api_key")
            return None

        try:
            from haystack.dataclasses import ChatMessage
            from haystack_integrations.components.generators.google_genai import (
                GoogleGenAIChatGenerator,
            )

            prompt = (
                "Classify the question into one capability: log_qa, zabbix, bitbucket.\n"
                "Return strict JSON with keys capability, confidence, reason.\n"
                f"Question: {question}"
            )
            generator = GoogleGenAIChatGenerator(
                api_key=Secret.from_token(project_settings.GEMINI_API_KEY),
                model=model,
            )
            out = generator.run(messages=[ChatMessage.from_user(prompt)])
            replies = out.get("replies", [])
            record_llm_request(
                provider=provider,
                model=model,
                status="success" if replies else "empty_reply",
            )
            if not replies:
                return None
            first = replies[0]
            text = getattr(first, "text", None)
            return self._parse_llm_decision(
                (text if text else str(first)),
                source="llm_gemini",
            )
        except Exception:
            record_llm_request(provider=provider, model=model, status="error")
            return None

    def _parse_llm_decision(self, raw: str, *, source: str) -> RouteDecision | None:
        raw = raw.strip()
        try:
            payload = json.loads(raw)
        except Exception:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                try:
                    payload = json.loads(raw[start : end + 1])
                except Exception:
                    return None
            else:
                return None

        capability = str(payload.get("capability", "")).strip().lower()
        if capability not in {"log_qa", "zabbix", "bitbucket"}:
            return None
        try:
            confidence = float(payload.get("confidence", 0.5))
        except Exception:
            confidence = 0.5
        reason = str(payload.get("reason", "llm_classification"))
        return RouteDecision(
            capability=capability,
            confidence=max(0.0, min(confidence, 1.0)),
            reason=reason,
            source=source,
        )
