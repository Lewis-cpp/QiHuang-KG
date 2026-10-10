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


class Dataset(DatasetSummary):
    version_label: str
    source_url: str
    license_statement: str
    attribution: str


class SourceRecord(BaseModel):
    id: str
    dataset_id: str
    filename: str
    record_key: str
    record_locator: str
    file_sha256: str
    content: dict[str, Any] | None
    content_truncated: bool


class EvidenceEdge(BaseModel):
    id: str
    relation: str
    source: Node
    target: Node


class EntityTarget(BaseModel):
    kind: Literal['entity']
    entity: Node


class EdgeTarget(BaseModel):
    kind: Literal['edge']
    edge: EvidenceEdge


class EvidenceDetail(EvidencePreview):
    target: EntityTarget | EdgeTarget
    raw_value: Any
    source_record: SourceRecord
    dataset: Dataset
    build_id: str

