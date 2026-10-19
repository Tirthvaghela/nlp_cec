"""Publication identity and history (security audit V10).

Every publish / unpublish records WHO and WHEN:
* the submission gets ``published_by`` (or ``unpublished_by``) and an entry appended to ``publication_log``;
* its evaluations get ``published_by`` while published.

Records created before this module existed have no such fields: they are NOT back-filled or rewritten, so their
publication identity is simply unknown. ``publication_log`` is append-only through the API ($push only); it is not
tamper-proof against someone with direct database write access.
"""

from __future__ import annotations

from pymongo.database import Database

from app.db import now

PUBLISHED, UNPUBLISHED, UNPUBLISHED_FOR_REEVALUATION = "published", "unpublished", "unpublished_for_reevaluation"


def record(db: Database, submission_id, action: str, actor_id) -> None:
    ts = now()
    entry = {"action": action, "by": actor_id, "at": ts}
    if action == PUBLISHED:
        db.submissions.update_one({"_id": submission_id},
                                  {"$set": {"published_by": actor_id}, "$push": {"publication_log": entry}})
        db.evaluations.update_many({"submission_id": submission_id}, {"$set": {"published_by": actor_id}})
    else:
        db.submissions.update_one({"_id": submission_id},
                                  {"$set": {"published_by": None, "unpublished_by": actor_id},
                                   "$push": {"publication_log": entry}})
        db.evaluations.update_many({"submission_id": submission_id}, {"$set": {"published_by": None}})
