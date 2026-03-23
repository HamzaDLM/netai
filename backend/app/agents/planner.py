from haystack.components.agents import Agent
from haystack_integrations.components.generators.google_genai import (
    GoogleGenAIChatGenerator,
)

from app.core.config import project_settings

prompt = """
You are a router agent that specializes in Network Engineering, your task is to recognize from the user's request,
which tools to use to gather information needed to answer the question.

The tools at your desposal are the following:

- syslog_fetcher
- zabbix_fetcher
- easynet_fetcher (source of truth for devices informations and attributes)
- bitbucket_fetcher (can retrieve device configurations and differences in configurations and last change times)
- device_show_command (can execute show commands on the target device to retrieve information)

Only list the tools that you're gonna use and give the rational behind it, don't do anything else. 

Respect the following format when answering:

- tool_name: rationale description
"""


planner_agent = Agent(
    chat_generator=GoogleGenAIChatGenerator(model=project_settings.GEMINI_MODEL),
    system_prompt=prompt,
    tools=[],
)
