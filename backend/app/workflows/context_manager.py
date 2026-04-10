import asyncio
from dataclasses import dataclass

from haystack.dataclasses import ChatMessage
from sqlalchemy import select, update

from app.llm import llm
from app.api.models.chat import ConversationSummary, Message, MessageRole
from app.core.config import project_settings
from app.db.session import SessionLocal
from app.prompts import SUMMARIZING_PROMPT

RECENT_MESSAGE_WINDOW = 10
COMPACTION_THRESHOLD_RATIO = 0.8


@dataclass(slots=True)
class BuiltContext:
    messages: list[ChatMessage]
    estimated_tokens: int
    used_summary_id: int | None
    compacted: bool
    context_window: int
    used_percent: int
    left_tokens: int
    left_percent: int

    def metrics(self) -> dict[str, int | bool | None]:
        return {
            "context_window": self.context_window,
            "used_tokens": self.estimated_tokens,
            "used_percent": self.used_percent,
            "left_tokens": self.left_tokens,
            "left_percent": self.left_percent,
            "compacted": self.compacted,
            "summary_id": self.used_summary_id,
        }


def _estimate_tokens(messages: list[ChatMessage]) -> int:
    # Lightweight heuristic (~4 chars/token) suitable for preflight budget checks.
    text = "\n".join(getattr(message, "text", "") or "" for message in messages)
    return max(1, len(text) // 4)


def _to_chat_message(message: Message) -> ChatMessage:
    role = (
        message.role.value
        if isinstance(message.role, MessageRole)
        else str(message.role)
    )
    if role == MessageRole.assistant.value:
        return ChatMessage.from_assistant(message.content)
    if role == MessageRole.system.value:
        return ChatMessage.from_system(message.content)
    return ChatMessage.from_user(message.content)


def _format_messages_for_summary(messages: list[Message]) -> str:
    lines: list[str] = []
    for message in messages:
        # Never summarize system prompts/messages.
        if message.role == MessageRole.system:
            continue
        lines.append(f"[{message.id}] {message.role.value}: {message.content}")
    return "\n".join(lines).strip()


async def _latest_summary(*, conversation_id: int) -> ConversationSummary | None:
    async with SessionLocal() as db:
        stmt = (
            select(ConversationSummary)
            .where(ConversationSummary.conversation_id == conversation_id)
            .order_by(ConversationSummary.id.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


async def _recent_messages_after_summary(
    *, conversation_id: int, up_to_message_id: int | None
) -> list[Message]:
    async with SessionLocal() as db:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .where(Message.archived.is_(False))
            .where(Message.role != MessageRole.system)
            .order_by(Message.id.asc())
        )
        if up_to_message_id is not None:
            stmt = stmt.where(Message.id > up_to_message_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())


async def compact_conversation_context(
    *,
    conversation_id: int,
    keep_recent: int = RECENT_MESSAGE_WINDOW,
) -> bool:
    async with SessionLocal() as db:
        latest_summary_stmt = (
            select(ConversationSummary)
            .where(ConversationSummary.conversation_id == conversation_id)
            .order_by(ConversationSummary.id.desc())
            .limit(1)
        )
        latest_summary = (await db.execute(latest_summary_stmt)).scalar_one_or_none()
        prev_up_to = latest_summary.up_to_message_id if latest_summary else 0

        recent_stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .where(Message.archived.is_(False))
            .where(Message.role != MessageRole.system)
            .order_by(Message.id.asc())
        )
        all_active_messages = list((await db.execute(recent_stmt)).scalars().all())
        if len(all_active_messages) <= keep_recent:
            return False

        cutoff_message_id = all_active_messages[-keep_recent - 1].id

        summarize_stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .where(Message.archived.is_(False))
            .where(Message.role != MessageRole.system)
            .where(Message.id <= cutoff_message_id)
            .where(Message.id > prev_up_to)
            .order_by(Message.id.asc())
        )
        to_summarize = list((await db.execute(summarize_stmt)).scalars().all())
        if not to_summarize:
            return False

        messages_text = _format_messages_for_summary(to_summarize)
        if not messages_text:
            return False

        if latest_summary:
            user_prompt = (
                "Previous summary:\n"
                f"{latest_summary.content}\n\n"
                "New messages:\n"
                f"{messages_text}\n\n"
                "Update the summary to reflect the full conversation so far."
            )
        else:
            user_prompt = "Summarize the following conversation:\n" f"{messages_text}"

        llm_result = await asyncio.to_thread(
            llm.run,
            messages=[
                ChatMessage.from_system(SUMMARIZING_PROMPT),
                ChatMessage.from_user(user_prompt),
            ],
        )
        summary_content = llm_result["replies"][0].text.strip()
        if not summary_content:
            return False

        db.add(
            ConversationSummary(
                conversation_id=conversation_id,
                content=summary_content,
                up_to_message_id=cutoff_message_id,
            )
        )
        await db.execute(
            update(Message)
            .where(Message.conversation_id == conversation_id)
            .where(Message.id <= cutoff_message_id)
            .values(archived=True)
        )
        await db.commit()
        return True


async def build_conversation_context(
    *,
    conversation_id: int,
    keep_recent: int = RECENT_MESSAGE_WINDOW,
) -> BuiltContext:
    context_limit = project_settings.LLM_CONTEXT_WINDOW
    limit_threshold = int(context_limit * COMPACTION_THRESHOLD_RATIO)

    latest_summary = await _latest_summary(conversation_id=conversation_id)
    recent_messages = await _recent_messages_after_summary(
        conversation_id=conversation_id,
        up_to_message_id=latest_summary.up_to_message_id if latest_summary else None,
    )

    prompt_messages: list[ChatMessage] = []
    if latest_summary:
        prompt_messages.append(
            ChatMessage.from_system(
                "Conversation summary (do not repeat verbatim; use as prior context):\n"
                f"{latest_summary.content}"
            )
        )

    tail = recent_messages[-keep_recent:] if keep_recent > 0 else recent_messages
    prompt_messages.extend(_to_chat_message(message) for message in tail)

    estimated_tokens = _estimate_tokens(prompt_messages)
    compacted = False
    if estimated_tokens > limit_threshold:
        compacted = await compact_conversation_context(
            conversation_id=conversation_id,
            keep_recent=keep_recent,
        )
        if compacted:
            latest_summary = await _latest_summary(conversation_id=conversation_id)
            recent_messages = await _recent_messages_after_summary(
                conversation_id=conversation_id,
                up_to_message_id=(
                    latest_summary.up_to_message_id if latest_summary else None
                ),
            )
            prompt_messages = []
            if latest_summary:
                prompt_messages.append(
                    ChatMessage.from_system(
                        "Conversation summary (do not repeat verbatim; use as prior context):\n"
                        f"{latest_summary.content}"
                    )
                )
            tail = (
                recent_messages[-keep_recent:] if keep_recent > 0 else recent_messages
            )
            prompt_messages.extend(_to_chat_message(message) for message in tail)
            estimated_tokens = _estimate_tokens(prompt_messages)

    used_percent = (
        int(round((estimated_tokens / context_limit) * 100)) if context_limit > 0 else 0
    )
    used_percent = max(0, min(100, used_percent))
    left_tokens = max(context_limit - estimated_tokens, 0)
    left_percent = max(0, min(100, 100 - used_percent))

    return BuiltContext(
        messages=prompt_messages,
        estimated_tokens=estimated_tokens,
        used_summary_id=latest_summary.id if latest_summary else None,
        compacted=compacted,
        context_window=context_limit,
        used_percent=used_percent,
        left_tokens=left_tokens,
        left_percent=left_percent,
    )
