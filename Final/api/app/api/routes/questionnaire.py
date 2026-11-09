"""Questionnaire (Contract.md §2.3, PRD FR-5 – FR-7)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ContainerDep, CurrentUser, DbDep
from app.api.schemas import AnswerRequest, AnswerSaved, AnswersOut, QuestionnaireOut
from app.services import completeness_service, questionnaire_service

router = APIRouter(prefix="/api/questionnaire", tags=["questionnaire"])


@router.get("")
async def get_questionnaire(_user: CurrentUser, container: ContainerDep) -> QuestionnaireOut:
    questionnaire = questionnaire_service.questionnaire_for(container.settings)
    return QuestionnaireOut(
        version=questionnaire.version,
        sections=questionnaire.public_sections(),
        attribution=questionnaire.attribution(),
    )


@router.get("/answers")
async def get_answers(user: CurrentUser, container: ContainerDep, db: DbDep) -> AnswersOut:
    questionnaire = questionnaire_service.questionnaire_for(container.settings)
    answers = questionnaire.known_answers(await questionnaire_service.get_answers(db, user.id))
    return AnswersOut(answers=answers, answered=len(answers), total=len(questionnaire))


@router.put("/answers/{question_id}")
async def save_answer(
    question_id: str, body: AnswerRequest, user: CurrentUser, container: ContainerDep, db: DbDep
) -> AnswerSaved:
    settings = container.settings
    await questionnaire_service.save_answer(db, user.id, question_id, body.value, settings)
    return AnswerSaved(completeness=await completeness_service.completeness(db, user.id, settings))
