// Mirrors backend/schemas.py; field names match the API exactly.

export type Direction = 'in' | 'out'

export interface Node { id: string; type: string; label: string }

export interface Match { field: 'name' | 'alias'; text: string }

export interface EntityHit extends Node {
  dataset_id: string
  category: string | null
  review_status: string
  match: Match | null
}

export interface EntityPage { items: EntityHit[]; total: number; limit: number; offset: number; build_id: string }

export interface Alias { name: string; source_record_id: string; field_path: string }

export interface RelationSummary { relation: string; direction: Direction; count: number }

export interface EvidencePreview { id: string; kind: string; field_path: string; excerpt: string | null }

export interface EvidenceItem extends EvidencePreview { source_record_id: string }

export interface EntityDetail extends Node {
  dataset: { id: string; title: string }
  category: string | null
  review_status: string
  review_status_raw: string | null
  source_record_id: string
  attributes: Record<string, unknown>
  aliases: Alias[]
  relation_summary: RelationSummary[]
  evidence_total: number
  evidence_preview: EvidencePreview[]
  same_name_entities: Node[]
  build_id: string
}

export interface EvidencePage { items: EvidenceItem[]; total: number; limit: number; offset: number; build_id: string }

export interface NeighborEdge {
  id: string
  relation: string
  properties: Record<string, unknown>
  quality_state: string
  evidence_ids: string[]
}

export interface NeighborItem { edge: NeighborEdge; neighbor: Node & { category: string | null } }

export interface NeighborPage {
  entity_id: string
  relation: string
  direction: Direction
  items: NeighborItem[]
  total: number
  limit: number
  offset: number
  build_id: string
}

export interface Dataset {
  id: string
  title: string
  version_label: string
  source_url: string
  license_statement: string
  attribution: string
}

export interface DatasetEntry extends Dataset { counts: { entities: number; edges: number; source_records: number } }

export interface DatasetPage { items: DatasetEntry[]; total: number; build_id: string }

export interface SourceRecord {
  id: string
  dataset_id: string
  filename: string
  record_key: string
  record_locator: string
  file_sha256: string
  content: Record<string, unknown> | null
  content_truncated: boolean
}

export interface EvidenceDetail extends EvidencePreview {
  target:
    | { kind: 'entity'; entity: Node }
    | { kind: 'edge'; edge: { id: string; relation: string; source: Node; target: Node } }
  raw_value: unknown
  source_record: SourceRecord
  dataset: Dataset
  build_id: string
}

export interface Stats {
  build_id: string
  entities: number
  edges: number
  business_records: number
  evidence: number
  entity_types: Record<string, number>
  relations: Record<string, number>
}

export interface Service { status: string; message?: string; projection?: string; version?: string; engine?: string }

export interface Health { status: string; services: Record<string, Service> }

export interface NoteSource { id: string; label: string; fields: Record<string, unknown> }

export interface FormulaNotes {
  entity_id: string
  patterns: (NoteSource & { evidence_ids: string[] })[]
  herbs: NoteSource[]
  build_id: string
}

export interface GraphEdge {
  id: string
  source_id: string
  target_id: string
  relation: string
  quality_state: string
  evidence_ids: string[]
  properties: Record<string, unknown>
}

export interface GraphResponse {
  center: string
  nodes: Node[]
  edges: GraphEdge[]
  truncated: boolean
  limits: { nodes: number; edges: number }
  relation_counts: (RelationSummary & { source: 'relational' })[]
  build_id: string
}
