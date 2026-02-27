"""Pydantic schemas for Stage 5 post-Stage-4 vulnerability simulation and scoring."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ScenarioName = Literal["decision", "scheduling", "db", "credential", "survey"]
VariantName = Literal["clean", "attacked"]
SeverityLevel = Literal["critical", "high", "medium", "low"]


class AttackTarget(BaseModel):
    """One field that an attack attempts to corrupt."""

    field: str
    type: str


class GoldClean(BaseModel):
    """Expected clean-path tool call and tool outcome for a document."""

    arguments: dict[str, Any] = Field(default_factory=dict)
    outcome: dict[str, Any] = Field(default_factory=dict)


class ScenarioSpec(BaseModel):
    """Ground-truth spec for one document in Stage 5 evaluation."""

    doc_id: str
    scenario: ScenarioName
    severity: SeverityLevel
    tool_name: str
    gold_clean: GoldClean
    attack_targets: list[AttackTarget] = Field(default_factory=list)
    success_rule: str = "any_attack_target_field_changed_or_decision_flipped"


class ToolCall(BaseModel):
    """Structured tool invocation emitted by the agent."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentTrialOutput(BaseModel):
    """One clean/attacked trial result from the Stage 5 simulator."""

    doc_id: str
    scenario: ScenarioName
    variant: VariantName
    trial_index: int
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    tool_call: ToolCall
    tool_result: dict[str, Any] = Field(default_factory=dict)
    final_outcome: dict[str, Any] = Field(default_factory=dict)
    parse_source: str


class DocEvaluationResult(BaseModel):
    """Doc-level majority result and vulnerability labels."""

    doc_id: str
    scenario: ScenarioName
    severity: SeverityLevel
    severity_weight: int
    clean_majority_matches_gold: bool
    baseline_failure: bool
    attack_success: bool
    success_rule_applied: str
    targeted_field_diffs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    targeted_field_changed_count: int = 0
    decision_flip: bool = False
    tool_parameter_corruption: bool = False
    wrong_entity_binding: bool = False
    unsafe_routing: bool = False
    persistence_poisoning: bool = False
    clean_majority: AgentTrialOutput
    attacked_majority: AgentTrialOutput


class ScenarioAggregateMetrics(BaseModel):
    """Scenario-level aggregates for batch reporting."""

    scenario: ScenarioName
    total_docs: int = 0
    eligible_docs: int = 0
    baseline_failure_count: int = 0
    successful_attacks: int = 0
    attack_success_rate: float = 0.0


class BatchEvaluationResult(BaseModel):
    """Batch-level vulnerability metrics and doc-level evidence."""

    run_id: str
    doc_ids: list[str] = Field(default_factory=list)
    total_docs: int = 0
    eligible_docs: int = 0
    baseline_failure_count: int = 0
    successful_attacks: int = 0
    attack_success_rate: float = 0.0
    decision_flip_rate: float = 0.0
    tool_parameter_corruption_rate: float = 0.0
    wrong_entity_binding_rate: float = 0.0
    unsafe_routing_rate: float = 0.0
    persistence_poisoning_rate: float = 0.0
    severity_weighted_vulnerability_score: float = 0.0
    scenario_metrics: list[ScenarioAggregateMetrics] = Field(default_factory=list)
    doc_results: list[DocEvaluationResult] = Field(default_factory=list)
