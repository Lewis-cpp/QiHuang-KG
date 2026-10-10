"""M1a response contracts; JSON source fields retain their original structure."""

from typing import Any, Literal

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class Node(BaseModel):
    id: str
    type: str
    label: str


class DatasetSummary(BaseModel):
    id: str
    title: str


class Alias(BaseModel):
    name: str
    source_record_id: str
    field_path: str


class RelationSummary(BaseModel):
    relation: str
    direction: Literal['in', 'out']
    count: int


class EvidencePreview(BaseModel):
    id: str
    kind: str
    field_path: str
    excerpt: str | None


class EvidenceItem(EvidencePreview):
    source_record_id: str


class EntityDetail(Node):
    dataset: DatasetSummary
    category: str | None
    review_status: str
    review_status_raw: str | None
    source_record_id: str
    attributes: dict[str, Any]
    aliases: list[Alias]
    relation_summary: list[RelationSummary]
    evidence_total: int
    evidence_preview: list[EvidencePreview]
    build_id: str


class EvidencePage(BaseModel):
    items: list[EvidenceItem]
    total: int
    limit: int
    offset: int
    build_id: str
