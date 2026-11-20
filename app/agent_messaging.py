from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .company_graph import _append_event
from .database import Base, SessionLocal
from .workforce import chat_with_agent, _agent_role


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class AgentConversation(Base):
    """Durable, company-scoped peer conversation between independent AI employees."""

    __tablename__ = "agent_conversations"
    __table_args__ = (
        Index("ix_agent_conversations_company_updated", "company_id", "updated_at"),
        Index("ix_agent_conversations_status", "company_id", "status"),
    )

    conversation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    initiator_agent_id: Mapped[str] = mapped_column(String(36), index=True)
    participant_agent_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(120))
    max_turns: Mapped[int] = mapped_column(Integer, default=6)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentConversationMessage(Base):
    """A single durable event/message in an agent-to-agent conversation."""

    __tablename__ = "agent_conversation_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence_no", name="uq_agent_conversation_sequence"),
        Index("ix_agent_conversation_messages_thread", "conversation_id", "sequence_no"),
        Index("ix_agent_conversation_messages_company", "company_id", "tenant_id"),
    )

    message_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_conversations.conversation_id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    sequence_no: Mapped[int] = mapped_column(Integer)
    sender_type: Mapped[str] = mapped_column(String(20))
    sender_agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    sender_name: Mapped[str] = mapped_column(String(120))
    recipient_agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    recipient_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    message_kind: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


def resolve_agent_discussion(
    agents: list[dict[str, Any]], message: str
) -> dict[str, Any] | None:
    """Resolve natural-language peer instructions into an initiator and recipients.

    The first named employee initiates the interaction. For shorthand such as
    'discuss with Jamal', the configured coordinator is the implied initiator.
    """
    active = [
        agent for agent in agents
        if agent.get("type") == "agent" and agent.get("status") not in {"ARCHIVED", "DISABLED", "PAUSED"}
    ]
    action = re.search(
        r"\b(discuss|talk|chat|speak|connect|consult|ask|tell|message|greet|"
        r"introduce|meet|sync|align|brainstorm|say\s+(?:hello|hi))\b",
        message,
        re.IGNORECASE,
    )
    if not action:
        return None

    mentions: list[tuple[int, dict[str, Any]]] = []
    for agent in active:
        name = str(agent.get("name") or "").strip()
        if not name:
            continue
        match = re.search(rf"(?<![\w])@?{re.escape(name)}(?![\w])", message, re.IGNORECASE)
        if match:
            mentions.append((match.start(), agent))
    mentions.sort(key=lambda item: item[0])

    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, agent in mentions:
        if agent["id"] not in seen:
            seen.add(agent["id"])
            unique.append(agent)

    if len(unique) >= 2:
        participants = unique[:4]
        initiator = participants[0]
        recipients = participants[1:]
    elif len(unique) == 1 and re.search(r"\b(with|to)\b", message, re.IGNORECASE):
        recipient = unique[0]
        coordinator = next(
            (
                agent for agent in active
                if str((agent.get("data") or {}).get("authority") or "").upper() == "COORDINATOR"
            ),
            None,
        )
        if not coordinator or coordinator["id"] == recipient["id"]:
            return None
        initiator = coordinator
        recipients = [recipient]
        participants = [initiator, recipient]
    else:
        return None

    if not recipients:
        return None

    is_greeting = bool(re.search(r"\b(hello|hi|greet|say\s+hi|say\s+hello)\b", message, re.IGNORECASE))
    return {
        "initiator": initiator,
        "recipients": recipients,
        "participants": participants,
        "max_turns": 2 if is_greeting else 6,
    }


def _message_dict(message: AgentConversationMessage) -> dict[str, Any]:
    return {
        "message_id": message.message_id,
        "conversation_id": message.conversation_id,
        "sequence_no": message.sequence_no,
        "sender_type": message.sender_type,
        "sender_agent_id": message.sender_agent_id,
        "sender_name": message.sender_name,
        "recipient_agent_id": message.recipient_agent_id,
        "recipient_name": message.recipient_name,
        "message_kind": message.message_kind,
        "content": message.content,
        "metadata": message.metadata_json or {},
        "created_at": _iso(message.created_at),
    }


