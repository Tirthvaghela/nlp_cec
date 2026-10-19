"""Read-only: which evaluations in the configured database were scored by the fallback (not the embedding engine)?

    python -m scripts.pilot_fallback_report

Used by docs/PILOT_RUNBOOK.md section 5. Prints ids and counts only (no names, e-mails or answers). For every
listed evaluation the teacher must enter their own mark with a reason before publication; in PILOT_MODE the server
refuses to publish a submission while any of its fallback-scored questions lacks one. Exit code 1 if any
fallback-scored evaluation still lacks a teacher mark with a reason.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def report(db) -> list[dict]:
    rows = []
    for e in db.evaluations.find({"backend": {"$ne": "embedding"}},
                                 {"assessment_id": 1, "submission_id": 1, "question_id": 1, "backend": 1, "published": 1,
                                  "teacher_score": 1, "adjustment_reason": 1, "evaluated_at": 1}):
        rows.append({
            "assessment_id": str(e["assessment_id"]), "submission_id": str(e["submission_id"]),
            "evaluation_id": str(e["_id"]), "backend": e.get("backend"), "published": bool(e.get("published")),
            "teacher_marked_with_reason": e.get("teacher_score") is not None and bool((e.get("adjustment_reason") or "").strip()),
        })
    return rows


def main() -> None:
    from app.config import Settings
    from app.db import get_db

    print(f"database: {Settings().mongodb_db}")
    rows = report(get_db())
    by_assessment = defaultdict(lambda: {"fallback": 0, "open": 0, "published": 0})
    for r in rows:
        a = by_assessment[r["assessment_id"]]
        a["fallback"] += 1
        a["open"] += not r["teacher_marked_with_reason"]
        a["published"] += r["published"]
    for aid, a in sorted(by_assessment.items()):
        print(f"assessment {aid}: {a['fallback']} fallback-scored evaluation(s), {a['open']} still need a teacher mark "
              f"with a reason, {a['published']} published")
    for r in rows:
        if not r["teacher_marked_with_reason"]:
            print(f"  needs teacher mark: submission {r['submission_id']} evaluation {r['evaluation_id']} (backend {r['backend']})")
    if not rows:
        print("no fallback-scored evaluations")
    sys.exit(1 if any(not r["teacher_marked_with_reason"] for r in rows) else 0)


if __name__ == "__main__":
    main()
