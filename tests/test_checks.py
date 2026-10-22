import copy
import json
import random

import pytest

from agent_tracecheck import Config, Record, Source, scan_records


def base():
    return {"messages": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]}


def tool():
    return {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [{"id": "a", "function": {"name": "search", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "a", "content": "result"},
            {"role": "assistant", "content": "done"},
        ]
    }


def run(*rows, config=None):
    return scan_records([Record(r, Source("<test>", i + 1, i)) for i, r in enumerate(rows)], config)


def rules(*rows, config=None):
    return {i.rule for i in run(*rows, config=config).issues}


def test_clean():
    assert not rules(base())
    assert not rules(tool())


@pytest.mark.parametrize(
    "row,expected",
    [
        (None, "SCHEMA_RECORD"),
        ({"messages": [7]}, "SCHEMA_MESSAGE"),
        ({"messages": [{"role": "assistant", "content": ""}]}, "EMPTY_ASSISTANT"),
        ({"messages": [{"role": "user", "content": "hi"}]}, "FINAL_ASSISTANT"),
        ({"messages": [{"role": "assistant", "content": "hi", "weight": 2}]}, "MESSAGE_WEIGHT"),
        ({"messages": [{"role": "assistant", "tool_calls": [None]}]}, "TOOL_CALL_FORMAT"),
    ],
)
def test_structural_rules(row, expected):
    assert expected in rules(row)


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("reward", True, "REWARD_INVALID"),
        ("reward", float("nan"), "REWARD_INVALID"),
        ("reward", float("inf"), "REWARD_INVALID"),
        ("reward", 10**400, "REWARD_INVALID"),
        ("reward", 2, "REWARD_RANGE"),
        ("truncated", True, "TRUNCATED"),
        ("truncated", "false", "SCHEMA_FIELD"),
        ("finish_reason", "length", "TRUNCATED"),
        ("id", [], "SCHEMA_FIELD"),
        ("outcome", {}, "SCHEMA_FIELD"),
        ("labels", "bad", "MASK_VALUE"),
        ("input_ids", [-1], "MASK_VALUE"),
    ],
)
def test_metadata(field, value, expected):
    row = base()
    row[field] = value
    assert expected in rules(row)


@pytest.mark.parametrize(
    "extra,expected",
    [
        ({"reward": 1, "outcome": "failure"}, "REWARD_OUTCOME"),
        ({"reward": 0.5, "reward_components": {"a": 0.1}}, "REWARD_COMPONENTS"),
        ({"input_ids": [1, 2], "labels": [1]}, "MASK_LENGTH"),
        ({"input_ids": [1], "labels": [2]}, "MASK_LABEL_MISMATCH"),
        ({"input_ids": [1], "labels": [1], "loss_mask": [0]}, "MASK_CONFLICT"),
        ({"input_ids": [1], "labels": [1], "token_roles": ["user"]}, "MASK_ROLE_LEAK"),
        ({"input_ids": [1], "labels": [1], "attention_mask": [0]}, "MASK_PADDING"),
        ({"input_ids": [1], "labels": [-100]}, "MASK_EMPTY"),
        ({"input_ids": [1], "labels": [1]}, "MASK_UNVERIFIABLE"),
        ({"input_ids": [1], "eos_token_id": 2}, "EOS_MISSING"),
    ],
)
def test_training(extra, expected):
    assert expected in rules(base() | extra)


def test_mask_clean_and_shifted():
    row = base() | {
        "input_ids": [1, 2, 3, 0],
        "labels": [-100, 2, 3, -100],
        "loss_mask": [0, 1, 1, 0],
        "attention_mask": [1, 1, 1, 0],
        "token_roles": ["user", "assistant", "assistant", "assistant"],
        "eos_token_id": 3,
    }
    assert not rules(row)
    row["labels"][1] = 3
    row["label_alignment"] = "shifted"
    assert not rules(row)


def test_pairing():
    row = tool()
    row["messages"].pop(1)
    assert {"TOOL_MISSING_RESULT", "TOOL_ORDER"} <= rules(row)
    row = tool()
    row["messages"][1]["tool_call_id"] = "missing"
    assert "TOOL_ORPHAN_RESULT" in rules(row)
    row = tool()
    row["messages"].insert(2, copy.deepcopy(row["messages"][1]))
    assert "TOOL_DUPLICATE_RESULT" in rules(row)
    row = tool()
    row["messages"][1]["name"] = "other"
    assert "TOOL_NAME_MISMATCH" in rules(row)
    row = tool()
    row["messages"][0]["tool_calls"] *= 2
    assert "TOOL_DUPLICATE_ID" in rules(row)


@pytest.mark.parametrize("arguments", ["{", "[]", "null", '{"x":NaN}', None, 2])
def test_arguments(arguments):
    row = tool()
    row["messages"][0]["tool_calls"][0]["function"]["arguments"] = arguments
    assert "TOOL_ARGUMENTS" in rules(row)


def test_parallel_results_may_arrive_out_of_order():
    row = tool()
    call = copy.deepcopy(row["messages"][0]["tool_calls"][0])
    call["id"] = "b"
    row["messages"][0]["tool_calls"].append(call)
    row["messages"].insert(1, {"role": "tool", "tool_call_id": "b", "content": "second"})
    assert not rules(row)


def test_duplicates():
    a, b = tool(), tool()
    b["messages"][0]["tool_calls"][0]["id"] = "random"
    b["messages"][1]["tool_call_id"] = "random"
    assert "DUPLICATE_SAMPLE" in rules(a, b)
    a["task_id"] = b["task_id"] = "same"
    assert "RETRY_DUPLICATE" in rules(a, b)
    a["reward"], b["reward"] = 1, 0
    a["split"], b["split"] = "train", "test"
    assert {"DUPLICATE_LABEL_CONFLICT", "SPLIT_LEAKAGE"} <= rules(a, b)
    b["messages"][1]["content"] = "different evidence"
    assert "RETRY_DUPLICATE" not in rules(a, b)


def test_split_leakage_after_missing_metadata():
    assert "SPLIT_LEAKAGE" in rules(base(), base() | {"split": "train"}, base() | {"split": "test"})


def test_id_collision():
    assert "ID_COLLISION" in rules(base() | {"id": "x"}, tool() | {"id": "x"})


def test_sharegpt():
    assert not rules({"conversations": [{"from": "human", "value": "hi"}, {"from": "gpt", "value": "hello"}]})


def test_policy():
    assert "REWARD_RANGE" not in rules(base() | {"reward": 5}, config=Config(reward_max=10))
    assert "REWARD_RANGE" not in rules(base() | {"reward": 5}, config=Config(disabled_rules=["REWARD_RANGE"]))
    assert (
        run(base() | {"reward": 5}, config=Config(severity={"REWARD_RANGE": "info"})).issues[0].severity
        == "info"
    )
    with pytest.raises(ValueError):
        Config(reward_min=5).validate()


def test_malformed_types_never_crash():
    rng = random.Random(42)
    values = [None, True, 3, "", [], {}, [1], {"bad": []}]
    samples = []
    for _ in range(500):
        row = tool()
        if rng.choice([True, False]):
            row[
                rng.choice(
                    ["messages", "reward", "task_id", "labels", "loss_mask", "outcome", "finish_reason"]
                )
            ] = rng.choice(values)
        else:
            row["messages"][rng.randrange(3)][
                rng.choice(["role", "content", "tool_calls", "tool_call_id", "weight"])
            ] = rng.choice(values)
        samples.append(row)
    result = run(*samples)
    assert result.records == 500
    json.dumps(result.to_dict(), allow_nan=False)
