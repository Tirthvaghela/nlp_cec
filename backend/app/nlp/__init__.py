"""AnswerWise NLP evaluation engine.

The package is deliberately independent of FastAPI and MongoDB so that it can be
unit-tested, calibrated and evaluated offline (see ``backend/evaluation``).

Public entry points:

* :func:`app.nlp.scorer.evaluate_answer` - score one answer against one question.
* :class:`app.nlp.config.EvaluationConfig` - every tunable parameter of the engine.
* :class:`app.nlp.rubric.QuestionSpec` / :class:`app.nlp.rubric.RubricItem` - rubric model.
"""

from app.nlp.config import ENGINE_VERSION, EvaluationConfig
from app.nlp.rubric import QuestionSpec, RubricError, RubricItem
from app.nlp.scorer import EvaluationResult, evaluate_answer

__all__ = [
    "ENGINE_VERSION",
    "EvaluationConfig",
    "EvaluationResult",
    "QuestionSpec",
    "RubricError",
    "RubricItem",
    "evaluate_answer",
]
