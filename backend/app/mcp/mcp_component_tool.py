import logging
from typing import Any

from haystack.tools import ComponentTool

logger = logging.getLogger(__name__)


def _root_error_type(error: Exception) -> str:
    root: BaseException = error
    seen: set[int] = set()
    while root.__cause__ is not None and id(root) not in seen:
        seen.add(id(root))
        root = root.__cause__
    return type(root).__name__


class IsolatedMCPComponentTool(ComponentTool):
    """Delegate to an MCP-backed component without making it a global dependency.

    Haystack normally warms every ``ComponentTool`` recursively when its parent
    Agent warms up. For an MCP-backed nested Agent that would connect every MCP
    server before handling even an unrelated question. This tool deliberately
    defers nested warm-up until the component is actually invoked and converts
    invocation failures into a normal tool result for the parent Agent.
    """

    def warm_up(self) -> None:
        """Mark the delegation tool ready without warming its nested MCP Agent."""

        self._is_warmed_up = True

    def invoke(self, **kwargs: Any) -> Any:
        try:
            return super().invoke(**kwargs)
        except Exception as exc:
            error_type = _root_error_type(exc)
            logger.warning(
                "MCP specialist '%s' invocation failed (%s)",
                self.name,
                error_type,
            )
            return {
                "error": "mcp_specialist_unavailable",
                "specialist": self.name,
                "available": False,
                "retryable": True,
                "message": (
                    f"The {self.name} service is currently unavailable. "
                    "Continue with other specialists when they can answer the request."
                ),
                "error_type": error_type,
            }
