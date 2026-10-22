import gzip
import json
import os
from dataclasses import asdict

import pytest

from agent_tracecheck import Config, Record, Source, scan, scan_records
from agent_tracecheck.cli import load_config, main
from agent_tracecheck.io import discover, read_records, strict_json
from agent_tracecheck.reporters import render
from agent_tracecheck.reproduce import reproduce


def row():
    return {"messages": [{"role": "assistant", "content": "ok"}]}


def check(value):
    return {i.rule for i in scan_records([Record(value)]).issues}


@pytest.mark.parametrize(
    "suffix,data", [(".jsonl", ""), (".jsonl", "\n \n"), (".json", "[]"), (".json", '{"trajectories":[]}')]
)
def test_empty_inputs_fail(tmp_path, suffix, data):
    path = tmp_path / ("empty" + suffix)
    path.write_text(data)
    report = scan([path])
    assert report.records == 0
    assert report.files == 1
    assert [i.rule for i in report.issues] == ["INPUT_EMPTY"]
    assert main(["scan", str(path)]) == 1


def test_empty_iterator():
    assert [i.rule for i in scan_records(iter([])).issues] == ["INPUT_EMPTY"]


@pytest.mark.parametrize(
    "text",
    [
        '{"a":1,"a":2}',
        '{"reward":NaN}',
        '{"reward":Infinity}',
        '{"reward":1e400}',
        "[" * 2000 + "0" + "]" * 2000,
    ],
)
def test_invalid_json_is_reported_and_scan_continues(tmp_path, text):
    path = tmp_path / "data.jsonl"
    path.write_text(text + "\n" + json.dumps(row()))
    report = scan([path])
    assert report.records == 2
    assert [i.rule for i in report.issues] == ["INPUT_JSON"]


@pytest.mark.parametrize("extension", ["json.gz", "jsonl.gz", "ndjson.gz"])
def test_gzip(tmp_path, extension):
    path = tmp_path / ("data." + extension)
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.write(json.dumps(row()))
    assert discover([tmp_path]) == [path]
    assert not scan([path]).issues


def test_corrupt_gzip_is_operational_failure(tmp_path):
    path = tmp_path / "data.jsonl.gz"
    path.write_bytes(b"broken")
    assert main(["scan", str(path)]) == 2


def test_exclude(tmp_path):
    (tmp_path / "data.jsonl").write_text(json.dumps(row()))
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports/out.json").write_text("{}")
    assert len(discover([tmp_path], ["reports/*"])) == 1
    assert main(["scan", str(tmp_path), "--exclude", "reports/*"]) == 0


@pytest.mark.parametrize(
    "config",
    [
        Config(train_roles=[{}]),
        Config(disabled_rules=[[]]),
        Config(severity={"MASK_EMPTY": []}),
        Config(ignore_index=0),
        Config(ignore_index=True),
    ],
)
def test_bad_policy_raises_value_error(config):
    with pytest.raises(ValueError):
        config.validate()


@pytest.mark.parametrize("data", [[], None, 42, "oops", {"train_roles": [{}]}])
def test_bad_json_config_has_no_traceback(tmp_path, data):
    path = tmp_path / "policy.JSON"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_config(str(path))


def test_config_snapshot_is_immutable_from_caller():
    config = Config()
    report = scan_records([Record(row())], config)
    config.train_roles.append("user")
    assert report.config.train_roles == ["assistant"]


def test_reward_and_masks_checked_despite_missing_messages():
    assert {"SCHEMA_RECORD", "REWARD_RANGE", "MASK_LENGTH"} <= check(
        {"reward": 5, "input_ids": [1], "labels": []}
    )


def test_ambiguous_message_arrays():
    assert "SCHEMA_FIELD" in check(row() | {"events": []})


def test_legacy_call_is_not_silently_accepted():
    value = row()
    value["messages"][0]["function_call"] = {"name": "f", "arguments": "{}"}
    assert "TOOL_LEGACY_FORMAT" in check(value)


def test_invalid_mask_no_cascading_false_leak():
    rules = check(row() | {"input_ids": [1], "labels": ["bad"], "token_roles": ["user"]})
    assert "MASK_VALUE" in rules
    assert "MASK_ROLE_LEAK" not in rules


def test_components_require_scalar_reward():
    assert "REWARD_COMPONENTS" in check(row() | {"reward_components": {"a": 1}})


def test_empty_tokens():
    assert "MASK_EMPTY" in check(row() | {"input_ids": []})


def test_id_collision_even_with_invalid_messages():
    report = scan_records([Record({"id": "x"}, Source("a")), Record({"id": "x", "reward": 1}, Source("b"))])
    assert "ID_COLLISION" in {i.rule for i in report.issues}


@pytest.mark.parametrize("data", [[], None, 42, {"schema_version": "1.0", "issues": [None]}])
def test_bad_repro_report(tmp_path, data):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data))
    assert main(["repro", str(path), "x", "-o", str(tmp_path / "repro.jsonl")]) == 2


def test_repro_budget_and_extension(tmp_path):
    path = tmp_path / "data.jsonl"
    path.write_text(json.dumps(row() | {"reward": 5}))
    report = scan([path])
    rp = tmp_path / "report.json"
    rp.write_text(render(report, "json"))
    issue = next(i for i in report.issues if i.rule == "REWARD_RANGE")
    with pytest.raises(ValueError):
        reproduce(rp, issue.id, tmp_path / "repro.json")
    with pytest.raises(ValueError):
        reproduce(rp, issue.id, tmp_path / "repro.jsonl", 0)
    manifest = reproduce(rp, issue.id, tmp_path / "repro.jsonl", 1)
    assert manifest["verified"] and not manifest["minimization_complete"]


def test_output_hardlink_cannot_destroy_input(tmp_path):
    path = tmp_path / "data.jsonl"
    path.write_text(json.dumps(row()))
    alias = tmp_path / "out.json"
    try:
        os.link(path, alias)
    except OSError:
        pytest.skip("Hard links unavailable on this filesystem")
    assert main(["scan", str(path), "-o", str(alias)]) == 2
    assert list(read_records(path))[0].raw == row()


def test_all_config_fields_round_trip(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(asdict(Config())))
    assert load_config(str(path)) == Config()


def test_tool_arguments_reject_duplicate_keys():
    with pytest.raises(ValueError, match="Duplicate"):
        strict_json('{"nested":{"x":1,"x":2}}')


def test_atomic_report_failure_preserves_existing_file(tmp_path, monkeypatch):
    from agent_tracecheck.io import atomic_write_text

    path = tmp_path / "report.json"
    path.write_text("original")

    def fail(*args):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        atomic_write_text(path, "replacement")
    assert path.read_text() == "original"
    assert list(tmp_path.iterdir()) == [path]


def test_sarif_repository_relative_uri(tmp_path, monkeypatch):
    from agent_tracecheck.reporters import sarif_report

    path = tmp_path / "data space.jsonl"
    path.write_text("{}")
    monkeypatch.chdir(tmp_path)
    result = sarif_report(scan([path]))["runs"][0]["results"][0]
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "data%20space.jsonl"


def test_json_depth_bound_is_explicit():
    assert strict_json("[" * 256 + "0" + "]" * 256)
    with pytest.raises(ValueError, match="256"):
        strict_json("[" * 257 + "0" + "]" * 257)


def test_json_depth_ignores_escaped_strings():
    content = "[" * 1000 + '\\"' + "]" * 1000
    assert strict_json(json.dumps({"content": content}))["content"] == content
