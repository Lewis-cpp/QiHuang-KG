import { collapsedFields, fieldLabels, hiddenFields, safetyFields, subKeyLabels } from './fieldLabels'

export interface AttributeRow { key: string; label: string; value: unknown; secondary?: unknown; missing: boolean }

export const isEmpty = (value: unknown) =>
  value == null || value === '' || (Array.isArray(value) && value.length === 0)

const englishSibling = (key: string) => key.endsWith('_zh') ? `${key.slice(0, -3)}_en` : null

// Rows for an object's own keys: `X_zh` carries `X_en` as secondary text, empty values are dropped.
export function objectRows(object: Record<string, unknown>, labels: Record<string, string> = subKeyLabels): AttributeRow[] {
  const rows: AttributeRow[] = []
  for (const [key, value] of Object.entries(object)) {
    if (isEmpty(value)) continue
    if (key.endsWith('_en') && `${key.slice(0, -3)}_zh` in object) continue
    const sibling = englishSibling(key)
    const base = sibling ? key.slice(0, -3) : key
    rows.push({ key, label: labels[key] ?? labels[base] ?? key, value, secondary: sibling ? object[sibling] : undefined, missing: false })
  }
  return rows
}

export interface AttributeSections { main: AttributeRow[]; safety: AttributeRow[]; collapsed: AttributeRow[]; other: AttributeRow[] }

export function attributeSections(type: string, attributes: Record<string, unknown>): AttributeSections {
  const used = new Set(hiddenFields)
  const row = (key: string, label: string): AttributeRow => {
    const sibling = englishSibling(key)
    used.add(key)
    if (sibling) used.add(sibling)
    const value = attributes[key]
    return { key, label, value, secondary: sibling ? attributes[sibling] : undefined, missing: isEmpty(value) }
  }
  const main = (fieldLabels[type] ?? []).map(([key, label]) => row(key, label))
  const safety = safetyFields
    .filter(([key]) => !isEmpty(attributes[key]) || !isEmpty(attributes[englishSibling(key) ?? '']))
    .map(([key, label]) => row(key, label))
  const collapsed = (collapsedFields[type] ?? []).filter(key => !isEmpty(attributes[key])).map(key => row(key, subKeyLabels[key] ?? key))
  const rest = Object.fromEntries(Object.entries(attributes).filter(([key]) => !used.has(key)))
  return { main, safety, collapsed, other: objectRows(rest, {}) }
}
