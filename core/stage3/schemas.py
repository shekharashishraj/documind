"""Pydantic schemas for Stage 3 manipulation_plan.json validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DocumentThreatModel(BaseModel):
    attacker_capability: str | None = None
    attack_goal: str | None = None
    target_consumers: list[str] | None = None
    assumed_defenses: str | None = None


class TextAttackTarget(BaseModel):
    page: int | None = None
    block_index: int | None = None
    bbox: list[float] | None = None
    region: str | None = None
    content_preview: str | None = None


class RenderParseBehavior(BaseModel):
    human_sees: str | None = None
    parser_sees: str | None = None


class TextAttack(BaseModel):
    """One text attack from the manipulation plan."""

    attack_id: str | None = None
    target: TextAttackTarget | None = None
    semantic_edit_strategy: str | None = Field(
        default=None,
        description="Semantic strategy: append | update | delete.",
    )
    injection_mechanism: str | None = Field(
        default=None,
        description="Physical embedding: hidden_text_injection | font_glyph_remapping | visual_overlay.",
    )
    injection_strategy: str | None = None
    technique: str | None = None
    payload_description: str | None = None
    intent: str | None = None
    render_parse_behavior: RenderParseBehavior | None = None
    effects_downstream: str | None = None
    priority: str | None = None
    scope: str | None = Field(
        default=None,
        description="'everywhere' = replace document-wide; 'single_block' = single location.",
    )
    search_key: str | None = Field(
        default=None,
        description="Exact value from Stage 2 value_to_replace to find and replace.",
    )
    replacement: str | None = Field(
        default=None,
        description="Single replacement value to use for all occurrences when scope is everywhere.",
    )
    consistency_note: str | None = Field(
        default=None,
        description="For aggregates: how related_elements must be updated (e.g. total + line items).",
    )


class ImageAttackTarget(BaseModel):
    page: int | None = None
    xref: int | None = None
    image_id: str | None = None
    bbox: list[float] | None = None
    content_description: str | None = None


class ImageAttack(BaseModel):
    attack_id: str | None = None
    target: ImageAttackTarget | None = None
    injection_strategy: str | None = None
    technique: str | None = None
    adversarial_objective: str | None = None
    vision_model_target: str | None = None
    perturbation_constraints: str | None = None
    intent: str | None = None
    render_parse_behavior: RenderParseBehavior | None = None
    effects_downstream: str | None = None
    priority: str | None = None


class StructuralAttackTarget(BaseModel):
    page: int | None = None
    link_text: str | None = None
    original_url: str | None = None
    region: str | None = None


class StructuralAttack(BaseModel):
    attack_id: str | None = None
    technique: str | None = None
    target: StructuralAttackTarget | None = None
    payload_description: str | None = None
    malicious_url: str | None = None
    attack_mechanism: str | None = None
    intent: str | None = None
    effects_downstream: str | None = None
    priority: str | None = None


class DefenseConsiderations(BaseModel):
    overall_detection_difficulty: str | None = None
    safedoc_applicable_attacks: list[str] | None = None
    undetectable_attacks: list[str] | None = None
    recommended_defenses: str | None = None


class ManipulationPlan(BaseModel):
    """Root model for Stage 3 manipulation_plan.json."""

    document_threat_model: DocumentThreatModel | None = None
    text_attacks: list[TextAttack] | None = None
    image_attacks: list[ImageAttack] | None = None
    structural_attacks: list[StructuralAttack] | None = None
    defense_considerations: DefenseConsiderations | None = None
