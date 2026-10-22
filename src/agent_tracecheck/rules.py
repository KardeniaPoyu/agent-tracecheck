"""Stable public rule identifiers and actionable remediation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    category: str
    severity: str
    title: str
    suggestion: str


RULES = {
    "INPUT_EMPTY": Rule(
        "input",
        "error",
        "Empty dataset",
        "Check export filters and input selection; an empty dataset cannot pass the training quality gate.",
    ),
    "TOOL_LEGACY_FORMAT": Rule(
        "tools",
        "error",
        "Unsupported legacy tool call",
        "Convert function_call to tool_calls with an explicit unique ID and preserve the corresponding tool_call_id. Do not infer pairing from name alone.",
    ),
    "INPUT_JSON": Rule(
        "input",
        "error",
        "Invalid JSON or UTF-8",
        "Repair the input encoding or JSON syntax at the reported physical line; do not silently skip this record.",
    ),
    "SCHEMA_RECORD": Rule(
        "schema",
        "error",
        "Invalid trajectory object",
        "Provide one object with a nonempty messages, conversations, or events array.",
    ),
    "SCHEMA_MESSAGE": Rule(
        "schema",
        "error",
        "Invalid message",
        "Use a supported role and string, structured-list, or null content. Preserve original ordering.",
    ),
    "SCHEMA_FIELD": Rule(
        "schema",
        "error",
        "Invalid training metadata",
        "Correct the reported field type against docs/format.md; do not coerce strings to booleans or numbers.",
    ),
    "TOOL_CALL_FORMAT": Rule(
        "tools",
        "error",
        "Malformed tool call",
        "Provide unique nonempty string id, type=function, and function{name, arguments}; arguments must encode a JSON object.",
    ),
    "TOOL_ARGUMENTS": Rule(
        "tools",
        "error",
        "Invalid tool arguments",
        "Repair arguments at the producer using structured JSON serialization; replay the tool only after validation.",
    ),
    "TOOL_DUPLICATE_ID": Rule(
        "tools",
        "error",
        "Reused tool call ID",
        "Assign a new ID to each invocation and update only its corresponding result reference.",
    ),
    "TOOL_ORPHAN_RESULT": Rule(
        "tools",
        "error",
        "Result has no preceding call",
        "Restore the original call or quarantine the incomplete sample. Do not invent a call to satisfy validation.",
    ),
    "TOOL_DUPLICATE_RESULT": Rule(
        "tools",
        "error",
        "Multiple results for one call",
        "Inspect retries and retain the result belonging to the accepted invocation; preserve other attempts in provenance.",
    ),
    "TOOL_MISSING_RESULT": Rule(
        "tools",
        "error",
        "Call has no result",
        "Restore the missing tool response, or mark and exclude the incomplete rollout from completed-episode training.",
    ),
    "TOOL_ORDER": Rule(
        "tools",
        "error",
        "Conversation advances before tools finish",
        "Place all pending tool responses before the next user/assistant turn; preserve parallel-call result order where meaningful.",
    ),
    "TOOL_NAME_MISMATCH": Rule(
        "tools",
        "error",
        "Tool response name disagrees with call",
        "Check routing and pair the response with the invocation that actually produced it.",
    ),
    "DUPLICATE_SAMPLE": Rule(
        "duplicates",
        "warning",
        "Repeated semantic trajectory",
        "Review the linked sample and deduplicate accepted trajectories before splitting; changed tool outputs remain distinct.",
    ),
    "RETRY_DUPLICATE": Rule(
        "duplicates",
        "warning",
        "Retry repeats an accepted trajectory",
        "Use task_id plus accepted-attempt provenance to keep one training sample per identical retry result.",
    ),
    "DUPLICATE_LABEL_CONFLICT": Rule(
        "duplicates",
        "error",
        "Identical trajectory has different supervision",
        "Compare reward, outcome and training masks across the linked records; resolve the source of contradictory supervision.",
    ),
    "SPLIT_LEAKAGE": Rule(
        "duplicates",
        "error",
        "Trajectory appears in different splits",
        "Deduplicate before partitioning and group related trajectories when assigning train/validation/test splits.",
    ),
    "ID_COLLISION": Rule(
        "duplicates",
        "error",
        "Record ID identifies different data",
        "Use an immutable unique sample ID and keep task_id separately for related attempts.",
    ),
    "REWARD_INVALID": Rule(
        "reward",
        "error",
        "Reward is not finite numeric data",
        "Emit a finite numeric reward; inspect evaluator failures instead of replacing NaN with a successful score.",
    ),
    "REWARD_RANGE": Rule(
        "reward",
        "error",
        "Reward lies outside configured range",
        "Check reward scaling or configure the documented range for this dataset.",
    ),
    "REWARD_OUTCOME": Rule(
        "reward",
        "warning",
        "Reward conflicts with declared outcome",
        "Review the evaluator and outcome metadata against your reward policy; this heuristic does not establish ground truth.",
    ),
    "REWARD_COMPONENTS": Rule(
        "reward",
        "error",
        "Reward does not equal declared component sum",
        "Recompute the scalar from reward_components, or omit additive components if your aggregation is non-additive.",
    ),
    "TRUNCATED": Rule(
        "completion",
        "warning",
        "Trajectory explicitly reports truncation",
        "Separate partial rollouts from completed episodes and preserve termination versus truncation semantics for RL bootstrapping.",
    ),
    "FINAL_ASSISTANT": Rule(
        "completion",
        "warning",
        "No final assistant response",
        "Restore the final response or disable require_final_assistant for intentionally partial trajectories.",
    ),
    "EMPTY_ASSISTANT": Rule(
        "completion",
        "warning",
        "Empty assistant turn",
        "Investigate a dropped generation; retain empty turns only if the target format explicitly requires them.",
    ),
    "EOS_MISSING": Rule(
        "completion",
        "warning",
        "Last active token is not declared EOS",
        "Verify tokenizer/template boundaries and truncation policy; an explicit eos_token_id enables this check.",
    ),
    "MASK_LENGTH": Rule(
        "masks",
        "error",
        "Token arrays have different lengths",
        "Regenerate all aligned arrays from the same final tokenized sequence after truncation and packing.",
    ),
    "MASK_VALUE": Rule(
        "masks",
        "error",
        "Invalid token or mask values",
        "Use integer token IDs and labels, binary loss/attention masks, and supported token roles.",
    ),
    "MASK_LABEL_MISMATCH": Rule(
        "masks",
        "error",
        "Labels disagree with aligned input tokens",
        "For unshifted causal labels, copy input_ids at trained positions and use ignore_index elsewhere. Set label_alignment=shifted to opt out of value equality checks.",
    ),
    "MASK_CONFLICT": Rule(
        "masks",
        "error",
        "Loss mask and label ignore positions disagree",
        "Generate labels and loss_mask from one shared supervision mask.",
    ),
    "MASK_ROLE_LEAK": Rule(
        "masks",
        "error",
        "Unintended role contributes to training loss",
        "Mask system/user/tool tokens or explicitly configure train_roles for your intended objective.",
    ),
    "MASK_PADDING": Rule(
        "masks",
        "error",
        "Padding contributes to loss",
        "Set labels to ignore_index and loss_mask to zero wherever attention_mask is zero.",
    ),
    "MASK_EMPTY": Rule(
        "masks",
        "warning",
        "No token contributes to loss",
        "Inspect template and truncation boundaries; remove zero-signal samples or regenerate their training masks.",
    ),
    "MESSAGE_WEIGHT": Rule(
        "masks",
        "error",
        "Invalid message training weight",
        "Use assistant weight=0 or 1 only; translate other weighting policies explicitly before importing.",
    ),
    "MASK_UNVERIFIABLE": Rule(
        "masks",
        "info",
        "Role-level token masking cannot be verified",
        "Export token_roles aligned to input_ids to validate which roles contribute to token-level loss.",
    ),
}
