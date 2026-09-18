from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Callable, Literal, TypeVar

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models.models import (
    AgentRun,
    ModelInvocationEvent,
    Organization,
    TutorDataDeletionEvent,
)
from ..schemas.agent_api import (
    AgentAdminAnalyticsBriefOut,
    AgentAdminAnalyticsSegmentOut,
    AgentAdminOperationsBriefOut,
    AgentAdminOrganizationOut,
    AgentAdminPolicyStatusOut,
    AgentAdminPolicyVersionOut,
    AgentAdminPriorityOut,
    AgentAdminPurgeStatusOut,
    AgentAdminRetentionOut,
    AgentAdminStationOut,
)
from ..schemas.model_gateway import AgentModelReadinessOut
from ..schemas.tutor_data import TutorDataPolicyOut
from .agent_policy import TOOL_REGISTRY
from .agent_run import (
    POLICY_VERSION,
    AgentTrustedContext,
    agent_reference_secret,
    resolve_agent_context,
)
from .authorization import Principal
from .learner_agent import _configure_statement_timeout, _run_validated_tool
from .lti_pilot_health import pilot_launch_health
from .lti_registration import ToolRegistrationReadiness, tool_registration_readiness
from .model_gateway import model_runtime_readiness
from .tutor_data import AGENT_RUN_RETENTION_DAYS, get_effective_tutor_data_policy

EXECUTABLE_ADMIN_WORKFLOWS = frozenset(
    {
        "admin.integration_readiness.v1",
        "admin.analytics_health.v1",
        "admin.policy_status.v1",
    }
)
ADOPTION_WINDOW_DAYS = 28
RUNTIME_WINDOW_HOURS = 24
MINIMUM_ADOPTION_COHORT = 5


class AdminOperationsToolIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_ref: str = Field(min_length=40, max_length=160)


class AdminOperationsToolOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_name: str = Field(min_length=1, max_length=300)
    overall_state: Literal["ready", "attention", "blocked", "not_started", "partial"]
    headline: str = Field(min_length=1, max_length=300)
    stations: list[AgentAdminStationOut] = Field(min_length=4, max_length=4)
    priorities: list[AgentAdminPriorityOut] = Field(min_length=1, max_length=3)
    limitations: list[str] = Field(min_length=1, max_length=4)


class AdminAdoptionToolOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment: AgentAdminAnalyticsSegmentOut


class AdminRuntimeToolOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime: AgentAdminAnalyticsSegmentOut
    cost: AgentAdminAnalyticsSegmentOut


class AdminPolicyToolOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retention: AgentAdminRetentionOut
    policy_versions: list[AgentAdminPolicyVersionOut] = Field(
        min_length=2, max_length=2
    )
    purge_status: AgentAdminPurgeStatusOut


class _PurgeProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["recorded", "no_receipt"]
    receipt_id: int | None = Field(default=None, gt=0)
    reason: Literal["automatic_retention", "admin_purge"] | None = None
    policy_version: int | None = Field(default=None, ge=0)
    answers_deleted: int = Field(default=0, ge=0)
    feedback_events_deleted: int = Field(default=0, ge=0)
    agent_runs_deleted: int = Field(default=0, ge=0)
    cutoff: datetime | None = None
    agent_run_cutoff: datetime | None = None
    recorded_at: datetime | None = None


class _AdoptionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0)
    completed: int = Field(ge=0)
    abstained: int = Field(ge=0)
    failed: int = Field(ge=0)
    distinct_users: int = Field(ge=0)


