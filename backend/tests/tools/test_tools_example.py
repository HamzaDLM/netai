from typing import Any

from app.tools.bitbucket_tools import list_bitbucket_devices


def _invoke_tool(tool_obj: Any, **kwargs: Any) -> Any:
    """Invoke a Haystack tool object in a version-tolerant way.

    Haystack tool invocation signatures can vary by version; this helper keeps the
    scaffold test stable while we decide on a single convention.
    """
    if not hasattr(tool_obj, "invoke"):
        raise AssertionError("Expected a tool object with an .invoke method")

    # Common shape: tool.invoke({"arg": value})
    try:
        return tool_obj.invoke(kwargs)
    except TypeError:
        pass

    # Alternate shape: tool.invoke(arg=value)
    try:
        return tool_obj.invoke(**kwargs)
    except TypeError:
        pass

    # Fallback: no-arg invoke for tools without inputs
    return tool_obj.invoke()


def test_example_invoke_tool_returns_error_payload() -> None:
    result = _invoke_tool(list_bitbucket_devices)

    assert isinstance(result, dict)
    assert "error" in result
    assert "bitbucket_list_devices_failed" in str(result["error"])
