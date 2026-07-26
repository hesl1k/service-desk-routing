from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO_DIR = ROOT / "data" / "scenarios"
DEFAULT_REPORT_DIR = ROOT / "reports"


@dataclass
class RequestResult:
    scenario: str
    ok: bool
    status_code: int
    elapsed_ms: float
    api_status: str
    error: str = ""


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def load_payloads(directory: Path) -> list[tuple[str, dict[str, Any]]]:
    payloads = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payloads.append((str(payload.get("scenario_id") or path.stem), payload))
    if not payloads:
        raise FileNotFoundError(f"no scenarios found in {directory}")
    return payloads


async def send_one(client: httpx.AsyncClient, payloads: list[tuple[str, dict[str, Any]]], semaphore: asyncio.Semaphore) -> RequestResult:
    scenario, payload = random.choice(payloads)
    async with semaphore:
        started = time.perf_counter()
        try:
            response = await client.post("/route", json=payload)
            elapsed = (time.perf_counter() - started) * 1000
            body = response.json()
            status = str(body.get("status", ""))
            ok = response.status_code == 200 and status in {"optimal", "infeasible"}
            error = "" if ok else str(body.get("message") or response.text[:200])
            return RequestResult(scenario, ok, response.status_code, elapsed, status, error)
        except Exception as exc:
            return RequestResult(scenario, False, 0, (time.perf_counter() - started) * 1000, "", str(exc))


async def run_load(host: str, scenario_dir: Path, target_rps: int, duration_sec: int, concurrency: int) -> dict[str, Any]:
    payloads = load_payloads(scenario_dir)
    semaphore = asyncio.Semaphore(concurrency)
    total_requests = target_rps * duration_sec
    interval = 1 / target_rps
    results: list[RequestResult] = []
    tasks: set[asyncio.Task[RequestResult]] = set()
    limits = httpx.Limits(max_connections=max(20, concurrency * 2), max_keepalive_connections=max(10, concurrency))

    async with httpx.AsyncClient(base_url=host.rstrip("/"), timeout=30.0, limits=limits) as client:
        started = time.perf_counter()
        for index in range(total_requests):
            target = started + index * interval
            delay = target - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            tasks.add(asyncio.create_task(send_one(client, payloads, semaphore)))
            done = {task for task in tasks if task.done()}
            for task in done:
                results.append(task.result())
            tasks -= done
        if tasks:
            results.extend(await asyncio.gather(*tasks))
        elapsed = time.perf_counter() - started

    latencies = [item.elapsed_ms for item in results]
    successes = sum(item.ok for item in results)
    failures = len(results) - successes
    return {
        "host": host,
        "target_rps": target_rps,
        "duration_sec": duration_sec,
        "concurrency": concurrency,
        "total_requests": len(results),
        "successful_requests": successes,
        "failed_requests": failures,
        "error_rate_percent": round(failures / len(results) * 100 if results else 0.0, 2),
        "actual_rps": round(len(results) / elapsed if elapsed else 0.0, 2),
        "average_response_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "median_response_ms": round(statistics.median(latencies), 2) if latencies else 0.0,
        "min_response_ms": round(min(latencies), 2) if latencies else 0.0,
        "max_response_ms": round(max(latencies), 2) if latencies else 0.0,
        "p95_response_ms": round(percentile(latencies, 0.95), 2),
        "p99_response_ms": round(percentile(latencies, 0.99), 2),
        "raw_results": [asdict(item) for item in results],
    }


def write_reports(summary: dict[str, Any], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    public = {key: value for key, value in summary.items() if key != "raw_results"}
    (report_dir / "load_test_summary.json").write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")
    with (report_dir / "load_test_results.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary["raw_results"][0].keys()) if summary["raw_results"] else [])
        if summary["raw_results"]:
            writer.writeheader()
            writer.writerows(summary["raw_results"])
    passed = public["error_rate_percent"] == 0 and public["actual_rps"] >= public["target_rps"] * 0.95
    report = f"""# Нагрузочная проверка REST API

## Параметры прогона

- Адрес: `{public['host']}`
- Целевая интенсивность: {public['target_rps']} запросов в секунду
- Длительность: {public['duration_sec']} секунд
- Ограничение параллельных запросов: {public['concurrency']}

## Результаты

| Показатель | Значение |
|---|---:|
| Отправлено запросов | {public['total_requests']} |
| Успешных запросов | {public['successful_requests']} |
| Ошибок | {public['failed_requests']} |
| Доля ошибок | {public['error_rate_percent']}% |
| Фактический RPS | {public['actual_rps']} |
| Среднее время ответа | {public['average_response_ms']} мс |
| Медиана | {public['median_response_ms']} мс |
| p95 | {public['p95_response_ms']} мс |
| p99 | {public['p99_response_ms']} мс |

## Вывод

Контрольный прогон {'прошёл без потери целевой интенсивности' if passed else 'показал ограничение по производительности или ошибки запросов'}. Тест обращался к реальному `POST /route`; искусственная задержка и заглушка API не использовались.
"""
    (report_dir / "load_test_report.md").write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send controlled load to POST /route")
    parser.add_argument("--host", default="http://127.0.0.1:8002")
    parser.add_argument("--scenario-dir", default=str(DEFAULT_SCENARIO_DIR))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--rps", type=int, default=20)
    parser.add_argument("--duration", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=50)
    args = parser.parse_args()
    summary = asyncio.run(run_load(args.host, Path(args.scenario_dir), args.rps, args.duration, args.concurrency))
    write_reports(summary, Path(args.report_dir))
    print(json.dumps({key: value for key, value in summary.items() if key != "raw_results"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