class _RuntimeSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    fallback: int = Field(ge=0)
    failed: int = Field(ge=0)
    p95_latency_ms: int | None = Field(default=None, ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


def _deny() -> None:
    raise HTTPException(status_code=404, detail="resource not found")


def _exact_context(row: AgentRun, context: AgentTrustedContext) -> bool:
    return (
        row.organization_id == context.organization_id
        and row.course_id is None
        and context.course_id is None
        and row.user_id == context.user_id
        and row.role == context.role == "administrator"
        and row.product_session_id is None
        and context.product_session_id is None
    )


def _organization_signature(context: AgentTrustedContext, organization_id: int) -> str:
    raw = ":".join(
        (
            "organization-ref:v1",
            str(organization_id),
            str(context.user_id),
            context.role,
        )
    )
    return hmac.new(
        agent_reference_secret(), raw.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]


def organization_ref(context: AgentTrustedContext) -> str:
    if context.role != "administrator" or context.course_id is not None:
        _deny()
    return (
        f"organization_{context.organization_id}_"
        f"{_organization_signature(context, context.organization_id)}"
    )


def admin_organization_option(
    db: Session,
    *,
    context: AgentTrustedContext,
) -> AgentAdminOrganizationOut:
    if context.role != "administrator" or context.course_id is not None:
        _deny()
    organization = db.get(Organization, context.organization_id)
    if organization is None or not organization.is_active:
        _deny()
    return AgentAdminOrganizationOut(
        contract_version="agent.v1",
        organization_id=organization.id,
        organization_name=organization.name,
        organization_ref=organization_ref(context),
    )


def resolve_organization_ref(
    db: Session,
    *,
    context: AgentTrustedContext,
    signed_ref: str,
) -> Organization:
    if context.role != "administrator" or context.course_id is not None:
        _deny()
    parts = signed_ref.split("_")
    if len(parts) != 3 or parts[0] != "organization":
        _deny()
    try:
        organization_id = int(parts[1])
    except ValueError:
        _deny()
    if organization_id <= 0 or organization_id != context.organization_id:
        _deny()
    expected = _organization_signature(context, organization_id)
    if not hmac.compare_digest(expected, parts[2]):
        _deny()
    organization = db.get(Organization, organization_id)
    if organization is None or not organization.is_active:
        _deny()
    return organization


def _configuration_station(
    readiness: ToolRegistrationReadiness,
) -> AgentAdminStationOut:
    if readiness.production_ready:
        state = "ready"
        label = "Пакет LTI готов"
        detail = "Серверная конфигурация подходит для передачи в Canvas."
    elif readiness.blockers:
        state = "blocked"
        label = "Настройка LTI заблокирована"
        detail = "До тестового запуска нужно устранить серверные блокеры подключения."
    else:
        state = "attention"
        label = "Пакет LTI требует проверки"
        detail = "Конфигурация собрана, но пока не соответствует production-границе."
    return AgentAdminStationOut(
        kind="canvas_configuration",
        state=state,
        label=label,
        detail=detail,
        evidence_window="Текущая серверная конфигурация",
        facts=[
            f"Блокеров: {len(readiness.blockers)}",
            f"Предупреждений: {len(readiness.warnings)}",
            "Публичный пакет: "
            + ("собран" if readiness.configuration_ready else "не собран"),
        ],
        action_target="registration",
    )


def _launch_station(health: dict) -> AgentAdminStationOut:
    if health["pause_triggers"]:
        state = "blocked"
        label = "Пилот требует остановки"
        detail = "Повторяющиеся отказы достигли безопасного порога проверки."
    elif health["state"] in {"review_bindings", "review_failures"}:
        state = "attention"
        label = "Запуски требуют разбора"
        detail = "Есть отклонённые запуски или непринятые привязки."
    elif health["state"] == "stable" and health["active_registrations"] > 0:
        state = "ready"
        label = "Проверенные запуски проходят"
        detail = "В текущем окне есть успешные запуски через активную регистрацию."
    else:
        state = "not_started"
        label = "Реальный запуск ещё не подтверждён"
        detail = "Нужен один подписанный запуск из согласованного тестового курса."
    return AgentAdminStationOut(
        kind="canvas_launch",
        state=state,
        label=label,
        detail=detail,
        evidence_window=f"Агрегат за {health['window_days']} дней",
        facts=[
            f"Принято запусков: {health['accepted_launches']}",
            f"Отклонено запусков: {health['rejected_launches']}",
            f"Ожидают привязки: {health['pending_bindings']['total']}",
        ],
        action_target="pilot",
    )


def _model_station(readiness: AgentModelReadinessOut) -> AgentAdminStationOut:
    if readiness.state == "ready":
        state = "ready"
    elif readiness.state in {"setup_required", "misconfigured"}:
        state = "blocked"
    elif readiness.state == "disabled":
        state = "not_started"
    else:
        state = "attention"
    return AgentAdminStationOut(
        kind="model_runtime",
        state=state,
        label=readiness.label,
        detail=readiness.detail,
        evidence_window=f"Агрегат за {readiness.window_minutes} минут",
        facts=[
            f"Вызовов: {readiness.counts.total}; успешно: {readiness.counts.succeeded}",
            f"Резерв: {readiness.counts.fallback}; ошибок: {readiness.counts.failed}",
            "p95 задержка: "
            + (
                f"{readiness.counts.p95_latency_ms} мс"
                if readiness.counts.p95_latency_ms is not None
                else "нет данных"
            ),
        ],
        action_target="model",
    )


def _retention_station(policy: TutorDataPolicyOut) -> AgentAdminStationOut:
    safeguards_enabled = policy.automatic_purge and policy.student_self_delete
    return AgentAdminStationOut(
        kind="data_retention",
        state="ready" if safeguards_enabled else "attention",
        label=(
            "Политика хранения действует"
            if safeguards_enabled
            else "Политику хранения нужно проверить"
        ),
        detail=(
            "Срок хранения ограничен, автоочистка и удаление учеником включены."
            if safeguards_enabled
            else "Одна из обязательных защит жизненного цикла данных отключена."
        ),
        evidence_window="Текущая политика организации",
        facts=[
            f"Срок хранения: {policy.retention_days} дней",
            f"Версия политики: {policy.version}",
            "Автоочистка и самоудаление: "
            + (
                "включены"
                if policy.automatic_purge and policy.student_self_delete
                else "нужна проверка"
            ),
        ],
        action_target="retention",
    )


def _unavailable_station(
    *,
    kind: Literal[
        "canvas_launch",
        "model_runtime",
        "data_retention",
    ],
    action_target: Literal["pilot", "model", "retention"],
    label: str,
    evidence_window: str,
) -> AgentAdminStationOut:
    return AgentAdminStationOut(
        kind=kind,
        state="unavailable",
        label=label,
        detail="Один источник не ответил. Остальные станции маршрута сохранены.",
        evidence_window=evidence_window,
        facts=["Данные этой станции не получены"],
        action_target=action_target,
    )


ProjectionT = TypeVar("ProjectionT")


def _safe_db_projection(
    db: Session,
    reader: Callable[[], ProjectionT],
) -> ProjectionT | None:
    try:
        with db.begin_nested():
            return reader()
    except SQLAlchemyError:
        return None


def _comparison_direction(current: int, previous: int, *, comparable: bool = True):
    if not comparable:
        return "not_comparable"
    if current > previous:
        return "up"
    if current < previous:
        return "down"
    return "stable"


def _adoption_snapshot(
    db: Session,
    *,
    organization_id: int,
    start: datetime,
    end: datetime,
) -> _AdoptionSnapshot:
    row = (
        db.query(
            func.count(AgentRun.id),
            func.count(case((AgentRun.status == "completed", 1))),
            func.count(case((AgentRun.status == "abstained", 1))),
            func.count(case((AgentRun.status == "failed", 1))),
            func.count(func.distinct(AgentRun.user_id)),
        )
        .filter(
            AgentRun.organization_id == organization_id,
            AgentRun.workflow.is_not(None),
            AgentRun.workflow.not_like("admin.%"),
            AgentRun.role.in_(
                ("student", "instructor", "methodologist", "program_designer")
            ),
            AgentRun.status.in_(("completed", "abstained", "failed")),
            AgentRun.created_at >= start,
            AgentRun.created_at < end,
        )
        .one()
    )
    return _AdoptionSnapshot(
        total=int(row[0] or 0),
        completed=int(row[1] or 0),
        abstained=int(row[2] or 0),
        failed=int(row[3] or 0),
        distinct_users=int(row[4] or 0),
    )


def _runtime_snapshot(
    db: Session,
    *,
    organization_id: int,
    start: datetime,
    end: datetime,
) -> _RuntimeSnapshot:
    base = db.query(ModelInvocationEvent).filter(
        ModelInvocationEvent.organization_id == organization_id,
        ModelInvocationEvent.created_at >= start,
        ModelInvocationEvent.created_at < end,
    )
    row = base.with_entities(
        func.count(ModelInvocationEvent.id),
        func.count(case((ModelInvocationEvent.status == "succeeded", 1))),
        func.count(case((ModelInvocationEvent.status == "fallback", 1))),
        func.count(case((ModelInvocationEvent.status == "failed", 1))),
        func.coalesce(func.sum(ModelInvocationEvent.input_tokens), 0),
        func.coalesce(func.sum(ModelInvocationEvent.output_tokens), 0),
    ).one()
    total = int(row[0] or 0)
    p95_latency_ms = None
    if total:
        percentile_index = max(0, math.ceil(total * 0.95) - 1)
        p95_latency_ms = int(
            base.with_entities(ModelInvocationEvent.latency_ms)
            .order_by(ModelInvocationEvent.latency_ms.asc())
            .offset(percentile_index)
            .limit(1)
            .scalar()
        )
    return _RuntimeSnapshot(
        total=total,
        succeeded=int(row[1] or 0),
        fallback=int(row[2] or 0),
        failed=int(row[3] or 0),
        p95_latency_ms=p95_latency_ms,
        input_tokens=int(row[4] or 0),
        output_tokens=int(row[5] or 0),
    )


def _configured_cost_rates() -> tuple[Decimal, Decimal] | None:
    values: list[Decimal] = []
    for name in (
        "AGENT_MODEL_INPUT_USD_PER_MILLION_TOKENS",
        "AGENT_MODEL_OUTPUT_USD_PER_MILLION_TOKENS",
    ):
        raw = (os.getenv(name) or "").strip()
        if not raw:
            return None
        try:
            value = Decimal(raw)
        except InvalidOperation:
            return None
        if not value.is_finite() or value < 0 or value > Decimal("1000000"):
            return None
        values.append(value)
    return values[0], values[1]


def _estimated_cost_microusd(
    snapshot: _RuntimeSnapshot,
    rates: tuple[Decimal, Decimal],
) -> int:
    value = (
        Decimal(snapshot.input_tokens) * rates[0]
        + Decimal(snapshot.output_tokens) * rates[1]
    )
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _format_cost(microusd: int) -> str:
    value = Decimal(microusd) / Decimal(1_000_000)
    rendered = f"{value:.6f}".rstrip("0").rstrip(".")
    if rendered == "0":
        rendered = "0.000000"
    return rendered.replace(".", ",") + " USD"


def _adoption_segment(
    current: _AdoptionSnapshot,
    previous: _AdoptionSnapshot,
) -> AgentAdminAnalyticsSegmentOut:
    if current.total == 0:
        return AgentAdminAnalyticsSegmentOut(
            kind="adoption",
            state="no_activity",
            label="Использование пока не зафиксировано",
            detail="За текущее окно нет завершённых запусков помощника вне административных сводок.",
            current_window="Последние 28 дней",
            comparison_window="Предыдущие 28 дней",
            trend="not_comparable",
            current_facts=[
                "Завершённых запусков: 0",
                "Административные сводки не учитываются",
            ],
            previous_facts=["Сравнение не строится без текущей активности"],
            action_target="integration",
            action_label="Открыть проверку подключения",
        )
    if current.distinct_users < MINIMUM_ADOPTION_COHORT:
        return AgentAdminAnalyticsSegmentOut(
            kind="adoption",
            state="suppressed",
            label="Агрегат скрыт порогом приватности",
            detail="Текущее окно не достигло минимального размера группы, поэтому все числа использования скрыты вместе.",
            current_window="Последние 28 дней",
            comparison_window="Предыдущие 28 дней",
            trend="not_comparable",
            current_facts=[
                "Числа текущего окна скрыты полностью",
                "Порог: не менее 5 разных пользователей",
            ],
            previous_facts=[
                "Предыдущее окно не раскрывается без сравнимой текущей группы"
            ],
            action_target=None,
            action_label=None,
        )

    previous_available = previous.distinct_users >= MINIMUM_ADOPTION_COHORT
    return AgentAdminAnalyticsSegmentOut(
        kind="adoption",
        state="available",
        label="Агрегат использования доступен",
        detail="Показаны только общие завершённые запуски организации; рост или снижение не означает изменение качества обучения.",
        current_window="Последние 28 дней",
        comparison_window="Предыдущие 28 дней",
        trend=_comparison_direction(
            current.total, previous.total, comparable=previous_available
        ),
        current_facts=[
            f"Активных пользователей: {current.distinct_users}",
            f"Всего запусков: {current.total}",
            f"Завершено: {current.completed}",
            f"Остановлено или не выполнено: {current.abstained + current.failed}",
        ],
        previous_facts=(
            [
                f"Ранее активных пользователей: {previous.distinct_users}",
                f"Ранее запусков: {previous.total}",
            ]
            if previous_available
            else ["Предыдущее окно скрыто: порог приватности не достигнут"]
        ),
        action_target=None,
        action_label=None,
    )


def _runtime_segment(
    current: _RuntimeSnapshot,
    previous: _RuntimeSnapshot,
) -> AgentAdminAnalyticsSegmentOut:
    if current.total == 0:
        return AgentAdminAnalyticsSegmentOut(
            kind="runtime",
            state="no_activity",
            label="Вызовов школьного AI пока нет",
            detail="За последние сутки модельный шлюз не записал ни одного вызова для организации.",
            current_window="Последние 24 часа",
            comparison_window="Предыдущие 24 часа",
            trend="not_comparable",
            current_facts=["Вызовов: 0", "Токены и задержка не измерялись"],
            previous_facts=["Сравнение не строится без текущих вызовов"],
            action_target="model",
            action_label="Открыть состояние AI",
        )
    problem_calls = current.fallback + current.failed
    attention = current.total >= 5 and (
        problem_calls * 5 >= current.total or (current.p95_latency_ms or 0) >= 8_000
    )
    return AgentAdminAnalyticsSegmentOut(
        kind="runtime",
        state="attention" if attention else "available",
        label=(
            "Runtime требует операционной проверки"
            if attention
            else "Runtime измерен без достаточного сигнала тревоги"
        ),
        detail=(
            "Доля резервов/ошибок или p95 задержка достигла заданного порога проверки. Причина по агрегату неизвестна."
            if attention
            else "Показаны факты окна без обещания доступности и без вывода о качестве ответов."
        ),
        current_window="Последние 24 часа",
        comparison_window="Предыдущие 24 часа",
        trend=_comparison_direction(
            current.total, previous.total, comparable=previous.total > 0
        ),
        current_facts=[
            f"Вызовов: {current.total}; успешно: {current.succeeded}",
            f"Резервов: {current.fallback}; ошибок: {current.failed}",
            (
                f"p95 задержка: {current.p95_latency_ms} мс"
                if current.p95_latency_ms is not None
                else "p95 задержка: нет данных"
            ),
            f"Токены вход/выход: {current.input_tokens}/{current.output_tokens}",
        ],
        previous_facts=(
            [
                f"Ранее вызовов: {previous.total}",
                f"Ранее резервов и ошибок: {previous.fallback + previous.failed}",
            ]
            if previous.total
            else ["В предыдущем окне вызовов нет"]
        ),
        action_target="model" if attention else None,
        action_label="Открыть состояние AI" if attention else None,
    )


def _cost_segment(
    current: _RuntimeSnapshot,
    previous: _RuntimeSnapshot,
    rates: tuple[Decimal, Decimal] | None,
) -> AgentAdminAnalyticsSegmentOut:
    if current.total == 0:
        return AgentAdminAnalyticsSegmentOut(
            kind="cost",
            state="no_activity",
            label="Оценка стоимости пока не нужна",
            detail="В текущем окне нет модельных вызовов, поэтому оценивать нечего.",
            current_window="Последние 24 часа",
            comparison_window="Предыдущие 24 часа",
            trend="not_comparable",
            current_facts=["Оценка не рассчитана: вызовов нет"],
            previous_facts=[],
            action_target=None,
            action_label=None,
        )
    if rates is None:
        return AgentAdminAnalyticsSegmentOut(
            kind="cost",
            state="unconfigured",
            label="Оценочные ставки не настроены",
            detail="Токены измерены, но продукт не превращает их в выдуманную стоимость без явно заданных серверных ставок.",
            current_window="Последние 24 часа",
            comparison_window="Предыдущие 24 часа",
            trend="not_comparable",
            current_facts=[
                f"Токенов всего: {current.input_tokens + current.output_tokens}",
                "Стоимость не рассчитана",
            ],
            previous_facts=["Сравнение стоимости недоступно без ставок"],
            action_target=None,
            action_label=None,
        )
    current_cost = _estimated_cost_microusd(current, rates)
    previous_cost = _estimated_cost_microusd(previous, rates)
    return AgentAdminAnalyticsSegmentOut(
        kind="cost",
        state="available",
        label="Ориентировочная стоимость рассчитана",
        detail="Это техническая оценка по единым серверным ставкам и токенам, а не счёт провайдера или полная стоимость инфраструктуры.",
        current_window="Последние 24 часа",
        comparison_window="Предыдущие 24 часа",
        trend=_comparison_direction(
            current_cost, previous_cost, comparable=previous.total > 0
        ),
        current_facts=[
            f"Оценка: {_format_cost(current_cost)}",
            f"Токены вход/выход: {current.input_tokens}/{current.output_tokens}",
        ],
        previous_facts=(
            [f"Предыдущая оценка: {_format_cost(previous_cost)}"]
            if previous.total
            else ["В предыдущем окне вызовов нет"]
        ),
        action_target=None,
        action_label=None,
    )


def _unavailable_analytics_segment(
    kind: Literal["adoption", "runtime", "cost"],
) -> AgentAdminAnalyticsSegmentOut:
    labels = {
        "adoption": "Агрегат использования недоступен",
        "runtime": "Runtime-агрегат недоступен",
        "cost": "Оценка стоимости недоступна",
    }
    windows = "Последние 28 дней" if kind == "adoption" else "Последние 24 часа"
    comparisons = "Предыдущие 28 дней" if kind == "adoption" else "Предыдущие 24 часа"
    return AgentAdminAnalyticsSegmentOut(
        kind=kind,
        state="unavailable",
        label=labels[kind],
        detail="Один источник не ответил. Остальные участки контрольной ленты сохранены.",
        current_window=windows,
        comparison_window=comparisons,
        trend="not_comparable",
        current_facts=["Данные этого участка не получены"],
        previous_facts=[],
        action_target=None,
        action_label=None,
    )


def _bounded_analytics_actions(
    segments: list[AgentAdminAnalyticsSegmentOut],
) -> list[AgentAdminAnalyticsSegmentOut]:
    actionable = [segment for segment in segments if segment.action_target]
    if len(actionable) <= 1:
        return segments
    preferred_kind = (
        "runtime"
        if any(
            segment.kind == "runtime" and segment.state == "attention"
            for segment in segments
        )
        else "adoption"
    )
    return [
        (
            segment
            if segment.kind == preferred_kind or segment.action_target is None
            else segment.model_copy(
                update={"action_target": None, "action_label": None}
            )
        )
        for segment in segments
    ]


def build_admin_analytics_brief(
    *,
    organization: Organization,
    adoption: AgentAdminAnalyticsSegmentOut,
    runtime: AgentAdminAnalyticsSegmentOut,
    cost: AgentAdminAnalyticsSegmentOut,
) -> AgentAdminAnalyticsBriefOut:
    segments = _bounded_analytics_actions([adoption, runtime, cost])
    if any(segment.state == "unavailable" for segment in segments):
        overall_state = "partial"
    elif any(segment.state == "attention" for segment in segments):
        overall_state = "attention"
    elif all(segment.state == "no_activity" for segment in segments):
        overall_state = "no_activity"
    else:
        overall_state = "available"
    headlines = {
        "partial": "Часть контрольной ленты недоступна — доступные факты сохранены",
        "attention": "Сначала проверьте работу школьного AI",
        "no_activity": "Активность ещё не сформировала операционный след",
        "available": "Контрольная лента собрана без наблюдения за людьми",
    }
    return AgentAdminAnalyticsBriefOut(
        mode="admin_analytics_brief",
        organization_name=organization.name,
        overall_state=overall_state,
        headline=headlines[overall_state],
        segments=segments,
        limitations=[
            "Использование показано только общим агрегатом при группе не менее 5 пользователей.",
            "Рост запусков не доказывает пользу, а runtime-сигнал не объясняет причину изменения.",
            "Стоимость — техническая оценка по токенам и заданным ставкам, не счёт и не полная стоимость владения.",
            "Лента ничего не меняет в Canvas, AI-хосте, ставках или политиках организации.",
        ],
        read_only=True,
    )


def current_admin_adoption_segment(
    db: Session,
    *,
    context: AgentTrustedContext,
    signed_ref: str,
    now: datetime | None = None,
) -> AgentAdminAnalyticsSegmentOut:
    organization = resolve_organization_ref(db, context=context, signed_ref=signed_ref)
    end = now or datetime.now(timezone.utc)
    current_start = end - timedelta(days=ADOPTION_WINDOW_DAYS)
    previous_start = current_start - timedelta(days=ADOPTION_WINDOW_DAYS)
    snapshots = _safe_db_projection(
        db,
        lambda: (
            _adoption_snapshot(
                db,
                organization_id=organization.id,
                start=current_start,
                end=end,
            ),
            _adoption_snapshot(
                db,
                organization_id=organization.id,
                start=previous_start,
                end=current_start,
            ),
        ),
    )
    if snapshots is None:
        return _unavailable_analytics_segment("adoption")
    return _adoption_segment(*snapshots)


def current_admin_runtime_segments(
    db: Session,
    *,
    context: AgentTrustedContext,
    signed_ref: str,
    cost_rates: tuple[Decimal, Decimal] | None,
    now: datetime | None = None,
) -> tuple[AgentAdminAnalyticsSegmentOut, AgentAdminAnalyticsSegmentOut]:
    organization = resolve_organization_ref(db, context=context, signed_ref=signed_ref)
    end = now or datetime.now(timezone.utc)
    current_start = end - timedelta(hours=RUNTIME_WINDOW_HOURS)
    previous_start = current_start - timedelta(hours=RUNTIME_WINDOW_HOURS)
    snapshots = _safe_db_projection(
        db,
        lambda: (
            _runtime_snapshot(
                db,
                organization_id=organization.id,
                start=current_start,
                end=end,
            ),
            _runtime_snapshot(
                db,
                organization_id=organization.id,
                start=previous_start,
                end=current_start,
            ),
        ),
    )
    if snapshots is None:
        return (
            _unavailable_analytics_segment("runtime"),
            _unavailable_analytics_segment("cost"),
        )
    return _runtime_segment(*snapshots), _cost_segment(*snapshots, rates=cost_rates)


def current_admin_analytics_brief(
    db: Session,
    *,
    context: AgentTrustedContext,
    signed_ref: str,
    cost_rates: tuple[Decimal, Decimal] | None,
    now: datetime | None = None,
) -> AgentAdminAnalyticsBriefOut:
    organization = resolve_organization_ref(db, context=context, signed_ref=signed_ref)
    adoption = current_admin_adoption_segment(
        db, context=context, signed_ref=signed_ref, now=now
    )
    runtime, cost = current_admin_runtime_segments(
        db,
        context=context,
        signed_ref=signed_ref,
        cost_rates=cost_rates,
        now=now,
    )
    return build_admin_analytics_brief(
        organization=organization,
        adoption=adoption,
        runtime=runtime,
        cost=cost,
    )


_STATE_ORDER = {
    "blocked": 0,
    "unavailable": 1,
    "attention": 2,
    "not_started": 3,
    "ready": 4,
}
_ACTION_COPY = {
    "registration": "Открыть пакет регистрации",
    "pilot": "Открыть маршрут запусков",
    "model": "Открыть состояние AI",
    "retention": "Показать сведения политики",
}


def _priority(station: AgentAdminStationOut) -> AgentAdminPriorityOut:
    attention = (
        "blocker"
        if station.state == "blocked"
        else "continue" if station.state == "ready" else "review"
    )
    return AgentAdminPriorityOut(
        kind=station.kind,
        attention=attention,
        title=station.label,
        detail=station.detail,
        evidence_label=station.evidence_window,
        action_target=station.action_target,
        action_label=_ACTION_COPY[station.action_target],
    )


def build_admin_operations_brief(
    *,
    organization: Organization,
    registration: ToolRegistrationReadiness,
    launch_health: dict | None,
    model_readiness: AgentModelReadinessOut | None,
    retention_policy: TutorDataPolicyOut | None,
) -> AgentAdminOperationsBriefOut:
    stations = [
        _configuration_station(registration),
        (
            _launch_station(launch_health)
            if launch_health is not None
            else _unavailable_station(
                kind="canvas_launch",
                action_target="pilot",
                label="Состояние запусков недоступно",
                evidence_window="Агрегат за 7 дней не получен",
            )
        ),
        (
            _model_station(model_readiness)
            if model_readiness is not None
            else _unavailable_station(
                kind="model_runtime",
                action_target="model",
                label="Состояние AI недоступно",
                evidence_window="Агрегат за 30 минут не получен",
            )
        ),
        (
            _retention_station(retention_policy)
            if retention_policy is not None
            else _unavailable_station(
                kind="data_retention",
                action_target="retention",
                label="Политика хранения недоступна",
                evidence_window="Текущая политика не получена",
            )
        ),
    ]
    ordered = sorted(stations, key=lambda item: (_STATE_ORDER[item.state], item.kind))
    actionable = [item for item in ordered if item.state != "ready"]
    priorities = [_priority(item) for item in (actionable or ordered[:1])[:3]]
    overall_state = (
        "partial"
        if any(item.state == "unavailable" for item in stations)
        else ordered[0].state
    )
    headlines = {
        "blocked": "Сначала устраните блокер безопасного запуска",
        "partial": "Часть сигналов недоступна — начните с доступного маршрута",
        "attention": "Сначала разберите один операционный сигнал",
        "not_started": "Сначала подтвердите тестовый маршрут",
        "ready": "Основные границы готовы к ограниченному пилоту",
    }
    return AgentAdminOperationsBriefOut(
        mode="admin_operations_brief",
        organization_name=organization.name,
        overall_state=overall_state,
        headline=headlines[overall_state],
        stations=stations,
        priorities=priorities,
        limitations=[
            "Это локальные агрегаты, а не живая проверка школьного Canvas.",
            "Запуски показаны за 7 дней, работа AI — за 30 минут.",
            "Сводка не содержит людей, диалогов, оценок или материалов курсов.",
            "Маршрут ничего не меняет в Canvas, настройках и политике хранения.",
        ],
        read_only=True,
    )


def current_admin_operations_brief(
    db: Session,
    *,
    context: AgentTrustedContext,
    signed_ref: str,
) -> AgentAdminOperationsBriefOut:
    organization = resolve_organization_ref(db, context=context, signed_ref=signed_ref)
    return build_admin_operations_brief(
        organization=organization,
        registration=tool_registration_readiness(),
        launch_health=_safe_db_projection(
            db,
            lambda: pilot_launch_health(db, organization_id=organization.id),
        ),
        model_readiness=_safe_db_projection(
            db,
            lambda: model_runtime_readiness(db, organization_id=organization.id),
        ),
        retention_policy=_safe_db_projection(
            db,
            lambda: get_effective_tutor_data_policy(db, organization.id),
        ),
    )


def _latest_safe_purge_projection(
    db: Session,
    *,
    organization_id: int,
) -> _PurgeProjection:
    row = (
        db.query(TutorDataDeletionEvent)
        .filter(
            TutorDataDeletionEvent.organization_id == organization_id,
            TutorDataDeletionEvent.course_id.is_(None),
            TutorDataDeletionEvent.subject_user_id.is_(None),
            TutorDataDeletionEvent.reason.in_(("automatic_retention", "admin_purge")),
        )
        .order_by(
            TutorDataDeletionEvent.created_at.desc(),
            TutorDataDeletionEvent.id.desc(),
        )
        .first()
    )
    if row is None:
        return _PurgeProjection(state="no_receipt")
    return _PurgeProjection(
        state="recorded",
        receipt_id=row.id,
        reason=row.reason,
        policy_version=int(row.policy_version),
        answers_deleted=int(row.answers_deleted),
        feedback_events_deleted=int(row.feedback_events_deleted),
        agent_runs_deleted=int(row.agent_runs_deleted),
        cutoff=row.cutoff,
        agent_run_cutoff=row.agent_run_cutoff,
        recorded_at=row.created_at,
    )


def _policy_version_rows(
    policy: TutorDataPolicyOut | None,
) -> list[AgentAdminPolicyVersionOut]:
    if policy is None:
        tutor_version = AgentAdminPolicyVersionOut(
            kind="tutor_data",
            label="Данные учебного помощника",
            version="недоступно",
            detail="Версию политики не удалось прочитать в этой проверке.",
        )
    elif policy.version == 0 and policy.updated_at is None:
        tutor_version = AgentAdminPolicyVersionOut(
            kind="tutor_data",
            label="Данные учебного помощника",
            version="по умолчанию · v0",
            detail="Организация ещё не сохраняла собственную версию срока хранения.",
        )
    else:
        tutor_version = AgentAdminPolicyVersionOut(
            kind="tutor_data",
            label="Данные учебного помощника",
            version=f"организация · v{policy.version}",
            detail="Сохранённая версия действует для этой организации.",
        )
    return [
        tutor_version,
        AgentAdminPolicyVersionOut(
            kind="agent_runtime",
            label="Правила ИИ-агента",
            version=POLICY_VERSION,
            detail="Версия серверных ролевых и инструментальных границ агента.",
        ),
    ]


def _retention_projection(
    policy: TutorDataPolicyOut | None,
) -> AgentAdminRetentionOut:
    if policy is None:
        return AgentAdminRetentionOut(
            state="unavailable",
            source="unavailable",
            retention_days=None,
            agent_metadata_retention_days=AGENT_RUN_RETENTION_DAYS,
            automatic_purge=None,
            student_self_delete=None,
            label="Срок хранения временно недоступен",
            detail=(
                "Граница метаданных агента известна, но эффективную политику "
                "учебного помощника прочитать не удалось."
            ),
        )
    source = (
        "default"
        if policy.version == 0 and policy.updated_at is None
        else "organization"
    )
    return AgentAdminRetentionOut(
        state="available",
        source=source,
        retention_days=policy.retention_days,
        agent_metadata_retention_days=AGENT_RUN_RETENTION_DAYS,
        automatic_purge=policy.automatic_purge,
        student_self_delete=policy.student_self_delete,
        label=f"Учебные данные — до {policy.retention_days} дней",
        detail=(
            "Действует значение по умолчанию; собственная версия организации "
            "ещё не сохранена."
            if source == "default"
            else "Действует сохранённая политика этой организации."
        ),
    )


def _purge_status_projection(
    *,
    policy: TutorDataPolicyOut | None,
    purge: _PurgeProjection | None,
) -> AgentAdminPurgeStatusOut:
    if purge is None:
        return AgentAdminPurgeStatusOut(
            state="unavailable",
            label="Журнал очистки временно недоступен",
            detail=(
                "Политика могла быть прочитана отдельно, но последнюю безопасную "
                "квитанцию получить не удалось."
            ),
            facts=["Статус квитанции не получен"],
            evidence_window="Текущая проверка источника завершилась частично",
        )
    if purge.state == "no_receipt":
        return AgentAdminPurgeStatusOut(
            state="no_receipt",
            label="Квитанции с удалёнными записями пока нет",
            detail=(
                "Это не означает, что очистка не запускалась: если удалять было "
                "нечего, отдельная квитанция не создаётся."
            ),
            facts=["Нет зафиксированного удаления данных организации"],
            evidence_window="Весь доступный журнал организации",
        )
    if policy is None:
        state = "recorded"
        detail = (
            "Безопасная агрегированная квитанция найдена, но сравнить её версию "
            "с текущей политикой сейчас нельзя."
        )
    elif purge.policy_version == policy.version:
        state = "current"
        detail = "Квитанция создана по текущей версии политики хранения."
    else:
        state = "previous_policy"
        detail = (
            "Квитанция относится к другой версии политики; это историческая "
            "запись, а не подтверждение текущего цикла очистки."
        )
    reason_label = (
        "Автоматическая очистка"
        if purge.reason == "automatic_retention"
        else "Очистка администратором"
    )
    recorded_at = purge.recorded_at
    evidence_window = (
        f"Последняя безопасная квитанция · {recorded_at.date().isoformat()}"
        if recorded_at is not None
        else "Последняя безопасная квитанция организации"
    )
    return AgentAdminPurgeStatusOut(
        state=state,
        label=reason_label,
        detail=detail,
        recorded_at=recorded_at,
        policy_version=purge.policy_version,
        facts=[
            f"Ответов удалено: {purge.answers_deleted}",
            f"Сигналов обратной связи удалено: {purge.feedback_events_deleted}",
            f"Запусков агента удалено: {purge.agent_runs_deleted}",
        ],
        evidence_window=evidence_window,
    )


def build_admin_policy_status(
    *,
    organization: Organization,
    policy: TutorDataPolicyOut | None,
    purge: _PurgeProjection | None,
) -> AgentAdminPolicyStatusOut:
    retention = _retention_projection(policy)
    purge_status = _purge_status_projection(policy=policy, purge=purge)
    if policy is None or purge is None:
        overall_state = "partial"
        headline = "Часть границ хранения временно недоступна"
    elif purge_status.state == "previous_policy":
        overall_state = "attention"
        headline = "Последняя квитанция относится к другой версии политики"
    elif purge_status.state == "no_receipt":
        overall_state = "no_receipt"
        headline = "Политика известна; удалений с квитанцией пока не было"
    else:
        overall_state = "ready"
        headline = "Текущая политика и последняя квитанция сопоставлены"
    return AgentAdminPolicyStatusOut(
        mode="admin_policy_status",
        organization_name=organization.name,
        overall_state=overall_state,
        headline=headline,
        retention=retention,
        policy_versions=_policy_version_rows(policy),
        purge_status=purge_status,
        action_label="Показать границы очистки",
        limitations=[
            "Квитанция создаётся только когда очистка действительно удалила записи.",
            "Показана одна последняя обезличенная квитанция без людей и курсов.",
            "Это политика дополнения к Canvas, а не проверка всех хранилищ школы.",
            "Маршрут ничего не меняет и не запускает очистку.",
        ],
        read_only=True,
    )


def _current_admin_policy_projection(
    db: Session,
    *,
    context: AgentTrustedContext,
    signed_ref: str,
) -> tuple[AgentAdminPolicyStatusOut, str]:
    organization = resolve_organization_ref(db, context=context, signed_ref=signed_ref)
    policy = _safe_db_projection(
        db, lambda: get_effective_tutor_data_policy(db, organization.id)
    )
    purge = _safe_db_projection(
        db,
        lambda: _latest_safe_purge_projection(db, organization_id=organization.id),
    )
    result = build_admin_policy_status(
        organization=organization,
        policy=policy,
        purge=purge,
    )
    source_payload = {
        "result": result.model_dump(mode="json"),
        "policy_source": (
            policy.model_dump(mode="json") if policy is not None else "unavailable"
        ),
        "purge_source": (
            purge.model_dump(mode="json") if purge is not None else "unavailable"
        ),
        "agent_policy_version": POLICY_VERSION,
    }
    digest = hashlib.sha256(
        json.dumps(source_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return result, digest


def current_admin_policy_status(
    db: Session,
    *,
    context: AgentTrustedContext,
    signed_ref: str,
) -> AgentAdminPolicyStatusOut:
    return _current_admin_policy_projection(db, context=context, signed_ref=signed_ref)[
        0
    ]


def _result_digest(
    result: AgentAdminOperationsBriefOut | AgentAdminAnalyticsBriefOut,
) -> str:
    return hashlib.sha256(result.model_dump_json().encode("utf-8")).hexdigest()


def _analytics_result_digest(
    result: AgentAdminAnalyticsBriefOut,
    cost_rates: tuple[Decimal, Decimal] | None,
) -> str:
    normalized_rates = (
        None
        if cost_rates is None
        else [format(value.normalize(), "f") for value in cost_rates]
    )
    payload = {
        "result": result.model_dump(mode="json"),
        "cost_rates_usd_per_million_tokens": normalized_rates,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def execute_admin_run(
    db: Session,
    *,
    principal: Principal,
    run_id: int,
) -> AgentRun:
    row = db.query(AgentRun).filter(AgentRun.id == run_id).one_or_none()
    if row is None:
        _deny()
    context = resolve_agent_context(db, principal, organization_id=row.organization_id)
    tool_names = (
        ("get_aggregate_adoption_health", "get_agent_latency_cost_health")
        if row.workflow == "admin.analytics_health.v1"
        else (
            ("get_retention_and_policy_status",)
            if row.workflow == "admin.policy_status.v1"
            else ("get_integration_readiness",)
        )
    )
    _configure_statement_timeout(
        db, max(TOOL_REGISTRY[name].timeout_seconds for name in tool_names)
    )
    row = (
        db.query(AgentRun).filter(AgentRun.id == run_id).with_for_update().one_or_none()
    )
    if (
        row is None
        or not _exact_context(row, context)
        or row.workflow not in EXECUTABLE_ADMIN_WORKFLOWS
    ):
        _deny()
    if row.status in {"completed", "abstained", "failed"}:
        return row
    if row.status != "tool_running" or not row.selection_ref:
        raise HTTPException(status_code=409, detail="run is not ready to execute")

    policy_source_digest: str | None = None
    if row.workflow == "admin.policy_status.v1":
        policy_projection = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="get_retention_and_policy_status",
            tool_input=AdminOperationsToolIn(organization_ref=row.selection_ref),
            call=lambda _deadline: _current_admin_policy_projection(
                db, context=context, signed_ref=row.selection_ref or ""
            ),
            output_projection=lambda value: AdminPolicyToolOut(
                retention=value[0].retention,
                policy_versions=value[0].policy_versions,
                purge_status=value[0].purge_status,
            ),
            organization_id=row.organization_id,
        )
        if not (
            isinstance(policy_projection, tuple)
            and len(policy_projection) == 2
            and isinstance(policy_projection[0], AgentAdminPolicyStatusOut)
            and isinstance(policy_projection[1], str)
        ):
            raise ValueError("administrator policy result is invalid")
        result = policy_projection[0]
        policy_source_digest = policy_projection[1]
    elif row.workflow == "admin.analytics_health.v1":
        analytics_cost_rates = _configured_cost_rates()
        organization = resolve_organization_ref(
            db, context=context, signed_ref=row.selection_ref
        )
        executed_at = datetime.now(timezone.utc)
        adoption = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="get_aggregate_adoption_health",
            tool_input=AdminOperationsToolIn(organization_ref=row.selection_ref),
            call=lambda _deadline: current_admin_adoption_segment(
                db,
                context=context,
                signed_ref=row.selection_ref or "",
                now=executed_at,
            ),
            output_projection=lambda value: AdminAdoptionToolOut(segment=value),
            organization_id=row.organization_id,
        )
        runtime_bundle = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="get_agent_latency_cost_health",
            tool_input=AdminOperationsToolIn(organization_ref=row.selection_ref),
            call=lambda _deadline: current_admin_runtime_segments(
                db,
                context=context,
                signed_ref=row.selection_ref or "",
                cost_rates=analytics_cost_rates,
                now=executed_at,
            ),
            output_projection=lambda value: AdminRuntimeToolOut(
                runtime=value[0], cost=value[1]
            ),
            organization_id=row.organization_id,
        )
        if not isinstance(adoption, AgentAdminAnalyticsSegmentOut) or not (
            isinstance(runtime_bundle, tuple)
            and len(runtime_bundle) == 2
            and all(
                isinstance(item, AgentAdminAnalyticsSegmentOut)
                for item in runtime_bundle
            )
        ):
            raise ValueError("administrator analytics result is invalid")
        result = build_admin_analytics_brief(
            organization=organization,
            adoption=adoption,
            runtime=runtime_bundle[0],
            cost=runtime_bundle[1],
        )
    else:
        result = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="get_integration_readiness",
            tool_input=AdminOperationsToolIn(organization_ref=row.selection_ref),
            call=lambda _deadline: current_admin_operations_brief(
                db, context=context, signed_ref=row.selection_ref or ""
            ),
            output_projection=lambda value: AdminOperationsToolOut(
                organization_name=value.organization_name,
                overall_state=value.overall_state,
                headline=value.headline,
                stations=value.stations,
                priorities=value.priorities,
                limitations=value.limitations,
            ),
            organization_id=row.organization_id,
        )
        if not isinstance(result, AgentAdminOperationsBriefOut):
            raise ValueError("administrator operations result is invalid")
    current = resolve_agent_context(db, principal, organization_id=row.organization_id)
    if not _exact_context(row, current):
        _deny()
    resolve_organization_ref(db, context=current, signed_ref=row.selection_ref)
    row.result_digest = (
        policy_source_digest
        if isinstance(result, AgentAdminPolicyStatusOut)
        else (
            _analytics_result_digest(result, analytics_cost_rates)
            if isinstance(result, AgentAdminAnalyticsBriefOut)
            else _result_digest(result)
        )
    )
    row.status = "completed"
    row.label = (
        "Контрольная лента администратора готова"
        if row.workflow == "admin.analytics_health.v1"
        else (
            "Границы хранения данных проверены"
            if row.workflow == "admin.policy_status.v1"
            else "Маршрут действий администратора готов"
        )
    )
    row.recovery_action = None
    db.commit()
    db.refresh(row)
    return row


