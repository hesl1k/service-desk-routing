from __future__ import annotations

import csv
import json
from pathlib import Path

from analytics.pipeline import run_pipeline

ROOT = Path(__file__).resolve().parents[1]


def test_pipeline_writes_consistent_outputs(tmp_path: Path) -> None:
    economy = run_pipeline(ROOT / "data" / "scenarios", tmp_path, "direct", "http://127.0.0.1:8002")
    assert economy["scenarios"] == 5
    assert (tmp_path / "metrics_summary.csv").exists()
    assert (tmp_path / "ticket_results.csv").exists()
    assert (tmp_path / "raw_results.json").exists()
    rows = list(csv.DictReader((tmp_path / "metrics_summary.csv").open(encoding="utf-8-sig")))
    assert len(rows) == 10
    assert {row["method"] for row in rows} == {"baseline", "lp"}
    saved = json.loads((tmp_path / "economy_summary.json").read_text(encoding="utf-8"))
    assert saved == economy
