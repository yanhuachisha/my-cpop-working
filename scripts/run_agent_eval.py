from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.agent_evaluation import evaluate_agent  # noqa: E402
from app.data_store import get_store  # noqa: E402
from app.langchain_agent import MusicAgent  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run C-Pop Agent benchmark.")
    parser.add_argument("--suite", default="smoke", help="smoke, full, history, memory, safety, etc.")
    parser.add_argument("--algorithm", default="auto", choices=["auto", "react", "plan_execute", "reflection"])
    parser.add_argument("--dataset", default=str(BACKEND / "app" / "evals" / "agent_benchmark.jsonl"))
    parser.add_argument("--output-dir", default=str(ROOT / "artifacts" / "agent_eval"))
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--live", action="store_true", help="Use live LLM if DEEPSEEK_API_KEY exists.")
    args = parser.parse_args()

    if args.live:
        load_dotenv(ROOT / ".env", override=False)
        if not os.getenv("DEEPSEEK_API_KEY"):
            parser.error("--live requires DEEPSEEK_API_KEY in the environment or project .env file")
    else:
        os.environ.pop("DEEPSEEK_API_KEY", None)

    report = evaluate_agent(
        MusicAgent(get_store()),
        suite=args.suite,
        dataset_path=args.dataset,
        algorithm=args.algorithm,
        max_cases=args.max_cases,
    )
    report["requested_mode"] = "live" if args.live else "offline"
    report["online_verified"] = bool(args.live) and all(
        case["provider"] == "deepseek" and case["mode"].startswith("langchain:")
        for case in report["cases"]
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.suite}_{args.algorithm}_{'live' if args.live else 'offline'}"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown_report(report), encoding="utf-8")

    print(f"Agent eval report: {json_path}")
    print(f"Markdown summary: {md_path}")
    print(f"pass_rate={report['pass_rate']} cases={report['case_count']} failed={report['failed_count']}")
    print(f"requested_mode={report['requested_mode']} online_verified={report['online_verified']}")
    if args.live and not report["online_verified"]:
        print("Live evaluation verification failed: at least one case used a fallback provider.", file=sys.stderr)
        return 2
    return 0 if report["failed_count"] == 0 else 1


def _markdown_report(report: dict) -> str:
    lines = [
        "# Agent Benchmark Report",
        "",
        f"- Suite: `{report['suite']}`",
        f"- Algorithm: `{report['algorithm']}`",
        f"- Requested mode: `{report.get('requested_mode', 'unknown')}`",
        f"- Online verified: `{report.get('online_verified', False)}`",
        f"- Generated at: `{report['generated_at']}`",
        f"- Cases: `{report['case_count']}`",
        f"- Pass rate: `{report['pass_rate']}`",
        f"- Avg latency: `{report['latency']['avg_ms']} ms`",
        f"- Max latency: `{report['latency']['max_ms']} ms`",
        "",
        "## Metrics",
        "",
        "| Metric | Score |",
        "| --- | ---: |",
    ]
    for name, value in report["metrics"].items():
        lines.append(f"| `{name}` | {value} |")

    lines.extend(["", "## Categories", "", "| Category | Cases | Pass Rate |", "| --- | ---: | ---: |"])
    for category, data in report["categories"].items():
        lines.append(f"| `{category}` | {data['case_count']} | {data['pass_rate']} |")

    failures = [case for case in report["cases"] if not case["passed"]]
    lines.extend(["", "## Failures", ""])
    if not failures:
        lines.append("No failures.")
    else:
        for case in failures:
            reasons = ", ".join(case["failure_reasons"])
            lines.append(f"- `{case['id']}`: {reasons}")

    lines.extend(["", "## Case Detail", "", "| Case | Category | Passed | Tools | Latency |", "| --- | --- | --- | --- | ---: |"])
    for case in report["cases"]:
        tools = ", ".join(case["tools_used"]) or "-"
        lines.append(f"| `{case['id']}` | `{case['category']}` | {case['passed']} | `{tools}` | {case['latency_ms']} |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
