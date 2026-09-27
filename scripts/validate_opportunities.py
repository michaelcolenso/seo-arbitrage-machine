"""Score provider-neutral opportunity evidence dossiers.

Input is a JSON array of EvidenceDossier objects. The collector can be a human,
browser agent, CSV import, first-party telemetry job, or future API adapter.
No paid SEO provider is required and raw evidence remains auditable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dsf_scout.radar.evidence_validation import EvidenceDossier, score_dossier


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    dossiers = [EvidenceDossier.model_validate(item) for item in payload]
    results = [score_dossier(d).model_dump() for d in dossiers]
    results.sort(key=lambda row: row["score"], reverse=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
