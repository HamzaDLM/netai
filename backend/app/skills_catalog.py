import ast
from functools import lru_cache
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
AGENTS_DIR = APP_DIR / "agents"


def _first_line(text: str | None) -> str:
    if not text:
        return ""
    return text.strip().splitlines()[0].strip()


def _resolve_call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _extract_tool_names_from_list(node: ast.expr) -> list[str]:
    if not isinstance(node, ast.List):
        return []
    names: list[str] = []
    for elt in node.elts:
        if isinstance(elt, ast.Name):
            names.append(elt.id)
            continue
        if isinstance(elt, ast.Call):
            call_name = _resolve_call_name(elt.func)
            if call_name == "cast" and len(elt.args) >= 2:
                second = elt.args[1]
                if isinstance(second, ast.Name):
                    names.append(second.id)
                elif isinstance(second, ast.Call):
                    nested_name = _resolve_call_name(second.func)
                    if nested_name:
                        names.append(nested_name)
                continue
            inner_name = _resolve_call_name(elt.func)
            if inner_name:
                names.append(inner_name)
    return names


def _extract_component_tool_name(module_node: ast.Module) -> str | None:
    for node in module_node.body:
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            value = node.value
        if value is None:
            continue
        if not isinstance(value, ast.Call):
            continue
        if _resolve_call_name(value.func) != "ComponentTool":
            continue
        for keyword in value.keywords:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                if isinstance(keyword.value.value, str):
                    return keyword.value.value
    return None


def _extract_import_map(module_node: ast.Module) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for node in module_node.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.module or not node.module.startswith("app.tools"):
            continue
        for alias in node.names:
            imported_name = alias.asname or alias.name
            mapping[imported_name] = node.module
    return mapping


@lru_cache(maxsize=64)
def _load_tool_module_metadata(module_name: str) -> dict[str, dict[str, str | None]]:
    relative_path = Path(*module_name.split(".")).with_suffix(".py")
    module_path = APP_DIR.parent / relative_path
    if not module_path.exists():
        return {}

    module_node = ast.parse(module_path.read_text(encoding="utf-8"))
    metadata: dict[str, dict[str, str | None]] = {}

    for node in module_node.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        runtime_name: str | None = None
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            decorator_name = _resolve_call_name(decorator.func)
            if decorator_name not in {"netai_tool", "tool"}:
                continue
            for keyword in decorator.keywords:
                if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                    if isinstance(keyword.value.value, str):
                        runtime_name = keyword.value.value
        metadata[node.name] = {
            "summary": _first_line(ast.get_docstring(node)),
            "runtime_name": runtime_name,
        }

    return metadata


@lru_cache(maxsize=1)
def get_agent_tool_catalog() -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []

    for path in sorted(AGENTS_DIR.glob("*_agent.py")):
        if path.name == "orchestrator_agent.py":
            continue

        module_node = ast.parse(path.read_text(encoding="utf-8"))
        imports_map = _extract_import_map(module_node)

        tools: list[str] = []
        for node in module_node.body:
            value = None
            if isinstance(node, ast.Assign):
                if (
                    len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id.endswith("_tools")
                ):
                    value = node.value
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id.endswith(
                    "_tools"
                ):
                    value = node.value

            if value is None:
                continue
            tools = _extract_tool_names_from_list(value)
            break

        tool_entries: list[dict[str, str | None]] = []
        for tool_name in tools:
            module_name = imports_map.get(tool_name)
            module_meta = _load_tool_module_metadata(module_name) if module_name else {}
            tool_meta = module_meta.get(tool_name, {})
            tool_entries.append(
                {
                    "python_name": tool_name,
                    "runtime_name": tool_meta.get("runtime_name"),
                    "summary": tool_meta.get("summary") or "",
                }
            )

        agent_key = path.stem.replace("_agent", "")
        catalog.append(
            {
                "agent_key": agent_key,
                "agent_name": agent_key.replace("_", " ").title(),
                "specialist_tool": _extract_component_tool_name(module_node),
                "tools": tool_entries,
            }
        )

    return catalog
