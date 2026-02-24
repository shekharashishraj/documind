"""Pydantic schemas for Stage 2 analysis.json validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RelatedElement(BaseModel):
    """A related element (e.g. component of an aggregate)."""

    page: int | None = None
    block_index_or_region: int | str | None = None
    content_preview: str | None = None


class Stage2SensitiveElement(BaseModel):
    """One sensitive element from Stage 2 analysis."""

    element_type: str | None = None
    page: int | None = None
    block_index_or_region: int | str | None = None
    content_preview: str | None = None
    sensitivity_type: str | None = None
    sensitivity_level: str | None = None
    decision_impact: str | None = Field(
        default=None,
        description="How changing this field affects the document's primary decision or outcome.",
    )
    value_to_replace: str | None = Field(
        default=None,
        description="Exact canonical value to replace document-wide (e.g. person name, amount, date).",
    )
    related_elements: list[RelatedElement] | None = Field(
        default=None,
        description="When this element is an aggregate (e.g. total amount), list related elements that must change consistently.",
    )


class Stage2Contains(BaseModel):
    """Document contains flags."""

    images: bool | None = None
    tables: bool | None = None
    code: bool | None = None
    equations: bool | None = None
    forms: bool | None = None
    signatures: bool | None = None
    watermarks: bool | None = None
    headers_footers: bool | None = None
    links: bool | None = None
    other: list[str] | None = None


class Stage2Metadata(BaseModel):
    """Document metadata."""

    suggested_tags: list[str] | None = None
    language: str | None = None
    page_count: int | None = None
    other: dict[str, Any] | None = None


class InjectableRegion(BaseModel):
    page: int | None = None
    region: str | None = None
    description: str | None = None


class RenderParseGap(BaseModel):
    page: int | None = None
    description: str | None = None


class RedactableTarget(BaseModel):
    page: int | None = None
    block_index: int | None = None
    content_preview: str | None = None
    impact: str | None = None


class TextSurface(BaseModel):
    injectable_regions: list[InjectableRegion] | None = None
    render_parse_gaps: list[RenderParseGap] | None = None
    redactable_targets: list[RedactableTarget] | None = None


class ImageSurfaceItem(BaseModel):
    page: int | None = None
    xref: int | None = None
    content_description: str | None = None
    role_in_document: str | None = None
    vision_model_reliance: str | None = None


class ImageSurface(BaseModel):
    image_count: int | None = None
    images: list[ImageSurfaceItem] | None = None


class LinkItem(BaseModel):
    page: int | None = None
    link_text: str | None = None
    target_url: str | None = None
    link_type: str | None = None
    risk_level: str | None = None


class StructureSurface(BaseModel):
    has_forms: bool | None = None
    has_javascript: bool | None = None
    has_annotations: bool | None = None
    has_layers: bool | None = None
    has_embedded_files: bool | None = None
    has_links: bool | None = None
    links: list[LinkItem] | None = None
    font_diversity: str | None = None


class AttackSurface(BaseModel):
    text_surface: TextSurface | None = None
    image_surface: ImageSurface | None = None
    structure_surface: StructureSurface | None = None


class DownstreamConsumer(BaseModel):
    consumer: str | None = None
    processing_path: str | None = None
    reliance_on_text: str | None = None
    reliance_on_images: str | None = None
    vulnerability_notes: str | None = None


class RiskProfile(BaseModel):
    primary_risks: list[str] | None = None
    domain_specific_risks: str | None = None
    overall_risk_level: str | None = None


class Stage2Analysis(BaseModel):
    """Root model for Stage 2 analysis.json."""

    summary: str | None = None
    domain: str | None = None
    intended_task: str | None = None
    sub_tasks: list[str] | None = None
    original_document_source: str | None = None
    decision_fields: str | None = Field(
        default=None,
        description="The 1-3 fields that control the document's primary decision or outcome.",
    )
    contains: Stage2Contains | None = None
    metadata: Stage2Metadata | None = None
    sensitive_elements: list[Stage2SensitiveElement] | None = None
    attack_surface: AttackSurface | None = None
    downstream_consumers: list[DownstreamConsumer] | None = None
    risk_profile: RiskProfile | None = None
