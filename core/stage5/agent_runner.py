"""LLM trial runner for Stage 5 agent simulation."""

from __future__ import annotations

import json
import logging
from typing import Any

from core.stage5.mock_tools import execute_mock_tool
from core.stage5.normalize_args import normalize_arguments
from core.stage5.prompts import build_stage5_system_prompt, build_stage5_user_prompt
from core.stage5.schemas import AgentTrialOutput, ScenarioSpec, ToolCall

log = logging.getLogger(__name__)


MAX_DOC_CHARS = 120_000
MAX_COMPLETION_TOKENS = 4096
EMPTY_CONTENT_MAX_RETRIES = 2


def _parse_agent_payload(raw_content: str, spec: ScenarioSpec) -> dict[str, Any]:
    payload = json.loads(raw_content)
    extracted_fields = payload.get("extracted_fields")
    if not isinstance(extracted_fields, dict):
        extracted_fields = {}

    tool_call_payload = payload.get("tool_call")
    if not isinstance(tool_call_payload, dict):
        tool_call_payload = {}

    tool_name = tool_call_payload.get("name") or spec.tool_name
    arguments = tool_call_payload.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}

    final_outcome = payload.get("final_outcome")
    if not isinstance(final_outcome, dict):
        final_outcome = {}

    return {
        "extracted_fields": extracted_fields,
        "tool_call": {"name": str(tool_name), "arguments": arguments},
        "final_outcome": final_outcome,
    }


def run_agent_trials(
    *,
    doc_id: str,
    variant: str,
    document_text: str,
    parse_source: str,
    spec: ScenarioSpec,
    model: str = "gpt-5-2025-08-07",
    trials: int = 3,
    api_key: str | None = None,
) -> list[AgentTrialOutput]:
    """Run N LLM agent simulation trials and execute deterministic mock tools."""
    if trials < 1:
        raise ValueError("trials must be >= 1")

    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Stage 5 requires openai: pip install openai") from None

    client = OpenAI(api_key=api_key or None)

    system_prompt = build_stage5_system_prompt(spec.scenario, spec.tool_name)
    user_prompt = build_stage5_user_prompt(doc_id, variant, document_text[:MAX_DOC_CHARS])

    outputs: list[AgentTrialOutput] = []
    for trial_index in range(1, trials + 1):
        raw_content = None
        finish_reason = None
        for attempt in range(EMPTY_CONTENT_MAX_RETRIES + 1):
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=MAX_COMPLETION_TOKENS,
            )

            if response.choices:
                choice = response.choices[0]
                raw_content = choice.message.content
                finish_reason = getattr(choice, "finish_reason", None)
                log.info(
                    "Stage 5 OpenAI response: doc=%s variant=%s trial=%s attempt=%s finish_reason=%s content_len=%s",
                    doc_id,
                    variant,
                    trial_index,
                    attempt + 1,
                    finish_reason,
                    len(raw_content) if raw_content else 0,
                )
            if raw_content:
                break
            finish_reason = getattr(response.choices[0], "finish_reason", None) if response.choices else None
            log.warning(
                "OpenAI returned empty content (finish_reason=%s), retrying: doc=%s variant=%s trial=%s attempt=%s",
                finish_reason,
                doc_id,
                variant,
                trial_index,
                attempt + 1,
            )
        if not raw_content:
            log.warning(
                "OpenAI returned empty content after %s attempts: doc=%s variant=%s trial=%s finish_reason=%s",
                EMPTY_CONTENT_MAX_RETRIES + 1,
                doc_id,
                variant,
                trial_index,
                finish_reason,
            )
            raise ValueError(
                f"OpenAI returned empty content for doc={doc_id} variant={variant} trial={trial_index} "
                f"(finish_reason={finish_reason})"
            )

        parsed = _parse_agent_payload(raw_content, spec)
        parsed["tool_call"]["arguments"] = normalize_arguments(
            spec.scenario, parsed["tool_call"]["arguments"], spec
        )
        tool_call = ToolCall.model_validate(parsed["tool_call"])
        tool_result = execute_mock_tool(spec.scenario, tool_call.name, tool_call.arguments, spec)

        # Prefer deterministic tool-driven outcome for scoring stability.
        final_outcome = tool_result

        outputs.append(
            AgentTrialOutput(
                doc_id=doc_id,
                scenario=spec.scenario,
                variant=variant,
                trial_index=trial_index,
                extracted_fields=parsed["extracted_fields"],
                tool_call=tool_call,
                tool_result=tool_result,
                final_outcome=final_outcome,
                parse_source=parse_source,
            )
        )

    log.info(
        "Stage 5 agent trials complete: doc=%s variant=%s scenario=%s trials=%s",
        doc_id,
        variant,
        spec.scenario,
        trials,
    )
    return outputs
