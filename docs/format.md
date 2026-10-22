# Input contract

One trajectory is a JSON object. Extra metadata is retained in source data but not interpreted.

JSON input rejects duplicate keys, nonfinite numeric values and nesting deeper than 256 containers. The explicit depth bound is consistent across supported Python versions; brackets inside strings do not count.

```json
{
  "id": "sample-1", "task_id": "task-1", "attempt_id": "attempt-1", "split": "train",
  "messages": [
    {"role": "user", "content": "What is 2 + 2?"},
    {"role": "assistant", "content": null, "tool_calls": [
      {"id": "call-1", "type": "function", "function": {"name": "calculator", "arguments": "{\"expression\":\"2+2\"}"}}
    ]},
    {"role": "tool", "tool_call_id": "call-1", "content": "4"},
    {"role": "assistant", "content": "4", "weight": 1}
  ],
  "reward": 1.0, "outcome": "success", "reward_components": {"correctness": 1.0},
  "truncated": false, "finish_reason": "stop"
}
```

`id`, `task_id`, `attempt_id`, `split` are optional nonempty strings. IDs are checked globally within one scan; task IDs describe related attempts. A duplicate sharing task_id is classified as RETRY_DUPLICATE; this is a provenance heuristic, not proof a retry occurred.

Messages require role in system/developer/user/assistant/tool. Content may be string, structured array, or null. Structured content is compared exactly; image/audio payload semantics are not inspected. Tool calls require nonempty string ID and function name; arguments may be an object or JSON-encoded object. Missing call type means function. Parallel results may arrive in any order, before the next non-tool turn. Assistant weight, when supplied, must be integer 0 or 1.

ShareGPT uses `conversations`, `from`, `value`; human→user, gpt→assistant, observation/function→tool. Tool messages still need explicit tool_call_id and structured tool_calls; unstructured function-call text is not parsed. `events` uses the same message structure. Export exactly one message array. Multiple aliases produce SCHEMA_FIELD; the first is still inspected for additional diagnostics.

Reward is optional finite numeric data. Outcome is success/failure/unknown. reward_components declares an **additive** mapping; do not use it for arbitrary non-additive evaluator internals. Truncation is explicit boolean true or finish_reason length/max_tokens. Absence of truncation markers is not evidence of completeness.

## Token-aligned supervision

```json
{
  "messages": [{"role":"user","content":"Hi"},{"role":"assistant","content":"Hello"}],
  "input_ids": [101, 102, 103, 0],
  "labels": [-100, 102, 103, -100],
  "loss_mask": [0, 1, 1, 0],
  "attention_mask": [1, 1, 1, 0],
  "token_roles": ["user", "assistant", "assistant", "assistant"],
  "eos_token_id": 103,
  "label_alignment": "unshifted"
}
```

Arrays, when present, must match input_ids length. Token IDs are nonnegative integers; labels allow configured ignore_index. Masks require integer 0/1 (JSON booleans are rejected). token_roles uses normalized roles. Training-role checks are policy based, default assistant only. Special tokens must be assigned the role used by your template's training policy. Packed datasets need a producer adapter to provide faithful boundaries; this tool does not infer them from token values.

No tokenizer is loaded. The tool cannot establish that content matches token IDs, infer EOS, inspect attention matrices, validate tokenizer vocabulary bounds, or infer cross-episode boundaries from a flat token array.
