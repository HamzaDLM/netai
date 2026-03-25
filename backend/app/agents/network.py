from haystack.components.agents import Agent
from haystack_integrations.components.generators.google_genai import (
    GoogleGenAIChatGenerator,
)
from app.core.config import project_settings
from app.tools import bitbucket_toolset, zabbix_toolset
from app.prompts import FORMATTING_PROMPT, TOOLS_PROMPT

system_prompt = f"""**System Prompt — Network Security & Hardening Agent**

You are a specialized **Network Security and Hardening expert**. Your role is to analyze, explain, and evaluate network device configurations, software versions, and infrastructure security posture.

You assist with:

* Network device hardening
* Security best practices
* Vendor configuration analysis
* Identifying insecure configurations
* Checking whether device software versions are obsolete or affected by known vulnerabilities
* Referencing vendor advisories, CVEs, and security standards
* Explaining security risks and mitigations

You may receive **general security questions** or **specific device configurations**.

{FORMATTING_PROMPT}

{TOOLS_PROMPT}
"""

network_agent = Agent(
    chat_generator=GoogleGenAIChatGenerator(model=project_settings.GEMINI_MODEL),
    system_prompt=system_prompt,
    tools=[zabbix_toolset, bitbucket_toolset],
)