def _conversation_dict(db, conversation: AgentConversation, include_messages: bool = False) -> dict[str, Any]:
    result = {
        "conversation_id": conversation.conversation_id,
        "company_id": conversation.company_id,
        "tenant_id": conversation.tenant_id,
        "title": conversation.title,
        "status": conversation.status,
        "initiator_agent_id": conversation.initiator_agent_id,
        "participant_agent_ids": conversation.participant_agent_ids or [],
        "created_by": conversation.created_by,
        "max_turns": conversation.max_turns,
        "summary": conversation.summary,
        "last_error": conversation.last_error,
        "created_at": _iso(conversation.created_at),
        "updated_at": _iso(conversation.updated_at),
        "completed_at": _iso(conversation.completed_at),
    }
    if include_messages:
        rows = (
            db.query(AgentConversationMessage)
            .filter(AgentConversationMessage.conversation_id == conversation.conversation_id)
            .order_by(AgentConversationMessage.sequence_no.asc())
            .all()
        )
        result["messages"] = [_message_dict(row) for row in rows]
    return result


def list_agent_conversations(*, company_id: str, tenant_id: str, limit: int = 30) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        rows = (
            db.query(AgentConversation)
            .filter(
                AgentConversation.company_id == company_id,
                AgentConversation.tenant_id == tenant_id,
            )
            .order_by(AgentConversation.updated_at.desc())
            .limit(min(max(limit, 1), 100))
            .all()
        )
        return [_conversation_dict(db, row) for row in rows]


def get_agent_conversation(
    *, company_id: str, tenant_id: str, conversation_id: str
) -> dict[str, Any] | None:
    with SessionLocal() as db:
        row = (
            db.query(AgentConversation)
            .filter(
                AgentConversation.conversation_id == conversation_id,
                AgentConversation.company_id == company_id,
                AgentConversation.tenant_id == tenant_id,
            )
            .first()
        )
        return _conversation_dict(db, row, include_messages=True) if row else None


def _event(db, *, company_id: str, tenant_id: str, actor_id: str, event_type: str, payload: dict[str, Any]) -> None:
    _append_event(
        db,
        company_id=company_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        event_type=event_type,
        payload=payload,
    )


