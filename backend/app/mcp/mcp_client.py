import logging

from haystack_integrations.tools.mcp import MCPTool, StreamableHttpServerInfo

logging.basicConfig(level=logging.WARNING)  # Set root logger to WARNING
mcp_logger = logging.getLogger("haystack_integrations.tools.mcp")
mcp_logger.setLevel(logging.DEBUG)

if not mcp_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    mcp_logger.addHandler(handler)
    mcp_logger.propagate = False  # Prevent propagation to root logger


def main():
    """Example of MCPTool usage with server connection."""

    server_info = StreamableHttpServerInfo(url="http://localhost:8030/mcp")
    tool = None
    tool_subtract = None
    try:
        tool = MCPTool(name="add", server_info=server_info)
        tool_subtract = MCPTool(name="subtract", server_info=server_info)

        result = tool.invoke(a=7, b=3)
        print(f"7 + 3 = {result}")

        result = tool_subtract.invoke(a=5, b=3)
        print(f"5 - 3 = {result}")

        result = tool.invoke(a=10, b=20)
        print(f"10 + 20 = {result}")

    except Exception as e:
        print(f"Error in client example: {e}")
    finally:
        if tool:
            tool.close()
        if tool_subtract:
            tool_subtract.close()


if __name__ == "__main__":
    main()
