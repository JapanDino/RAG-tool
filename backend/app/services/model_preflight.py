from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Mapping

from ..schemas.model_gateway import CompatibilityProbeOutput
from ..schemas.model_preflight import (
    ModelCompatibilityProfileId,
    ModelCompatibilityProfileOut,
    ModelHostPreflightOut,
    ModelPreflightCheckOut,
    ModelPreflightStatus,
    OrganizationModelRouteState,
)
from .model_gateway import (
    model_gateway_configuration,
    model_gateway_configuration_checks,
)
from .openai_client import extract_json_block


@dataclass(frozen=True)
class _Profile:
    id: ModelCompatibilityProfileId
    cli_name: str
    label: str
    summary: str
    fixture: dict


_PROFILES = (
    _Profile(
        id="deepseek_openai_v1",
        cli_name="deepseek",
        label="DeepSeek · OpenAI-совместимый",
        summary=(
            "Проверяет общий chat-completions конверт и строгий JSON-результат "
            "на синтетическом ответе DeepSeek-формы."
        ),
        fixture={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"status":"ok","detail":"synthetic"}',
                    }
                }
            ]
        },
    ),
    _Profile(
        id="gemma_openai_v1",
        cli_name="gemma",
        label="Gemma · OpenAI-совместимый",
        summary=(
            "Проверяет тот же контракт и безопасное извлечение одного JSON-блока "
            "из синтетического ответа Gemma-формы."
        ),
        fixture={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": (
                            "```json\n" '{"status":"ok","detail":"synthetic"}' "\n```"
                        ),
                    }
                }
            ]
        },
    ),
)
_PROFILE_BY_ID = {profile.id: profile for profile in _PROFILES}
PROFILE_ID_BY_CLI_NAME = {profile.cli_name: profile.id for profile in _PROFILES}

REQUIRED_SERVER_FIELDS = (
    "AGENT_MODEL_ENABLED",
    "AGENT_MODEL_BASE_URL",
    "AGENT_MODEL_ALLOWED_HOSTS",
    "AGENT_MODEL_ID",
    "AGENT_MODEL_API_KEY",
    "AGENT_MODEL_CONNECT_TIMEOUT",
    "AGENT_MODEL_READ_TIMEOUT",
    "AGENT_MODEL_RETRIES",
    "AGENT_MODEL_MAX_CONCURRENCY",
    "AGENT_MODEL_MAX_INPUT_CHARS",
    "AGENT_MODEL_MAX_OUTPUT_TOKENS",
    "AGENT_MODEL_MAX_RESPONSE_BYTES",
)

LIMITATIONS = (
    "Реальный школьный AI-сервис не вызывался, а его доступность не проверялась.",
    "Синтетический конверт подтверждает формат, но не качество ответов модели.",
    "TLS, DNS, доступность модели и задержка проверяются только в одобренной инфраструктуре.",
    "Ключи, адреса, идентификаторы модели, промпты и данные курсов в пакет не входят.",
)


def model_compatibility_profiles() -> list[ModelCompatibilityProfileOut]:
    return [
        ModelCompatibilityProfileOut(
            id=profile.id,
            label=profile.label,
            contract="openai_chat_completions_v1",
            summary=profile.summary,
        )
        for profile in _PROFILES
    ]


