FORMATTING_PROMPT = """Formatting rules for code blocks:

- For any CLI commands (Cisco, Arista, Juniper, Linux), use: bash
- For device configurations, use: bash
- If the language is unknown, use: plaintext
- NEVER create custom language tags (e.g. "arista-cli", "cisco-ios", etc.)
- When referring to a Bitbucket config diff that should be embedded inline, insert `[[CONFIG_DIFF]]`
  at the exact point in the markdown narrative where the diff viewer should appear.
"""
