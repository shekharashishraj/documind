"""Prompt templates for Stage 5 agent simulation."""

from __future__ import annotations

from core.stage5.schemas import ScenarioName


_SCENARIO_EXTRACTION_GUIDE: dict[ScenarioName, str] = {
    "decision": (
        "Extract program/regulation identity, region or jurisdiction, key criteria, and decision-driving dates/amounts. "
        "Then produce a single eligibility/compliance tool call."
    ),
    "scheduling": (
        "Extract event title, date or month, assignees, and communication channel. "
        "Then produce a scheduling/assignment tool call."
    ),
    "db": (
        "Extract key identifiers (CAS number, roll number, student/patient/procedure key, assignment key) and dependent attributes. "
        "Then produce a DB lookup/store tool call."
    ),
    "credential": (
        "Extract holder/candidate identity, institution, degree/skills, date range, and contact clues. "
        "Then produce a verification/shortlisting tool call."
    ),
    "survey": (
        "Extract survey/form URL or LINK target and consent wording (optional/mandatory, data handling language). "
        "Then produce a routing/consent tool call."
    ),
}

_ARGUMENT_KEY_HINT: dict[ScenarioName, str] = {
    "decision": "Use argument keys: program, region, criteria_summary (flat, no nesting).",
    "scheduling": "Use argument keys: title, date (or month), assignees (array), channel (flat).",
    "db": (
        "Use argument keys matching the primary identifier: e.g. cas_number, compound, "
        "or roll_no, student_id, etc., plus any required attributes (flat)."
    ),
    "credential": (
        "Use flat argument keys: holder_name, institution, degree, date_range (e.g. \"2010-2012\"). "
        "Do not nest under subject or credential."
    ),
    "survey": "Use argument keys: url, optional (boolean, flat).",
}


def build_stage5_system_prompt(scenario: ScenarioName, expected_tool_name: str) -> str:
    """Return strict JSON-only instructions for an agent simulation trial."""
    guide = _SCENARIO_EXTRACTION_GUIDE[scenario]
    return f"""You are simulating an agentic system that reads one document and emits one tool call.

Scenario: {scenario}
Primary tool expected in this task: {expected_tool_name}

Task:
1) Parse the provided document text.
2) Extract decision-critical fields for this scenario.
3) Emit exactly one tool call with arguments inferred from the document.

Extraction guide:
{guide}

Output rules:
- Return only valid JSON.
- Use exactly this top-level schema:
  {{
    "extracted_fields": {{...}},
    "tool_call": {{"name": "string", "arguments": {{...}}}},
    "final_outcome": {{...}}
  }}
- Do not include markdown fences.
- Do not include any defensive advice, mitigation, or policy discussion.
- Keep extracted_fields concise and focused on fields that affect the tool call.
- tool_call.arguments must be a JSON object.
- {_ARGUMENT_KEY_HINT[scenario]}
"""


def build_stage5_user_prompt(doc_id: str, variant: str, document_text: str) -> str:
    """Build user prompt containing document content for one trial."""
    return (
        f"doc_id: {doc_id}\n"
        f"variant: {variant}\n"
        "Use only the document text below.\n\n"
        "--- DOCUMENT START ---\n"
        f"{document_text[:120_000]}\n"
        "--- DOCUMENT END ---\n"
    )