def _fixture_valid(profile: _Profile) -> bool:
    try:
        content = profile.fixture["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            return False
        parsed = CompatibilityProbeOutput.model_validate_json(
            extract_json_block(content)
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return False
    return parsed.status == "ok" and parsed.detail == "synthetic"


def _check(
    code: str,
    passed: bool,
    *,
    label: str,
    detail_passed: str,
    detail_blocked: str,
) -> ModelPreflightCheckOut:
    return ModelPreflightCheckOut(
        code=code,
        status="passed" if passed else "blocked",
        owner="application",
        label=label,
        detail=detail_passed if passed else detail_blocked,
    )


def _external(code: str, label: str, detail: str) -> ModelPreflightCheckOut:
    return ModelPreflightCheckOut(
        code=code,
        status="external",
        owner="system_administrator",
        label=label,
        detail=detail,
    )


def _status(configuration_state: str) -> ModelPreflightStatus:
    if configuration_state == "configured":
        return "ready_for_credentialed_probe"
    if configuration_state == "misconfigured":
        return "configuration_blocked"
    return "configuration_required"


def _canonical_bytes(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def build_model_host_preflight(
    *,
    profile_id: ModelCompatibilityProfileId,
    organization_model_route: OrganizationModelRouteState = "not_assessed",
    env: Mapping[str, str] | None = None,
) -> ModelHostPreflightOut:
    values = os.environ if env is None else env
    profile = _PROFILE_BY_ID[profile_id]
    configuration = model_gateway_configuration(values)
    configuration_checks = model_gateway_configuration_checks(values)
    fixture_valid = _fixture_valid(profile)
    checks = [
        _check(
            "profile_contract_supported",
            fixture_valid,
            label="Структурированный ответ распознаётся",
            detail_passed="Синтетический ответ прошёл тот же строгий JSON-контракт, что использует шлюз.",
            detail_blocked="Локальный профиль не прошёл строгую проверку структуры.",
        ),
        _check(
            "server_feature_enabled",
            configuration_checks.feature_enabled,
            label="Серверный маршрут AI включён",
            detail_passed="Серверная конфигурация разрешает модельный шлюз.",
            detail_blocked="Системному администратору нужно включить модельный шлюз на сервере.",
        ),
        _check(
            "server_credential_present",
            configuration_checks.credential_present,
            label="Серверный секрет предоставлен",
            detail_passed="Наличие секрета подтверждено без чтения или вывода его значения.",
            detail_blocked="Серверный секрет ещё не предоставлен через хранилище секретов.",
        ),
        _check(
            "server_model_selection_present",
            configuration_checks.model_selection_present,
            label="Сервер выбрал модель",
            detail_passed="Наличие серверного выбора подтверждено без вывода идентификатора.",
            detail_blocked="Системному администратору нужно выбрать модель в серверной конфигурации.",
        ),
        _check(
            "exact_origin_policy_valid",
            configuration_checks.origin_policy_valid,
            label="Адрес и allow-list согласованы",
            detail_passed="Единый валидатор принял HTTPS origin и точный серверный allow-list.",
            detail_blocked="Адрес и точный allow-list ещё не образуют безопасную конфигурацию.",
        ),
        _check(
            "bounded_runtime_policy_valid",
            configuration_checks.runtime_policy_valid,
            label="Лимиты вызова ограничены",
            detail_passed="Таймауты, повторы, параллельность и размеры прошли единый валидатор.",
            detail_blocked="Один или несколько серверных лимитов отсутствуют либо недопустимы.",
        ),
        _external(
            "host_reachable_from_application",
            "Сервис достижим из приложения",
            "Проверить маршрут только из одобренной серверной сети, не из браузера.",
        ),
        _external(
            "tls_chain_trusted",
            "TLS-цепочка доверена",
            "Проверить сертификат и имя узла внутри целевой инфраструктуры.",
        ),
        _external(
            "configured_model_available",
            "Выбранная модель доступна",
            "Подтвердить доступность серверного выбора, не публикуя его идентификатор.",
        ),
        _external(
            "structured_probe_succeeds",
            "Проверочный вызов проходит",
            "Выполнить один синтетический вызов без данных курса и проверить строгую схему.",
        ),
        _external(
            "latency_budget_observed",
            "Задержка укладывается в бюджет",
            "Зафиксировать серверную задержку после одобренного проверочного вызова.",
        ),
    ]
    profile_out = next(
        item for item in model_compatibility_profiles() if item.id == profile.id
    )
    payload = {
        "schema_version": 1,
        "profile": profile_out.model_dump(mode="json"),
        "available_profiles": [
            item.model_dump(mode="json") for item in model_compatibility_profiles()
        ],
        "status": _status(configuration.state),
        "configuration_state": configuration.state,
        "organization_model_route": organization_model_route,
        "network_probe_performed": False,
        "credentials_included": False,
        "course_data_used": False,
        "checks": [item.model_dump(mode="json") for item in checks],
        "required_server_fields": list(REQUIRED_SERVER_FIELDS),
        "operator_command": (
            "python scripts/check_agent_model_preflight.py "
            f"--profile {profile.cli_name}"
        ),
        "limitations": list(LIMITATIONS),
    }
    fingerprint = hashlib.sha256(_canonical_bytes(payload)).hexdigest()[:16]
    return ModelHostPreflightOut(
        **payload,
        bundle_fingerprint=f"sha256:{fingerprint}",
    )


def serialize_model_host_preflight(report: ModelHostPreflightOut) -> bytes:
    return _canonical_bytes(report.model_dump(mode="json")) + b"\n"


__all__ = [
    "PROFILE_ID_BY_CLI_NAME",
    "REQUIRED_SERVER_FIELDS",
    "build_model_host_preflight",
    "model_compatibility_profiles",
    "serialize_model_host_preflight",
]
