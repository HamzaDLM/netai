TITLE_GENERATION_PROMPT = """
You generate short titles for conversations.

Summarize the following conversation into a concise title.

Rules:
- Max 6 words
- No punctuation at the end
- No quotes
- No filler words (like "help with", "question about")
- Be specific

Conversation:
User: Explain TCP SYN and SYN-ACK in networking
Assistant: The TCP handshake starts with SYN...

Title:
"""