def _persist_message(
    *,
    conversation_id: str,
    company_id: str,
    tenant_id: str,
    actor_id: str,
    sequence_no: int,
    sender_type: str,
    sender_name: str,
    content: str,
    message_kind: str,
    sender_agent_id: str | None = None,
    recipient_agent_id: str | None = None,
    recipient_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    message_id = str(uuid.uuid4())
    clean_content = content.strip()
    row = AgentConversationMessage(
        message_id=message_id,
        conversation_id=conversation_id,
        company_id=company_id,
        tenant_id=tenant_id,
        sequence_no=sequence_no,
        sender_type=sender_type,
        sender_agent_id=sender_agent_id,
        sender_name=sender_name,
        recipient_agent_id=recipient_agent_id,
        recipient_name=recipient_name,
        message_kind=message_kind,
        content=clean_content,
        content_sha256=hashlib.sha256(clean_content.encode("utf-8")).hexdigest(),
        metadata_json=metadata or {},
    )
    with SessionLocal() as db:
        db.add(row)
        conversation = db.query(AgentConversation).filter(
            AgentConversation.conversation_id == conversation_id,
            AgentConversation.company_id == company_id,
            AgentConversation.tenant_id == tenant_id,
        ).first()
        if conversation is None:
            raise LookupError("Conversation was not found while writing a message")
        conversation.updated_at = _now()
        _event(
            db,
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=sender_agent_id or actor_id,
            event_type="agent.conversation.message",
            payload={
                "conversation_id": conversation_id,
                "message_id": message_id,
                "sequence_no": sequence_no,
                "sender_type": sender_type,
                "sender_agent_id": sender_agent_id,
                "recipient_agent_id": recipient_agent_id,
                "message_kind": message_kind,
                "content_sha256": row.content_sha256,
            },
        )
        db.commit()
        db.refresh(row)
        return _message_dict(row)


def _set_conversation_status(
    *, conversation_id: str, company_id: str, tenant_id: str,
    actor_id: str, status: str, summary: str | None = None, error: str | None = None
) -> None:
    with SessionLocal() as db:
        row = db.query(AgentConversation).filter(
            AgentConversation.conversation_id == conversation_id,
            AgentConversation.company_id == company_id,
            AgentConversation.tenant_id == tenant_id,
        ).first()
        if row is None:
            return
        row.status = status
        row.summary = summary
        row.last_error = (error or "")[:2000] or None
        row.updated_at = _now()
        if status in {"COMPLETED", "FAILED", "CANCELLED"}:
            row.completed_at = _now()
        _event(
            db,
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            event_type=f"agent.conversation.{status.lower()}",
            payload={"conversation_id": conversation_id, "status": status},
        )
        db.commit()


async def stream_agent_discussion(
    *,
    company_id: str,
    tenant_id: str,
    actor_id: str,
    company: dict[str, Any],
    agents: list[dict[str, Any]],
    initiator: dict[str, Any],
    recipients: list[dict[str, Any]],
    founder_message: str,
    max_turns: int = 6,
) -> AsyncIterator[dict[str, Any]]:
    """Run a bounded peer conversation, persisting and streaming every message."""
    participants = [initiator, *recipients]
    max_turns = min(max(int(max_turns), 2), 12)
    simple_greeting = bool(re.search(r"\b(hello|hi|greet|say\s+hi|say\s+hello)\b", founder_message, re.IGNORECASE))
    if simple_greeting:
        max_turns = 2

    conversation_id = str(uuid.uuid4())
    title = re.sub(r"\s+", " ", founder_message).strip()[:240] or "Agent discussion"
    with SessionLocal() as db:
        conversation = AgentConversation(
            conversation_id=conversation_id,
            company_id=company_id,
            tenant_id=tenant_id,
            title=title,
            status="RUNNING",
            initiator_agent_id=initiator["id"],
            participant_agent_ids=[agent["id"] for agent in participants],
            created_by=actor_id,
            max_turns=max_turns,
        )
        db.add(conversation)
        founder_row = AgentConversationMessage(
            message_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            company_id=company_id,
            tenant_id=tenant_id,
            sequence_no=1,
            sender_type="FOUNDER",
            sender_agent_id=None,
            sender_name="Founder",
            recipient_agent_id=initiator["id"],
            recipient_name=initiator["name"],
            message_kind="INSTRUCTION",
            content=founder_message.strip(),
            content_sha256=hashlib.sha256(founder_message.strip().encode("utf-8")).hexdigest(),
            metadata_json={},
        )
        db.add(founder_row)
        _event(
            db,
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            event_type="agent.conversation.started",
            payload={
                "conversation_id": conversation_id,
                "initiator_agent_id": initiator["id"],
                "participant_agent_ids": [agent["id"] for agent in participants],
                "title": title,
            },
        )
        db.commit()
        db.refresh(founder_row)

    yield {
        "type": "conversation_started",
        "conversation_id": conversation_id,
        "title": title,
        "participants": [{"id": agent["id"], "name": agent["name"], "role": _agent_role(agent)} for agent in participants],
        "message": _message_dict(founder_row),
    }

    sequence_no = 2
    try:
        first_recipient = recipients[0]
        acknowledgement = (
            f"Okay — I’ll discuss this with {first_recipient['name']} and report back."
        )
        item = _persist_message(
            conversation_id=conversation_id, company_id=company_id, tenant_id=tenant_id,
            actor_id=actor_id, sequence_no=sequence_no, sender_type="AGENT",
            sender_name=initiator["name"], sender_agent_id=initiator["id"],
            recipient_name="Founder", message_kind="ACKNOWLEDGEMENT",
            content=acknowledgement, metadata={"audience": "FOUNDER"},
        )
        sequence_no += 1
        yield {"type": "message", "message": item}

        opening_context = (
            f"You are beginning a private work conversation with {first_recipient['name']} "
            f"({ _agent_role(first_recipient) }). The founder instructed you: {founder_message!r}. "
            "Write the first message directly to your colleague. Do not address the founder, "
            "do not claim that you have already received a reply, and make the purpose clear."
        )
        opening = await chat_with_agent(
            agent=initiator, company=company, agents=agents,
            message=f"Start the discussion with {first_recipient['name']} now.",
            history=[],
            company_id=company_id, tenant_id=tenant_id,
            system_context=opening_context,
        )
        opening_item = _persist_message(
            conversation_id=conversation_id, company_id=company_id, tenant_id=tenant_id,
            actor_id=actor_id, sequence_no=sequence_no, sender_type="AGENT",
            sender_name=initiator["name"], sender_agent_id=initiator["id"],
            recipient_agent_id=first_recipient["id"], recipient_name=first_recipient["name"],
            message_kind="A2A", content=opening,
            metadata={"turn": 1, "channel": "agent-to-agent"},
        )
        sequence_no += 1
        yield {"type": "message", "message": opening_item}

        transcript: list[dict[str, str]] = [
            {"role": "assistant", "content": f"{initiator['name']} to {first_recipient['name']}: {opening}"}
        ]
        previous_speaker = initiator
        complete = False
        for turn in range(2, max_turns + 1):
            speaker = first_recipient if previous_speaker["id"] == initiator["id"] else initiator
            peer = previous_speaker
            latest = transcript[-1]["content"]
            context = (
                f"You are {speaker['name']}, speaking as an independent AI employee to "
                f"{peer['name']} ({_agent_role(peer)}). This is a colleague-to-colleague conversation, "
                "not a reply to the founder. Use your own role, responsibilities, skills and instructions. "
                "Respond to the latest message, ask useful follow-up questions or challenge assumptions "
                "when appropriate. Keep the discussion focused. When the matter is resolved and you have "
                "nothing material to add, append the exact token <PB_DISCUSSION_COMPLETE> at the end."
            )
            reply = await chat_with_agent(
                agent=speaker, company=company, agents=agents,
                message=(
                    f"Your colleague {peer['name']} sent this message to you:\n\n"
                    f"{latest}\n\nReply directly to {peer['name']}."
                ),
                history=transcript[-10:],
                company_id=company_id, tenant_id=tenant_id,
                system_context=context,
            )
            complete = "<PB_DISCUSSION_COMPLETE>" in reply
            reply = re.sub(r"\s*<PB_DISCUSSION_COMPLETE>\s*", "", reply).strip()
            if not reply:
                reply = "I have nothing further to add. Thank you."
                complete = True
            item = _persist_message(
                conversation_id=conversation_id, company_id=company_id, tenant_id=tenant_id,
                actor_id=actor_id, sequence_no=sequence_no, sender_type="AGENT",
                sender_name=speaker["name"], sender_agent_id=speaker["id"],
                recipient_agent_id=peer["id"], recipient_name=peer["name"],
                message_kind="A2A", content=reply,
                metadata={"turn": turn, "channel": "agent-to-agent"},
            )
            sequence_no += 1
            yield {"type": "message", "message": item}
            transcript.append({"role": "assistant", "content": f"{speaker['name']} to {peer['name']}: {reply}"})
            previous_speaker = speaker
            if complete:
                break

        summary_context = (
            f"You are {initiator['name']}. You have just completed a discussion with "
            f"{first_recipient['name']}. You are now reporting to the founder. Use the discussion "
            "transcript to provide a concise, useful summary: key points agreed, differing views, "
            "open questions and next steps. Do not invent decisions or claim actions were executed."
        )
        summary = await chat_with_agent(
            agent=initiator, company=company, agents=agents,
            message="Please report the outcome of your discussion to the founder.",
            history=transcript[-10:],
            company_id=company_id, tenant_id=tenant_id,
            system_context=summary_context,
        )
        summary_item = _persist_message(
            conversation_id=conversation_id, company_id=company_id, tenant_id=tenant_id,
            actor_id=actor_id, sequence_no=sequence_no, sender_type="AGENT",
            sender_name=initiator["name"], sender_agent_id=initiator["id"],
            message_kind="FOUNDER_SUMMARY", content=summary,
            metadata={"audience": "FOUNDER"},
        )
        _set_conversation_status(
            conversation_id=conversation_id, company_id=company_id, tenant_id=tenant_id,
            actor_id=actor_id, status="COMPLETED", summary=summary,
        )
        yield {"type": "message", "message": summary_item}
        conversation = get_agent_conversation(
            company_id=company_id, tenant_id=tenant_id, conversation_id=conversation_id
        )
        yield {"type": "complete", "conversation": conversation}
    except Exception as exc:
        _set_conversation_status(
            conversation_id=conversation_id, company_id=company_id, tenant_id=tenant_id,
            actor_id=actor_id, status="FAILED", error=f"{type(exc).__name__}: {str(exc)[:1800]}",
        )
        raise
