# Agent Benchmark Report

This report records a verified live DeepSeek/LangChain evaluation of the minimum expanded Agent benchmark: 125 JSONL cases across eight suites. Each suite was executed online with `--live`, then merged into one evidence file. Every case reported `provider=deepseek` with a LangChain execution mode; no deterministic fallback was used.

## Run

```powershell
python scripts/run_agent_eval.py --suite recommendation --algorithm auto --live --output-dir artifacts/agent_eval_125_verified_categories/recommendation
python scripts/run_agent_eval.py --suite search --algorithm auto --live --output-dir artifacts/agent_eval_125_verified_categories/search
python scripts/run_agent_eval.py --suite history --algorithm auto --live --output-dir artifacts/agent_eval_125_verified_categories/history
python scripts/run_agent_eval.py --suite memory --algorithm auto --live --output-dir artifacts/agent_eval_125_verified_categories_rerun/memory
python scripts/run_agent_eval.py --suite multi-turn --algorithm auto --live --output-dir artifacts/agent_eval_125_verified_categories_rerun2/multi-turn
python scripts/run_agent_eval.py --suite tool-failure --algorithm auto --live --output-dir artifacts/agent_eval_125_verified_categories/tool-failure
python scripts/run_agent_eval.py --suite safety --algorithm auto --live --output-dir artifacts/agent_eval_125_verified_categories/safety
python scripts/run_agent_eval.py --suite no-tool --algorithm auto --live --output-dir artifacts/agent_eval_125_verified_categories/no-tool
```

- Generated at: `2026-08-18T03:54:50.888106+00:00`
- Dataset: `backend/app/evals/agent_benchmark.jsonl`
- Requested mode: `live`
- Online verified: `True`
- Provider: `deepseek` (`125/125` cases)
- Model: `deepseek-v4-flash`
- Cases: `125`
- Passed: `125`
- Failed: `0`
- Pass rate: `1.0`
- Average latency: `6125.54 ms`
- Maximum latency: `16537 ms`

## Metrics

| Metric | Score | Meaning |
| --- | ---: | --- |
| `tool_recall` | 1.0 | Every expected tool was selected. |
| `tool_precision` | 1.0 | No unexpected tool type was selected. |
| `arg_accuracy` | 1.0 | Required tool arguments matched, including semantic substring checks. |
| `grounding_score` | 1.0 | Required answer evidence appeared. |
| `safety_score` | 1.0 | Forbidden answer content was absent. |
| `trajectory_score` | 1.0 | Tool order, forbidden tools, and iteration budgets passed. |
| `latency_score` | 1.0 | Every live case stayed within the live latency budget. |

## Coverage

| Suite | Category | Cases | Passed | Pass Rate |
| --- | --- | ---: | ---: | ---: |
| `recommendation` | `recommendation` | 20 | 20 | 1.0 |
| `search` | `music_search` | 15 | 15 | 1.0 |
| `history` | `listening_history` | 15 | 15 | 1.0 |
| `memory` | `memory` | 15 | 15 | 1.0 |
| `multi-turn` | `multi_turn` | 15 | 15 | 1.0 |
| `tool-failure` | `tool_failure` | 15 | 15 | 1.0 |
| `safety` | `safety` | 20 | 20 | 1.0 |
| `no-tool` | `no_tool` | 10 | 10 | 1.0 |

## Verification Notes

- `--live` loads the project `.env` automatically and fails fast when `DEEPSEEK_API_KEY` is missing.
- Live verification requires every case to report the DeepSeek provider and a LangChain execution mode.
- The benchmark includes synonym-heavy routing, time-period queries, user memory, multi-turn follow-ups, injected tool failures, safety refusals, and no-tool chat/help cases.
- Tool precision is part of the pass gate; unexpected extra tools fail a case.
- Tool failures are injected through evaluation context and must produce explicit degradation without fabricated results.
- Deterministic offline search uses the bundled local catalog, so CI smoke runs do not depend on public network search.

## Evidence

- Merged machine-readable report: `artifacts/agent_eval_125_live_merged/full_auto_live.json`
- Merged Markdown summary: `artifacts/agent_eval_125_live_merged/full_auto_live.md`
- Dataset generator: `scripts/build_agent_benchmark.py`
- Dataset: `backend/app/evals/agent_benchmark.jsonl`
