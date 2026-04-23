from typing import cast

from haystack.components.agents import Agent
from haystack.tools import ComponentTool, Tool

from app.core.config import project_settings
from app.llm import llm

if project_settings.TOOLS_USE_MOCK_DATA:
    from app.tools._bitbucket_tools_mock import (
        bitbucket_device_config_exists,
        get_bitbucket_device_configuration,
        get_bitbucket_device_file_info,
        get_bitbucket_recent_commits,
        get_recent_device_config_diff,
    )
else:
    from app.tools.bitbucket_tools import (
        bitbucket_device_config_exists,
        get_bitbucket_device_configuration,
        get_bitbucket_device_file_info,
        get_bitbucket_recent_commits,
        get_recent_device_config_diff,
    )

BITBUCKET_SPECIALIST_PROMPT = """
You are a Bitbucket specialist agent.

Use Bitbucket tools to inspect repositories, commits, and device configuration artifacts.
Answer with evidence from tool output and keep responses concise.
"""

bitbucket_tools: list[Tool] = [
    cast(Tool, bitbucket_device_config_exists),
    cast(Tool, get_bitbucket_device_file_info),
    cast(Tool, get_recent_device_config_diff),
    cast(Tool, get_bitbucket_device_configuration),
    cast(Tool, get_bitbucket_recent_commits),
]

bitbucket_agent = Agent(
    chat_generator=llm,
    system_prompt=BITBUCKET_SPECIALIST_PROMPT,
    tools=bitbucket_tools,
    max_agent_steps=10,
)

bitbucket_specialist_tool = ComponentTool(
    component=bitbucket_agent,
    name="bitbucket_specialist",
    description=(
        "Configuration history specialist. Use for repository/device config lookups, "
        "file diffs, commit timelines, and change provenance in Bitbucket."
    ),
)
