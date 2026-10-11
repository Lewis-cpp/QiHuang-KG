import type { Direction } from './api/types'

export const typeNames: Record<string, string> = {
  herb: '中药', formula: '经典方剂', pattern: '证候', text: '古籍', tcm_term: '中医术语',
  patent_medicine: '中成药', herbal_piece: '中药饮片', icd11_code: 'ICD-11 编码', medicinal_property: '药性',
}

export const datasetNames: Record<string, string> = { bencaodian: '本草典', 'tcm-mkg': 'TCM-MKG' }

export const reviewNames: Record<string, string> = {
  editor_reviewed: '编辑已审核', draft: '草稿', needs_review: '待审核', unknown: '来源提供 · 未审核',
}

export const evidenceKinds: Record<string, string> = {
  curated: '整理数据', bibliographic: '书目', source_quote: '原文引用',
}

export const roleNames: Record<string, string> = { jun: '君', chen: '臣', zuo: '佐', shi: '使' }

export const serviceStates: Record<string, string> = {
  ready: '连接正常', verified: '调用已验证', not_configured: '尚未配置', not_verified: '等待验证',
  unavailable: '暂不可用', blocked: '验证未通过',
}

export const projectionNames: Record<string, string> = { sample: '样例投影', full: '全量投影', not_ready: '未就绪' }

// spec §5.6: section order and titles for each (relation, direction).
export const relationSections: { relation: string; out: string; in: string }[] = [
  { relation: 'CONTAINS', out: '组成', in: '收录该药的方剂' },
  { relation: 'ASSOCIATED_WITH_PATTERN', out: '关联证候', in: '关联该证候的方剂' },
  { relation: 'CITED_IN', out: '出处古籍', in: '引用该书的条目' },
  { relation: 'HAS_HERBAL_PIECE', out: '饮片组成', in: '含该饮片的中成药' },
  { relation: 'ASSOCIATED_WITH_TERM', out: '关联术语', in: '关联该术语的中成药' },
  { relation: 'MAPPED_TO_ICD11', out: 'ICD-11 编码', in: '映射到该编码的中成药' },
  { relation: 'HAS_MEDICINAL_PROPERTY', out: '药性', in: '具有该药性的饮片' },
]

export const relationNames: Record<string, string> = {
  CONTAINS: '包含', ASSOCIATED_WITH_PATTERN: '关联证候', CITED_IN: '出处', HAS_HERBAL_PIECE: '含饮片',
  ASSOCIATED_WITH_TERM: '关联术语', MAPPED_TO_ICD11: '映射 ICD-11', HAS_MEDICINAL_PROPERTY: '具有药性',
}

export function sectionTitle(relation: string, direction: Direction): string {
  const section = relationSections.find(s => s.relation === relation)
  return section ? section[direction] : `${relation}（${direction === 'out' ? '出边' : '入边'}）`
}

export const label = (map: Record<string, string>, value: string | null | undefined) =>
  value == null ? '' : map[value] ?? value

export const number = (n: number | undefined | null) => n == null ? '—' : n.toLocaleString('zh-CN')

export function setTitle(name: string) {
  document.title = `${name} · 岐黄知图`
}

// After async content replaces a placeholder heading, focus falls back to <body>; move it to the new heading.
export function refocusHeading() {
  setTimeout(() => {
    const active = document.activeElement
    if (!active || active === document.body) document.querySelector<HTMLElement>('main h1')?.focus({ preventScroll: true })
  })
}
