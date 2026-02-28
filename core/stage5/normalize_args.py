"""Normalize LLM tool_call.arguments to gold schema for Stage 5 evaluation."""

from __future__ import annotations

from typing import Any

from core.stage5.schemas import ScenarioName, ScenarioSpec


def _nested_get(data: dict[str, Any], dotted: str) -> Any:
    current: Any = data
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _get_first(raw: dict[str, Any], *candidates: str) -> Any:
    """Return first non-None, non-empty value from raw using candidate keys or dotted paths."""
    for key in candidates:
        if "." in key:
            value = _nested_get(raw, key)
        else:
            value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _normalize_decision(raw: dict[str, Any], gold_keys: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "program" in gold_keys:
        out["program"] = _get_first(raw, "program", "program_name")
    if "region" in gold_keys:
        out["region"] = _get_first(raw, "region", "jurisdiction", "state")
    if "criteria_summary" in gold_keys:
        out["criteria_summary"] = _get_first(
            raw, "criteria_summary", "criteria", "eligibility_criteria"
        )
    return out


def _normalize_scheduling(raw: dict[str, Any], gold_keys: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "title" in gold_keys:
        out["title"] = _get_first(raw, "title", "event_title", "name")
    if "date" in gold_keys:
        out["date"] = _get_first(raw, "date", "month", "deadline", "scheduled_date")
    if "assignees" in gold_keys:
        val = _get_first(raw, "assignees", "assignee")
        if val is not None:
            out["assignees"] = [val] if isinstance(val, str) else val
        else:
            out["assignees"] = None
    if "channel" in gold_keys:
        out["channel"] = _get_first(raw, "channel", "communication_channel")
    return out


def _normalize_db(raw: dict[str, Any], gold_keys: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in gold_keys:
        val = _get_first(raw, key, f"lookup_key.{key}", f"key_identifier.{key}")
        out[key] = val
    return out


def _normalize_credential(raw: dict[str, Any], gold_keys: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "holder_name" in gold_keys:
        out["holder_name"] = _get_first(
            raw, "holder_name", "candidate_name", "subject.full_name", "name"
        )
    if "institution" in gold_keys:
        out["institution"] = _get_first(
            raw,
            "institution",
            "institution_name",
            "claimed_institution",
            "credential.institution_name",
            "primary_claimed_credential.institution",
        )
    if "degree" in gold_keys:
        degree = _get_first(
            raw,
            "degree",
            "degree_name",
            "claimed_degree",
            "credential.degree_name",
        )
        if _is_empty(degree):
            field = _get_first(raw, "field_of_study", "credential.field_of_study")
            deg_base = _get_first(raw, "degree", "degree_name", "credential.degree_name")
            if deg_base and field:
                degree = f"{deg_base} {field}"
            elif deg_base:
                degree = deg_base
        out["degree"] = degree
    if "date_range" in gold_keys:
        date_range = _get_first(raw, "date_range")
        if _is_empty(date_range):
            start = _get_first(raw, "start_year", "credential.start_year")
            end = _get_first(raw, "end_year", "credential.end_year")
            if start is None or end is None:
                dr = _nested_get(raw, "primary_claimed_credential") or _nested_get(raw, "credential")
                if isinstance(dr, dict):
                    inner = dr.get("date_range") if isinstance(dr.get("date_range"), dict) else dr
                    if isinstance(inner, dict):
                        start = start or inner.get("start_year")
                        end = end or inner.get("end_year")
            if start is not None and end is not None:
                date_range = f"{start}-{end}"
            else:
                date_range = None
        out["date_range"] = date_range
    return out


def _normalize_survey(raw: dict[str, Any], gold_keys: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "url" in gold_keys:
        out["url"] = _get_first(raw, "url", "link", "survey_url")
    if "optional" in gold_keys:
        val = raw.get("optional")
        if val is not None:
            out["optional"] = bool(val)
        else:
            consent = _get_first(raw, "consent_text", "consent")
            if consent is not None and isinstance(consent, str):
                out["optional"] = "mandatory" not in consent.lower()
            else:
                out["optional"] = None
    return out


def normalize_arguments(
    scenario: ScenarioName,
    raw: dict[str, Any],
    spec: ScenarioSpec,
) -> dict[str, Any]:
    """
    Map raw LLM tool_call.arguments to gold schema keys.
    Returns a dict with exactly the keys in spec.gold_clean.arguments.
    """
    if not isinstance(raw, dict):
        return {k: None for k in (spec.gold_clean.arguments or {})}

    gold_keys = set((spec.gold_clean.arguments or {}).keys())
    if not gold_keys:
        return {}

    if scenario == "decision":
        return _normalize_decision(raw, gold_keys)
    if scenario == "scheduling":
        return _normalize_scheduling(raw, gold_keys)
    if scenario == "db":
        return _normalize_db(raw, gold_keys)
    if scenario == "credential":
        return _normalize_credential(raw, gold_keys)
    if scenario == "survey":
        return _normalize_survey(raw, gold_keys)

    # Fallback: try each gold key as flat then dotted
    out: dict[str, Any] = {}
    for key in gold_keys:
        out[key] = _get_first(raw, key, f"arguments.{key}")
    return out
