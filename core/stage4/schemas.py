"""Pydantic schemas for Stage 4 replacements manifest."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReplacementItem(BaseModel):
    """One replacement applied in Stage 4 injection."""

    search_key: str = Field(..., description="Exact value to find and replace.")
    replacement: str = Field(..., description="Replacement value.")
    scope: str | None = Field(default="everywhere", description="'everywhere' or 'single_block'.")
    consistency_note: str | None = Field(
        default=None,
        description="For aggregates: how related elements were updated.",
    )
    semantic_edit_strategy: str | None = Field(
        default=None,
        description="append | update | delete",
    )
    injection_mechanism: str | None = Field(
        default=None,
        description="hidden_text_injection | font_glyph_remapping | visual_overlay",
    )


class ReplacementsManifest(BaseModel):
    """Manifest of replacements applied (stage4/replacements.json)."""

    replacements: list[ReplacementItem] = Field(default_factory=list)


class HiddenTextItem(BaseModel):
    """One hidden-text insertion planned for Stage 4."""

    page: int = Field(ge=0)
    payload: str
    semantic_edit_strategy: str = "append"
    injection_mechanism: str = "hidden_text_injection"
    attack_id: str | None = None
    target_bbox: list[float] | None = None


class HiddenTextManifest(BaseModel):
    """Manifest of hidden-text insertions applied (stage4/hidden_text.json)."""

    insertions: list[HiddenTextItem] = Field(default_factory=list)
