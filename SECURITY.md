# Security and data handling

Scanning is local and never executes tools described by input data. HTML reports have no external resources and display untrusted values through textContent. JSON payloads escape script-closing characters.

The scanner is not a sandbox for unlimited hostile inputs. Impose filesystem, CPU, record-size and memory limits when processing untrusted large datasets. JSON arrays and individual JSONL records are loaded in memory. Findings accumulate in memory; duplicate metadata is stored in a temporary SQLite database removed at scan completion.

Reports include source paths and diagnostic identifiers. Reproductions copy original data and may contain secrets or personal information. Review artifacts before sharing. The reproduction command reads source paths listed in a report; use reports you generated or have reviewed. No automatic source changes or fixes occur.

For security issues, contact the repository maintainer privately using the hosting platform's private vulnerability reporting when enabled. Do not post sensitive datasets in public issues.
