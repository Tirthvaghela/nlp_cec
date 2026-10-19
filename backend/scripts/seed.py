"""Seed a local development database with demonstration data.

Usage (from backend/):
    python -m scripts.seed           # refuses to run if the demo teacher already exists
    python -m scripts.seed --reset   # DROPS the configured database first (development only!)

Creates (all clearly marked as demo data, ``source: "seed"``):
  * 1 teacher and 4 students with the development credentials printed at the end
  * "NLP Unit 2: Text Preprocessing"   - published; submissions in every workflow state
  * "NLP Unit 3: Text Representation"  - published with a deadline; one pending submission,
                                          other students can still attempt it
  * "Machine Learning Basics"          - draft, to demonstrate the question/rubric editor
Answers are synthetic examples taken from evaluation/dataset.json; their AI scores are
produced by the real NLP engine during seeding.

These credentials are for local demos only - never use them in a real deployment.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app import deployment  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import ensure_indexes, get_db, now  # noqa: E402
from app.nlp.similarity import get_backend  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services.evaluation_service import evaluate_submission, publish_submission  # noqa: E402

TEACHER = {"name": "Prof. Meera Iyer", "email": "teacher@answerwise.dev", "password": "Teacher@123"}
STUDENTS = [
    {"name": "Aarav Shah", "email": "aarav@answerwise.dev"},
    {"name": "Diya Patel", "email": "diya@answerwise.dev"},
    {"name": "Kabir Mehta", "email": "kabir@answerwise.dev"},
    {"name": "Riya Nair", "email": "riya@answerwise.dev"},
]
STUDENT_PASSWORD = "Student@123"
OWN_COLLECTIONS = {"users", "assessments", "questions", "submissions", "evaluations", "evaluation_history", "enrollments",
                   "enrollment_events", deployment.MARKER_COLLECTION}
DEMO_DOMAIN = "@answerwise.dev"

LEVELS = {
    "Q1": {"excellent": "Defines tokens with examples, explains why it comes first and mentions tricky cases.",
           "satisfactory": "Correct definition but little on its role or special cases.",
           "needs_improvement": "Confuses tokenization with stemming or gives no definition."},
}


def load_dataset() -> dict:
    data = json.loads((BACKEND / "evaluation" / "dataset.json").read_text(encoding="utf-8"))
    return {q["id"]: q for q in data["questions"]}


def answer(ds: dict, answer_id: str) -> str:
    qid = answer_id.split("-")[0]
    return next(a["text"] for a in ds[qid]["answers"] if a["id"] == answer_id)


def add_question(db, assessment_id, order: int, q: dict) -> dict:
    ts = now()
    doc = {
        "assessment_id": assessment_id,
        "order": order,
        "text": q["text"],
        "max_marks": float(q["max_marks"]),
        "reference_answer": q["reference_answer"],
        "rubric": [{"id": i["id"], "label": i["label"], "description": i["description"],
                    "marks": float(i["marks"]), "keywords": i.get("keywords", [])} for i in q["rubric"]],
        "rubric_levels": LEVELS.get(q["id"], {"excellent": "", "satisfactory": "", "needs_improvement": ""}),
        "settings": {},
        "rubric_version": 1,
        "created_at": ts,
        "updated_at": ts,
    }
    doc["_id"] = db.questions.insert_one(doc).inserted_id
    return doc


def add_assessment(db, teacher_id, title, subject, instructions, status, deadline=None) -> dict:
    ts = now()
    doc = {"teacher_id": teacher_id, "title": title, "subject": subject, "instructions": instructions,
           "status": status, "deadline": deadline, "assigned_student_ids": [], "created_at": ts, "updated_at": ts,
           "published_at": ts if status == "published" else None}
    doc["_id"] = db.assessments.insert_one(doc).inserted_id
    return doc


def add_submission(db, assessment, questions, student, answer_texts, ago_hours: float) -> dict:
    ts = now() - timedelta(hours=ago_hours)
    doc = {
        "assessment_id": assessment["_id"],
        "student_id": student["_id"],
        "answers": [{"question_id": str(q["_id"]), "text": t} for q, t in zip(questions, answer_texts)],
        "status": "submitted",
        "created_at": ts - timedelta(minutes=40),
        "updated_at": ts,
        "submitted_at": ts,
        "published_at": None,
        "source": "seed",
    }
    doc["_id"] = db.submissions.insert_one(doc).inserted_id
    return doc


def check_seed_target(db, settings, reset: bool) -> None:
    """Decide from the TARGET DATABASE (not only this shell's environment) whether demo data may be written.

    Fails closed (SystemExit) when: this process is configured for production or the pilot; the database carries the
    pilot marker or an unknown marker; the database cannot be inspected; or it holds data that is not identifiably
    demo data. Allowed: an empty database, a database marked "development" by an earlier seed, and - with --reset -
    an unmarked database whose users are all demo accounts (the pre-marker development database)."""
    if settings.environment == "production" or settings.pilot_mode:
        sys.exit("Refusing to seed: demo accounts have published passwords and must never exist in a production or "
                 "pilot database.")
    try:
        marker = deployment.read_marker(db)
        collections = set(db.list_collection_names())
        demo_problems = _not_demo_only(db, collections) if (collections and marker is None) else []
    except Exception as exc:  # noqa: BLE001 - cannot verify the target: do not write
        sys.exit(f"Refusing to seed: the target database could not be inspected ({type(exc).__name__}).")
    kind = marker.get("kind") if isinstance(marker, dict) else None
    if kind == deployment.PILOT:
        sys.exit(f"Refusing to seed '{db.name}': it is marked as a PILOT database. Demo accounts must never exist there.")
    if marker is not None and (problems := deployment.marker_problems(marker, deployment.DEVELOPMENT)):
        sys.exit(f"Refusing to seed '{db.name}': unknown deployment marker or ambiguous identity ({'; '.join(problems)}).")
    foreign = collections - OWN_COLLECTIONS
    if foreign:
        sys.exit(f"Refusing to seed '{db.name}': it contains collections that do not belong to AnswerWise "
                 f"({', '.join(sorted(foreign))}). Check MONGODB_DB in backend/.env.")
    if kind == deployment.DEVELOPMENT or not collections:
        return
    # Unmarked, non-empty database: only a reset of identifiable demo data is allowed.
    if not reset:
        sys.exit(f"Refusing to seed '{db.name}': it already contains data. Run with --reset to recreate demo data "
                 "(only allowed when every account is a demo account).")
    if demo_problems:
        sys.exit(f"Refusing to reset '{db.name}': it is not marked as a development database and does not hold only "
                 f"identifiable demo data ({'; '.join(demo_problems)}). It may be a pilot or real database.")


def _not_demo_only(db, collections: set[str]) -> list[str]:
    """Why an UNMARKED, non-empty database is not identifiably the old demo database (V8). Every collection is
    checked, not only users: demo users only, demo-seeded assessments/submissions only, and every question,
    evaluation and history entry belonging to them. Anything else - including data without any user - is refused."""
    problems = []
    demo_re = {"$regex": f"{DEMO_DOMAIN.replace('.', '[.]')}$"}
    users = db.users.count_documents({})
    if not users:
        problems.append("no demo accounts")
    elif db.users.count_documents({"email": {"$not": demo_re}}):
        problems.append("non-demo accounts")
    seeded_a = [a["_id"] for a in db.assessments.find({"source": "seed"}, {"_id": 1})]
    seeded_s = [s["_id"] for s in db.submissions.find({"source": "seed"}, {"_id": 1})]
    if db.assessments.count_documents({"source": {"$ne": "seed"}}):
        problems.append("assessments not created by the seed")
    if db.submissions.count_documents({"source": {"$ne": "seed"}}):
        problems.append("submissions not created by the seed")
    if db.questions.count_documents({"assessment_id": {"$nin": seeded_a}}):
        problems.append("questions outside seeded assessments")
    for coll in ("evaluations", "evaluation_history"):
        if db[coll].count_documents({"submission_id": {"$nin": seeded_s}}):
            problems.append(f"{coll} outside seeded submissions")
    for coll in ("enrollments", "enrollment_events", deployment.MARKER_COLLECTION):
        if coll in collections and db[coll].count_documents({}):
            problems.append(f"{coll} present")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="drop the configured database before seeding")
    args = ap.parse_args()

    settings = get_settings()
    if settings.environment == "production" or settings.pilot_mode:  # before connecting at all
        check_seed_target(None, settings, args.reset)
    db = get_db()
    check_seed_target(db, settings, args.reset)
    if args.reset:
        print(f"Dropping database '{settings.mongodb_db}' ...")
        db.client.drop_database(settings.mongodb_db)
    elif db.users.find_one({"email": TEACHER["email"]}):
        sys.exit("Demo data already present. Run with --reset to recreate it (this drops the database).")
    ensure_indexes(db)
    if not deployment.read_marker(db):
        deployment.write_marker(db, deployment.DEVELOPMENT)  # later seeds/resets recognise this as development data

    print("Loading NLP model (first run may take a minute) ...")
    backend = get_backend(settings.similarity_backend, settings.embedding_model)
    print(f"  similarity backend: {backend.name} ({backend.model_name})")

    ts = now()
    teacher = {"name": TEACHER["name"], "email": TEACHER["email"], "password_hash": hash_password(TEACHER["password"]),
               "role": "teacher", "created_at": ts, "updated_at": ts}
    teacher["_id"] = db.users.insert_one(teacher).inserted_id
    students = []
    for s in STUDENTS:
        doc = {**s, "password_hash": hash_password(STUDENT_PASSWORD), "role": "student", "created_at": ts, "updated_at": ts}
        doc["_id"] = db.users.insert_one(doc).inserted_id
        students.append(doc)
    aarav, diya, kabir, riya = students

    ds = load_dataset()

    # --- Assessment 1: all workflow states -------------------------------------------------
    a1 = add_assessment(db, teacher["_id"], "NLP Unit 2: Text Preprocessing", "Natural Language Processing",
                        "Answer all three questions in your own words. Marks are shown next to each question. "
                        "Write complete sentences and give examples where helpful.", "published")
    q1 = [add_question(db, a1["_id"], n, ds[qid]) for n, qid in enumerate(["Q1", "Q7", "Q3"])]
    plan = [
        (aarav, ["Q1-a1", "Q7-a1", "Q3-a1"], "publish"),
        (diya, ["Q1-a4", "Q7-a6", "Q3-a5"], "publish"),
        (kabir, ["Q1-a2", "Q7-a2", "Q3-a7"], "evaluate"),
        (riya, ["Q1-a5", "Q7-a3", "Q3-a4"], "submit"),
    ]
    for n, (student, ids, stage) in enumerate(plan):
        sub = add_submission(db, a1, q1, student, [answer(ds, i) for i in ids], ago_hours=72 - n * 5)
        if stage in ("evaluate", "publish"):
            evaluate_submission(db, sub, reason="initial")
        if stage == "publish":
            if student is diya:
                # Demonstrate a teacher adjustment of an AI suggestion.
                ev = db.evaluations.find_one({"submission_id": sub["_id"], "question_id": q1[0]["_id"]})
                adjusted = min(ev["max_marks"], ev["ai_score"] + 0.5)
                db.evaluations.update_one({"_id": ev["_id"]}, {"$set": {
                    "teacher_score": adjusted, "status": "reviewed", "reviewed_at": now(), "reviewed_by": teacher["_id"],
                    "adjustment_reason": "Spelling mistakes do not affect understanding; the special cases point is adequately covered.",
                    "teacher_feedback": "Good understanding. Please proof-read for spelling before submitting."}})
            publish_submission(db, db.submissions.find_one({"_id": sub["_id"]}))

    # --- Assessment 2: open for attempts --------------------------------------------------
    a2 = add_assessment(db, teacher["_id"], "NLP Unit 3: Text Representation", "Natural Language Processing",
                        "This assessment covers vector representations of text. Attempt all questions. "
                        "You can save a draft and come back before the deadline.", "published",
                        deadline=now() + timedelta(days=14))
    q2 = [add_question(db, a2["_id"], n, ds[qid]) for n, qid in enumerate(["Q2", "Q5", "Q9"])]
    add_submission(db, a2, q2, aarav, [answer(ds, i) for i in ["Q2-a4", "Q5-a4", "Q9-a2"]], ago_hours=6)

    # --- Assessment 3: draft -------------------------------------------------------------
    a3 = add_assessment(db, teacher["_id"], "Machine Learning Basics", "Machine Learning",
                        "Short descriptive questions on core machine-learning ideas.", "draft")
    add_question(db, a3["_id"], 0, ds["Q10"])

    print("\nDemo data created (synthetic, for local development only):")
    print(f"  Teacher : {TEACHER['email']} / {TEACHER['password']}")
    for s in STUDENTS:
        print(f"  Student : {s['email']} / {STUDENT_PASSWORD}")
    print("\nChange or remove these accounts before any real deployment.")


if __name__ == "__main__":
    main()
