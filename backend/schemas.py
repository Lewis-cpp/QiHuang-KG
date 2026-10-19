"""M1 response contracts; JSON source fields retain their original structure."""

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
    same_name_entities: list[Node]
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


class RelationPath(BaseModel):
    node_ids: list[str]
    edge_ids: list[str]


class RelationEdge(BaseModel):
    id: str
    relation: str
    source_id: str
    target_id: str
    properties: dict[str, Any]
    quality_state: str
    evidence_ids: list[str]


class RelationPage(BaseModel):
    template: Literal['formula_herbs', 'herb_formulas', 'formula_patterns', 'herb_patterns_via_formula',
                      'patent_medicine_pieces', 'piece_patent_medicines', 'piece_properties']
    entity_id: str
    paths: list[RelationPath]
    nodes: dict[str, Node]
    edges: dict[str, RelationEdge]
    note: str | None = None
    total: int
    limit: int
    offset: int
    build_id: str


class Match(BaseModel):
    field: Literal['name', 'alias']
    text: str


class EntityHit(Node):
    dataset_id: str
    category: str | None
    review_status: str
    match: Match | None


class EntityPage(BaseModel):
    items: list[EntityHit]
    total: int
    limit: int
    offset: int
    build_id: str


class NeighborEdge(BaseModel):
    id: str
    relation: str
    properties: dict[str, Any]
    quality_state: str
    evidence_ids: list[str]


class Neighbor(Node):
    category: str | None


class NeighborItem(BaseModel):
    edge: NeighborEdge
    neighbor: Neighbor


class NeighborPage(BaseModel):
    entity_id: str
    relation: str
    direction: Literal['in', 'out']
    items: list[NeighborItem]
    total: int
    limit: int
    offset: int
    build_id: str


class DatasetCounts(BaseModel):
    entities: int
    edges: int
    source_records: int


class DatasetEntry(Dataset):
    counts: DatasetCounts


class DatasetPage(BaseModel):
    items: list[DatasetEntry]
    total: int
    build_id: str


class GraphNode(Node):
    category: str | None
    usage: int  # edges pointing at the node in the graph; a data-coverage count, not clinical frequency


class GraphLimits(BaseModel):
    nodes: int
    edges: int


class GraphPage(BaseModel):
    center: str
    nodes: list[GraphNode]
    edges: list[RelationEdge]
    truncated: bool
    limits: GraphLimits
    relations: list[str]
    relation_counts: list[RelationSummary]
    relation_counts_source: str
    graph_source: Literal['neo4j']
    build_id: str


class NoteSource(BaseModel):
    id: str
    label: str
    fields: dict[str, Any]


class PatternNote(NoteSource):
    evidence_ids: list[str]


class FormulaNotes(BaseModel):
    entity_id: str
    patterns: list[PatternNote]
    herbs: list[NoteSource]
    build_id: str
