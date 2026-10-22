import json

import pytest

from agent_tracecheck import scan
from agent_tracecheck.cli import main
from agent_tracecheck.io import read_records
from agent_tracecheck.reporters import render
from agent_tracecheck.reproduce import reproduce


def dataset(tmp_path):
    path = tmp_path / "data.jsonl"
    rows = [
        {
            "id": "one",
            "messages": [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "answer"}],
            "reward": 5,
        }
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return path


def test_jsonl_errors_and_bom(tmp_path):
    path = tmp_path / "broken.jsonl"
    path.write_bytes(b"\xef\xbb\xbf{}\n\n{broken\n\xff\n{}")
    records = list(read_records(path))
    assert [r.source.line for r in records] == [1, 3, 4, 5]
    assert len([i for i in scan([path]).issues if i.rule == "INPUT_JSON"]) == 2


@pytest.mark.parametrize("wrapped", [False, True])
def test_json_pointer(tmp_path, wrapped):
    path = tmp_path / "array.json"
    path.write_text(json.dumps({"trajectories": [{}]} if wrapped else [{}]))
    assert scan([path]).issues[0].source.pointer == ("/trajectories/0" if wrapped else "/0")


@pytest.mark.parametrize("fmt", ["text", "json", "html", "sarif", "markdown"])
def test_reports(tmp_path, fmt):
    report = scan([dataset(tmp_path)])
    output = render(report, fmt)
    assert "REWARD_RANGE" in output
    if fmt in ("json", "sarif"):
        json.loads(output)


def test_html_script_injection(tmp_path):
    path = dataset(tmp_path)
    report = scan([path])
    report.issues[0].message = "</script><script>alert(1)</script>"
    output = render(report, "html")
    assert "</script><script>alert(1)" not in output
    assert "innerHTML" not in output


def test_cli_exit_codes_and_outputs(tmp_path, capsys):
    path = dataset(tmp_path)
    report = tmp_path / "report.json"
    assert main(["scan", str(path), "--json", str(report)]) == 1
    assert report.exists()
    assert main(["scan", str(path), "--fail-on", "none"]) == 0
    assert main(["scan", str(path), "-o", str(path)]) == 2
    assert main(["scan", str(path), "--disable", "UNKNOWN"]) == 2
    assert main(["scan", str(tmp_path / "missing")]) == 2
    assert main(["rules"]) == 0
    assert main(["explain", "REWARD_RANGE"]) == 0


def test_repro_replay_and_stale_source(tmp_path):
    path = dataset(tmp_path)
    report = scan([path])
    report_path = tmp_path / "report.json"
    report_path.write_text(render(report, "json"), encoding="utf-8")
    issue = next(i for i in report.issues if i.rule == "REWARD_RANGE")
    output = tmp_path / "repro.jsonl"
    manifest = reproduce(report_path, issue.id, output)
    assert manifest["verified"] and manifest["minimization_complete"]
    assert "REWARD_RANGE" in {i.rule for i in scan([output]).issues}
    assert "id" not in list(read_records(output))[0].raw
    assert main(["scan", str(output), "--config", str(output) + ".meta.json"]) == 1
    path.write_text("{}")
    with pytest.raises(ValueError, match="changed"):
        reproduce(report_path, issue.id, tmp_path / "another.jsonl")


def test_duplicate_repro(tmp_path):
    path = dataset(tmp_path)
    content = path.read_text()
    path.write_text(content + "\n" + content)
    report = scan([path])
    rp = tmp_path / "report.json"
    rp.write_text(render(report, "json"))
    issue = next(i for i in report.issues if i.rule == "DUPLICATE_SAMPLE")
    out = tmp_path / "repro.jsonl"
    assert reproduce(rp, issue.id, out)["verified"]
    assert len(list(read_records(out))) == 2
