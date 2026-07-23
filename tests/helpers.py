from __future__ import annotations

from copy import deepcopy


def finding(**overrides):
    data = {
        "id": "TEST-001",
        "title": "A concrete issue",
        "category": "test.category",
        "severity": "P2",
        "confidence": "HYPOTHESIS",
        "status": "OPEN",
        "scope": {"files": ["src/example.py"], "symbols": []},
        "evidence": [
            {
                "level": "E1",
                "type": "code",
                "location": "src/example.py:1",
                "summary": "Relevant code path exists.",
            }
        ],
        "reproduction": None,
        "impact": "Impact is bounded but real.",
        "recommended_action": "Apply a targeted correction.",
        "verification": [],
    }
    data.update(deepcopy(overrides))
    return data
