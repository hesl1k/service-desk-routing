from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    client = TestClient(app)
    health = client.get('/health')
    health.raise_for_status()

    payload = json.loads((ROOT / 'data' / 'scenarios' / 'normal_load.json').read_text(encoding='utf-8'))
    route = client.post('/route', json=payload)
    route.raise_for_status()
    body = route.json()
    if body.get('status') != 'optimal':
        raise RuntimeError(body.get('message') or f"unexpected status: {body.get('status')}")
    print(json.dumps({
        'health': health.json(),
        'route_status': body['status'],
        'backend': body['backend'],
        'objective_cost': body['objective_cost'],
        'assigned_tickets': len(body['ticket_results']),
        'unassigned_tickets': len(body['unassigned_ticket_ids']),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