def project_admin_operations_brief(
    db: Session,
    *,
    row: AgentRun,
) -> AgentAdminOperationsBriefOut:
    context = AgentTrustedContext(
        organization_id=row.organization_id,
        course_id=row.course_id,
        user_id=row.user_id,
        role=row.role,
        product_session_id=row.product_session_id,
    )
    if (
        row.workflow != "admin.integration_readiness.v1"
        or not row.selection_ref
        or not row.result_digest
    ):
        _deny()
    result = current_admin_operations_brief(
        db, context=context, signed_ref=row.selection_ref
    )
    if not hmac.compare_digest(row.result_digest, _result_digest(result)):
        _deny()
    return result


def project_admin_analytics_brief(
    db: Session,
    *,
    row: AgentRun,
) -> AgentAdminAnalyticsBriefOut:
    context = AgentTrustedContext(
        organization_id=row.organization_id,
        course_id=row.course_id,
        user_id=row.user_id,
        role=row.role,
        product_session_id=row.product_session_id,
    )
    if (
        row.workflow != "admin.analytics_health.v1"
        or not row.selection_ref
        or not row.result_digest
    ):
        _deny()
    cost_rates = _configured_cost_rates()
    result = current_admin_analytics_brief(
        db,
        context=context,
        signed_ref=row.selection_ref,
        cost_rates=cost_rates,
    )
    if not hmac.compare_digest(
        row.result_digest, _analytics_result_digest(result, cost_rates)
    ):
        _deny()
    return result


def project_admin_policy_status(
    db: Session,
    *,
    row: AgentRun,
) -> AgentAdminPolicyStatusOut:
    context = AgentTrustedContext(
        organization_id=row.organization_id,
        course_id=row.course_id,
        user_id=row.user_id,
        role=row.role,
        product_session_id=row.product_session_id,
    )
    if (
        row.workflow != "admin.policy_status.v1"
        or not row.selection_ref
        or not row.result_digest
    ):
        _deny()
    result, digest = _current_admin_policy_projection(
        db, context=context, signed_ref=row.selection_ref
    )
    if not hmac.compare_digest(row.result_digest, digest):
        _deny()
    return result


__all__ = [
    "EXECUTABLE_ADMIN_WORKFLOWS",
    "admin_organization_option",
    "build_admin_analytics_brief",
    "build_admin_operations_brief",
    "build_admin_policy_status",
    "current_admin_analytics_brief",
    "current_admin_operations_brief",
    "current_admin_policy_status",
    "execute_admin_run",
    "organization_ref",
    "project_admin_analytics_brief",
    "project_admin_operations_brief",
    "project_admin_policy_status",
    "resolve_organization_ref",
]
