"""Lossless field aliases for OpenAI messages, ShareGPT, and canonical events.

Adapters never guess tool-call IDs or infer rewards from natural language.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class Message:
    data: dict
    pointer: str
    role: Any
    content: Any
    calls: Any
    result_id: Any


def messages(raw: dict) -> tuple[list[Message], str, Any]:
    key = next((k for k in ("messages", "conversations", "events") if k in raw), "messages")
    rows = raw.get(key)
    if not isinstance(rows, list):
        return [], key, rows
    aliases = {"human": "user", "gpt": "assistant", "observation": "tool", "function": "tool"}
    result = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            result.append(Message({}, f"/{key}/{index}", None, None, None, None))
            continue
        role = row.get("role", row.get("from"))
        role = aliases.get(role, role) if isinstance(role, str) else role
        result.append(
            Message(
                row,
                f"/{key}/{index}",
                role,
                row.get("content", row.get("value")),
                row.get("tool_calls", []),
                row.get("tool_call_id"),
            )
        )
    return result, key, rows


def semantic_messages(rows: list[Message]) -> list[dict]:
    """Canonicalize call identifiers only; retain content, arguments, order and results."""
    ids = {}
    result = []
    for msg in rows:
        calls = []
        for call in msg.calls:
            cid = call["id"]
            ids.setdefault(cid, f"call_{len(ids)}")
            fn = dict(call["function"])
            args = fn.get("arguments")
            if isinstance(args, str):
                import json

                try:
                    fn["arguments"] = json.loads(args)
                except ValueError:
                    pass
            calls.append({"id": ids[cid], "function": fn, "type": call.get("type", "function")})
        result.append(
            {
                "role": msg.role,
                "content": msg.content,
                "tool_calls": calls,
                "tool_call_id": ids.get(msg.result_id, msg.result_id),
            }
        )
    return result
