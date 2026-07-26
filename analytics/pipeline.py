from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from analytics.api_client import call_route_api
from analytics.baseline import solve_baseline
from analytics.metrics import add_savings, flatten_ticket_results, summarize_result
from app.lp_core import solve_lp


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run_pipeline(input_dir: Path, output_dir: Path, lp_source: str, api_url: str) -> dict[str, Any]:
    scenario_paths = sorted(input_dir.glob("*.json"))
    if not scenario_paths:
        raise FileNotFoundError(f"no JSON scenarios found in {input_dir}")

    metrics_rows: list[dict[str, Any]] = []
    ticket_rows: list[dict[str, Any]] = []
    raw_results: dict[str, Any] = {}

    for path in scenario_paths:
        data = load_json(path)
        scenario = str(data.get("scenario_id") or path.stem)
        baseline = solve_baseline(data)
        lp_result = call_route_api(data, api_url) if lp_source == "api" else solve_lp(data)
        if lp_result.get("status") not in {"optimal", "infeasible"}:
            raise RuntimeError(f"LP failed for {scenario}: {lp_result.get('message')}")

        raw_results[scenario] = {"baseline": baseline, "lp": lp_result}
        metrics_rows.append(summarize_result(scenario, "baseline", data, baseline))
        metrics_rows.append(summarize_result(scenario, "lp", data, lp_result))
        ticket_rows.extend(flatten_ticket_results(scenario, "baseline", data, baseline))
        ticket_rows.extend(flatten_ticket_results(scenario, "lp", data, lp_result))

    metrics_rows = add_savings(metrics_rows)
    write_csv(output_dir / "metrics_summary.csv", metrics_rows)
    write_csv(output_dir / "ticket_results.csv", ticket_rows)
    write_json(output_dir / "raw_results.json", raw_results)

    baseline_rows = [row for row in metrics_rows if row["method"] == "baseline"]
    lp_rows = [row for row in metrics_rows if row["method"] == "lp"]
    baseline_total = sum(float(row["total_cost"]) for row in baseline_rows)
    lp_total = sum(float(row["total_cost"]) for row in lp_rows)
    savings = baseline_total - lp_total
    overall_percent = savings / baseline_total * 100 if baseline_total else 0.0
    average_percent = sum(float(row["savings_percent"]) for row in lp_rows) / len(lp_rows) if lp_rows else 0.0
    economy = {
        "scenarios": len(lp_rows),
        "lp_source": lp_source,
        "baseline_total_cost": round(baseline_total, 2),
        "lp_total_cost": round(lp_total, 2),
        "total_savings": round(savings, 2),
        "overall_savings_percent": round(overall_percent, 2),
        "average_scenario_savings_percent": round(average_percent, 2),
        "target_savings_percent": 7.0,
        "target_reached": overall_percent >= 7.0,
    }
    write_json(output_dir / "economy_summary.json", economy)
    return economy


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare baseline routing with the LP model")
    parser.add_argument("--input-dir", default="data/scenarios")
    parser.add_argument("--output-dir", default="data/output")
    parser.add_argument("--lp-source", choices=["direct", "api"], default="direct")
    parser.add_argument("--api-url", default="http://127.0.0.1:8002")
    args = parser.parse_args()
    result = run_pipeline(Path(args.input_dir), Path(args.output_dir), args.lp_source, args.api_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
