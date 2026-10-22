from __future__ import annotations

import json
import math
from typing import Callable

from .adapters import messages
from .model import Config, finite_number

ROLES = {"system", "developer", "user", "assistant", "tool"}


def check_record(raw: object, config: Config, emit: Callable) -> list:
    if not isinstance(raw, dict):
        emit("SCHEMA_RECORD", "", "Trajectory must be a JSON object.")
        return []
    rows, key, original = messages(raw)
    if not isinstance(original, list) or not original:
        emit("SCHEMA_RECORD", f"/{key}", "A nonempty message array is required.")
        return []
    pending, seen, resolved = {}, {}, set()
    for index, msg in enumerate(rows):
        ptr, role = msg.pointer, msg.role
        if "tool_call_id" in msg.data and not isinstance(msg.result_id, str):
            emit("SCHEMA_FIELD", ptr + "/tool_call_id", "tool_call_id must be a string.")
        if not isinstance(original[index], dict) or not isinstance(role, str) or role not in ROLES:
            emit("SCHEMA_MESSAGE", ptr, "Message must be an object with a supported role.")
            continue
        if not (msg.content is None or isinstance(msg.content, (str, list))):
            emit("SCHEMA_MESSAGE", ptr + "/content", "Content must be text, a structured array, or null.")
        if role != "tool" and pending:
            emit(
                "TOOL_ORDER",
                ptr,
                "A new turn starts while tool results are pending.",
                details={"pending_ids": list(pending)},
            )
        if "weight" in msg.data and (
            role != "assistant" or type(msg.data["weight"]) is not int or msg.data["weight"] not in (0, 1)
        ):
            emit("MESSAGE_WEIGHT", ptr + "/weight", "Weight must be integer 0 or 1 on an assistant turn.")
        calls = msg.calls
        if not isinstance(calls, list):
            emit("TOOL_CALL_FORMAT", ptr + "/tool_calls", "tool_calls must be an array.")
            calls = []
        if calls and role != "assistant":
            emit("TOOL_CALL_FORMAT", ptr + "/tool_calls", "Only assistant turns may issue tool calls.")
        for call_index, call in enumerate(calls):
            cp = f"{ptr}/tool_calls/{call_index}"
            if not isinstance(call, dict):
                emit("TOOL_CALL_FORMAT", cp, "Tool call must be an object.")
                continue
            cid, fn = call.get("id"), call.get("function")
            if (
                not isinstance(cid, str)
                or not cid
                or not isinstance(fn, dict)
                or not isinstance(fn.get("name"), str)
                or not fn.get("name")
                or call.get("type", "function") != "function"
            ):
                emit("TOOL_CALL_FORMAT", cp, "Tool call needs a string ID and a named function.")
                continue
            args = fn.get("arguments")
            try:
                parsed = (
                    json.loads(args, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
                    if isinstance(args, str)
                    else args
                )
                if not isinstance(parsed, dict):
                    raise ValueError("not an object")
                json.dumps(parsed, allow_nan=False)
            except (ValueError, TypeError):
                emit(
                    "TOOL_ARGUMENTS",
                    cp + "/function/arguments",
                    "Arguments must be a JSON object or its valid JSON serialization.",
                )
            if cid in seen:
                emit("TOOL_DUPLICATE_ID", cp + "/id", "Tool call ID is reused within this trajectory.")
            else:
                seen[cid] = (fn["name"], cp)
                pending[cid] = cp
        if role == "tool":
            cid = msg.result_id
            if not isinstance(cid, str) or not cid or cid not in seen:
                emit(
                    "TOOL_ORPHAN_RESULT", ptr + "/tool_call_id", "Tool result has no matching preceding call."
                )
            elif cid in resolved:
                emit("TOOL_DUPLICATE_RESULT", ptr + "/tool_call_id", "This tool call already has a result.")
            else:
                resolved.add(cid)
                pending.pop(cid, None)
                if "name" in msg.data and msg.data["name"] != seen[cid][0]:
                    emit("TOOL_NAME_MISMATCH", ptr + "/name", "Tool result name does not match its call.")
        if role == "assistant" and not msg.content and not calls:
            emit("EMPTY_ASSISTANT", ptr, "Assistant turn contains neither content nor a tool call.")
    for cp in pending.values():
        emit("TOOL_MISSING_RESULT", cp, "Tool invocation has no corresponding response.")
    if config.require_final_assistant and (rows[-1].role != "assistant" or rows[-1].calls):
        emit("FINAL_ASSISTANT", rows[-1].pointer, "Trajectory does not end in an assistant answer.")
    finish = raw.get("finish_reason", rows[-1].data.get("finish_reason"))
    if "truncated" in raw and type(raw["truncated"]) is not bool:
        emit("SCHEMA_FIELD", "/truncated", "truncated must be a boolean.")
    if raw.get("truncated") is True or finish in ("length", "max_tokens"):
        pointer = (
            "/truncated"
            if raw.get("truncated") is True
            else ("/finish_reason" if "finish_reason" in raw else rows[-1].pointer + "/finish_reason")
        )
        emit("TRUNCATED", pointer, "Generation ended at a truncation boundary.")
    for field in ("id", "task_id", "attempt_id", "split"):
        if field in raw and (not isinstance(raw[field], str) or not raw[field]):
            emit("SCHEMA_FIELD", f"/{field}", f"{field} must be a nonempty string.")
    check_reward(raw, config, emit)
    check_masks(raw, config, emit)
    return rows


def check_reward(raw: dict, config: Config, emit: Callable) -> None:
    outcome = raw.get("outcome")
    if "outcome" in raw and outcome not in ("success", "failure", "unknown"):
        emit("SCHEMA_FIELD", "/outcome", "outcome must be success, failure, or unknown.")
    if "reward" not in raw:
        return
    reward = raw["reward"]
    if not finite_number(reward):
        emit("REWARD_INVALID", "/reward", "Reward must be a finite number, excluding booleans.")
        return
    if not config.reward_min <= reward <= config.reward_max:
        emit("REWARD_RANGE", "/reward", "Reward is outside the configured range.")
    if (outcome == "success" and reward < config.success_reward_min) or (
        outcome == "failure" and reward > config.failure_reward_max
    ):
        emit(
            "REWARD_OUTCOME", "/reward", "Reward contradicts the configured policy for the declared outcome."
        )
    if "reward_components" in raw:
        components = raw["reward_components"]
        if (
            not isinstance(components, dict)
            or not components
            or not all(finite_number(v) for v in components.values())
        ):
            emit(
                "REWARD_COMPONENTS",
                "/reward_components",
                "Components must be a nonempty mapping of finite numbers.",
            )
        else:
            try:
                total = math.fsum(components.values())
            except OverflowError:
                total = math.inf
            if not math.isclose(total, reward, rel_tol=1e-7, abs_tol=1e-8):
                emit(
                    "REWARD_COMPONENTS",
                    "/reward_components",
                    "Additive reward components do not sum to reward.",
                )


def check_masks(raw: dict, config: Config, emit: Callable) -> None:
    fields = ("input_ids", "labels", "loss_mask", "attention_mask", "token_roles")
    arrays = {}
    for name in fields:
        if name in raw:
            value = raw[name]
            if not isinstance(value, list):
                emit("MASK_VALUE", f"/{name}", f"{name} must be an array.")
                continue
            arrays[name] = value
            if name == "token_roles":
                valid = all(isinstance(v, str) and v in ROLES for v in value)
            elif name in ("attention_mask", "loss_mask"):
                valid = all(type(v) is int and v in (0, 1) for v in value)
            else:
                valid = all(
                    type(v) is int and (v >= 0 or name == "labels" and v == config.ignore_index)
                    for v in value
                )
            if not valid:
                emit("MASK_VALUE", f"/{name}", f"{name} contains invalid values.")
    if not arrays:
        return
    if "input_ids" not in arrays:
        emit("SCHEMA_FIELD", "/input_ids", "Token supervision requires input_ids.")
        return
    n = len(arrays["input_ids"])
    for name, value in arrays.items():
        if len(value) != n:
            emit("MASK_LENGTH", f"/{name}", f"{name} length {len(value)} differs from input_ids length {n}.")
    if any(len(v) != n for v in arrays.values()):
        return
    alignment = raw.get("label_alignment", "unshifted")
    if alignment not in ("unshifted", "shifted"):
        emit("SCHEMA_FIELD", "/label_alignment", "label_alignment must be unshifted or shifted.")
    labels, mask = arrays.get("labels"), arrays.get("loss_mask")
    supervised = [
        (labels is not None and labels[i] != config.ignore_index) or (mask is not None and mask[i] == 1)
        for i in range(n)
    ]

    def positions(rule: str, field: str, indices: list[int], text: str) -> None:
        if indices:
            emit(
                rule,
                f"/{field}/{indices[0]}",
                text,
                details={"positions": indices[:20], "count": len(indices)},
            )

    if labels is not None and alignment == "unshifted":
        positions(
            "MASK_LABEL_MISMATCH",
            "labels",
            [i for i in range(n) if labels[i] != config.ignore_index and labels[i] != arrays["input_ids"][i]],
            "Unshifted supervised labels must match input_ids.",
        )
    if labels is not None and mask is not None:
        positions(
            "MASK_CONFLICT",
            "loss_mask",
            [i for i in range(n) if (labels[i] != config.ignore_index) != (mask[i] == 1)],
            "labels and loss_mask select different training positions.",
        )
    if labels is not None or mask is not None:
        if not any(supervised):
            emit("MASK_EMPTY", "/labels" if labels is not None else "/loss_mask", "No tokens are supervised.")
        roles, attention = arrays.get("token_roles"), arrays.get("attention_mask")
        if roles is not None:
            positions(
                "MASK_ROLE_LEAK",
                "token_roles",
                [i for i in range(n) if supervised[i] and roles[i] not in config.train_roles],
                "Supervised tokens belong to roles outside train_roles.",
            )
        else:
            emit(
                "MASK_UNVERIFIABLE", "/input_ids", "No token_roles supplied; role leakage cannot be checked."
            )
        if attention is not None:
            positions(
                "MASK_PADDING",
                "attention_mask",
                [i for i in range(n) if supervised[i] and attention[i] == 0],
                "Padding tokens contribute to the training objective.",
            )
    if "eos_token_id" in raw:
        eos = raw["eos_token_id"]
        if type(eos) is not int or eos < 0:
            emit("SCHEMA_FIELD", "/eos_token_id", "eos_token_id must be a nonnegative integer.")
        else:
            attention = arrays.get("attention_mask", [1] * n)
            active = [i for i in range(n) if attention[i] == 1]
            if active and arrays["input_ids"][active[-1]] != eos:
                emit(
                    "EOS_MISSING",
                    f"/input_ids/{active[-1]}",
                    "Last nonpadding token differs from eos_token_id.",
                )
