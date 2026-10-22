# Agent TraceCheck

**像检查代码一样检查 Agent 训练轨迹。** 在数据进入 SFT / RL 之前，定位工具配对、重试重复、奖励矛盾、截断和训练掩码问题。

Python 3.11+ · 零运行时第三方依赖 · 本地离线处理 · MIT

```text
Agent logs → JSON / JSONL → 34 quality rules → Evidence + reproduction + remediation
                                     └── JSON / HTML / SARIF / Markdown → CI
```

## 快速开始

从本仓库安装（尚未声明发布到 PyPI）：

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux: source .venv/bin/activate
python -m pip install -e .
agent-tracecheck scan examples/clean.jsonl
agent-tracecheck scan examples/broken.jsonl --json reports/report.json --html reports/report.html
```

第二条扫描故意含错误，退出码为 **1**。直接用浏览器打开 `reports/report.html`，按规则、严重程度或关键词筛选；全部资源内嵌，无需服务器。

| 检查范围 | 具体问题 |
| --- | --- |
| 工具调用 | 缺失结果、孤立结果、重复 ID、重复结果、非法参数、调用未完成就继续对话、名称不一致 |
| 数据重复 | 忽略随机 call ID 的语义一致轨迹、同任务重试重复、矛盾监督、跨 split 泄漏、样本 ID 冲突 |
| 奖励 | 非数值 / NaN / Infinity、越界、声明 outcome 与奖励策略矛盾、加法分项不一致 |
| 完整性 | 显式截断、缺少最终 assistant、空生成、已声明 EOS 缺失 |
| 训练掩码 | 长度和值、labels 与 input_ids、loss_mask 与 ignore_index、角色泄漏、padding 参与训练、零训练信号 |

每个问题包含稳定规则名、严重程度、文件、JSONL 行号、记录索引、JSON Pointer、源记录 SHA-256、关联样本和修复建议。JSON 文档中的行号仅指向文档入口，精确定位使用 JSON Pointer。

## 提取并验证最小复现

从 JSON 报告复制问题 ID：

```bash
agent-tracecheck repro reports/report.json ISSUE_ID --output reports/repro.jsonl
agent-tracecheck scan reports/repro.jsonl --config reports/repro.jsonl.meta.json
```

提取器验证源记录哈希，保留关联样本，并反复删除顶层字段和整条消息。每次删除都重新运行检查器，最终必须仍触发目标规则。默认最多 300 次缩减检查，最后额外做一次验证；预算耗尽会明确标注。

这里的“最小”指上述删除操作下的 **1-minimal**，不是全局最小或最短字节串。token 数组和嵌套字段保留以避免破坏对齐；可触发同一规则的多个实例不保证保留原实例。复现不会执行任何工具调用。坏 JSON 使用报告给出的原始行排查，不能转成合法 JSONL 复现。

## 配置策略

```bash
agent-tracecheck scan data/ --config tracecheck.toml --fail-on warning
agent-tracecheck rules
agent-tracecheck explain MASK_ROLE_LEAK
agent-tracecheck scan data.jsonl --disable FINAL_ASSISTANT
```

配置可设置奖励范围、成功/失败阈值、允许训练的角色、ignore_index、最终回答要求、禁用规则和严重程度。见 [tracecheck.toml](tracecheck.toml)。默认奖励范围 `[0,1]`；采用负奖励或非标准尺度时必须配置。

退出码：`0` 无达到阈值的问题；`1` 质检未通过；`2` 输入路径、配置或输出错误；`130` 用户中断。`--fail-on none` 只生成报告。不要将报告输出目录放入下一轮扫描的数据目录，因为目录扫描会读取所有 JSON 文件。

## 输入格式与 Python API

支持一行一个对象的 `.jsonl` / `.ndjson`、单对象 JSON、JSON 数组和 `{"trajectories": [...]}`。消息字段可用 OpenAI 风格 `messages`、ShareGPT `conversations`（human/gpt/observation）或同构的 `events`。这里支持的是消息子集，**不接受原始 Responses API 流事件或任意框架 trace**。完整契约和转换示例见 [格式说明](docs/format.md)。

```python
from agent_tracecheck import Config, scan

report = scan(["data/train.jsonl", "data/test.jsonl"], Config(reward_min=-1))
for issue in report.issues:
    print(issue.rule, issue.source.line, issue.pointer, issue.suggestion)
```

一次传入全部 split 才能进行跨 split 检测。也可使用 `scan_records(iterable_of_Record, config)` 接入生成器；调用者应为每条 Record 提供唯一 Source 位置。

## 工程集成

```bash
agent-tracecheck scan data/ --sarif reports/tracecheck.sarif --markdown reports/summary.md
python -m pip install -e ".[dev]"
python -m pytest
python -m build
```

附带 Windows / Linux、Python 3.11–3.13 的 GitHub Actions 工作流，执行测试、lint、构建和示例扫描。SARIF 2.1.0 报告可交给支持 SARIF 的代码扫描平台。上游数据流水线示例见 [集成说明](docs/integration.md)。

## 边界和设计取舍

- 奖励检查只验证格式、范围和声明之间的一致性，不证明任务是否真正完成，也不自动改奖励。
- 重复定义为消息角色、内容、工具名称、解析后的参数和结果相同；仅归一化工具 ID。不是 embedding 近似去重，不把调用相似但结果不同的轨迹合并。并行调用的不同排列仍视为不同轨迹。
- JSONL 逐行读入；磁盘 SQLite 索引只保存哈希和定位元数据。报告问题保留在内存，空间随问题数增长。单条超大记录仍需完整读入，JSON 数组完整加载。不宣称无限规模流式内存。
- 未提供 token_roles 时无法核实角色泄漏；会输出信息提示。默认 labels 是未移位的 causal labels；`label_alignment="shifted"` 只关闭 token 值相等检查，不验证位移是否正确。
- `events` 是本工具的消息别名，不会自动重建执行图、处理跨轨迹的工具 ID 或猜测 legacy function_call 的配对。
- 报告含本地路径、工具 ID 和诊断；复现含原数据。工具不联网、不执行轨迹内容、不原地修复数据。

本项目为可运行的 **0.1.0 alpha**，提供规则测试和可复现工作流；接入实际训练前应使用你自己的数据分布与奖励策略校准误报率。

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)、[规则目录](docs/rules.md) 和 [安全说明](SECURITY.md)。优先欢迎新的真实缺陷样本、带负例的规则和明确格式契约的适配器。
