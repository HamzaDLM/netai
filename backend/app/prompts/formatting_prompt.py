FORMATTING_PROMPT = """Formatting rules for code blocks:

- For any CLI commands (Cisco, Arista, Juniper, Linux), use: bash
- For Syslogs use: log
- For device configurations, use: bash
- If the language is unknown, use: plaintext
- NEVER create custom language tags (e.g. "arista-cli", "cisco-ios", etc.)
- Do not emit custom visual markers. Tool-backed visuals are inserted automatically at
  their exact position in the streamed response.
- When a tool creates a visual artifact, summarize its findings in prose without repeating
  the raw payload. In particular, do not repeat a unified configuration diff in a code block.
"""
