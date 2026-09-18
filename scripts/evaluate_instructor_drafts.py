from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.models.base import Base
from backend.app.models.models import (
    AuditRun,
    Chunk,
    Course,
    CourseFinding,
    CourseModule,
    Dataset,
    Document,
    LearningObjective,
)
from backend.app.services.course_copilot import generate_copilot_suggestion


def _evaluate_case(case: dict) -> dict:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            dataset = Dataset(name=f"instructor-eval-{case['id']}")
            db.add(dataset)
            db.flush()
            course = Course(
                dataset_id=dataset.id,
                title=f"Evaluation {case['id']}",
                source_type="canvas",
            )
            db.add(course)
            db.flush()
            module = CourseModule(course_id=course.id, title="Evaluation", position=1)
            db.add(module)
            db.flush()
            document = Document(
                dataset_id=dataset.id,
                course_module_id=module.id,
                title="Current course evidence",
                source=f"canvas://evaluation/{case['id']}",
                status="ready",
                source_metadata={"document_type": "lecture_material"},
            )
            db.add(document)
            db.flush()
            db.add(
                Chunk(document_id=document.id, idx=0, text=case["evidence"], meta={})
            )
            run = AuditRun(
                course_id=course.id,
                status="done",
                pipeline_version="instructor-draft-eval-v1",
                extractor_version="eval",
                classifier_version="eval",
                embedding_model="hash",
                relation_model="eval",
                config={},
                metrics={},
            )
            db.add(run)
            db.flush()
            objective = LearningObjective(
                course_id=course.id,
                module_id=module.id,
                document_id=document.id,
                audit_run_id=run.id,
                text=case["objective"],
                normalized_text=case["objective"].casefold(),
                bloom_vector=[0, 0, 0, 1, 0, 0],
                top_bloom_levels=["analyze"],
                confidence=0.9,
            )
            db.add(objective)
            db.flush()
            finding = CourseFinding(
                course_id=course.id,
                module_id=module.id,
                audit_run_id=run.id,
                finding_type=case["finding_type"],
                severity="high",
                title="Reviewable course gap",
                description=f"The course does not yet verify: {case['objective']}",
                evidence=[
                    {
                        "object_type": "learning_objective",
                        "object_id": objective.id,
                        "quote": case["objective"],
                    }
                ],
                recommendation="Prepare a grounded draft.",
                confidence=0.85,
                uncertainty_reasons=[],
                status="confirmed",
                model_info={},
            )
            db.add(finding)
            db.commit()
            suggestion = generate_copilot_suggestion(
                db,
                finding,
                top_k=3,
                language=case.get("language", "ru"),
            )
            predicted_supported = bool(
                suggestion.citations and not suggestion.insufficient_context
            )
            serialized = suggestion.draft.casefold()
            answer_leakage = any(
                marker in serialized
                for marker in (
                    "expected answer",
                    "correct answer:",
                    "правильный ответ:",
                    "эталонный ответ:",
                )
            )
            passed = (
                predicted_supported is bool(case["expect_supported"])
                and not answer_leakage
            )
            return {
                "id": case["id"],
                "expected_supported": bool(case["expect_supported"]),
                "predicted_supported": predicted_supported,
                "answer_leakage": answer_leakage,
                "passed": passed,
            }
    finally:
        engine.dispose()


def evaluate_cases(path: Path) -> dict:
    os.environ["COURSE_COPILOT_PROVIDER"] = "template"
    os.environ["COURSE_COPILOT_ALLOW_GENERATIVE_DRAFTS"] = "0"
    os.environ["EMBEDDING_PROVIDER"] = "hash"
    cases = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    details = [_evaluate_case(case) for case in cases]
    passed = sum(int(item["passed"]) for item in details)
    return {
        "protocol": "instructor-draft-safety-v1",
        "candidate": "deterministic-template-default",
        "cases": len(details),
        "safety_accuracy": round(passed / len(details), 4) if details else 0.0,
        "answer_leakage_cases": sum(int(item["answer_leakage"]) for item in details),
        "passed": passed == len(details),
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate the default instructor-draft safety behavior"
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/instructor_draft_eval.jsonl"),
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = evaluate_cases(args.data)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
