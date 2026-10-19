<script setup lang="ts">
import cytoscape, { type Core, type ElementDefinition } from 'cytoscape'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Canvas } from '../graph'
import { relationStyles, typeStyles } from '../graph'

export type Selection = { kind: 'node' | 'edge'; id: string } | null

const props = defineProps<{ canvas: Canvas; centerId: string; selected: Selection }>()
const emit = defineEmits<{ node: [id: string]; edge: [id: string] }>()
const container = ref<HTMLElement | null>(null)
let cy: Core | null = null

function elements(): ElementDefinition[] {
  const nodes = [...props.canvas.nodes.values()].map(n => ({
    group: 'nodes' as const,
    data: { id: n.id, label: n.label, color: typeStyles[n.type]?.color ?? '#6f6f6f', shape: typeStyles[n.type]?.shape ?? 'ellipse' },
    classes: [n.id === props.centerId ? 'center' : '', props.canvas.expanded.has(n.id) ? 'expanded' : ''].join(' '),
  }))
  const edges = [...props.canvas.edges.values()].map(e => {
    const style = relationStyles[e.relation] ?? { color: '#888', dash: [] }
    return {
      group: 'edges' as const,
      data: { id: e.id, source: e.source_id, target: e.target_id, color: style.color, dash: style.dash.length ? style.dash : [1, 0] },
      classes: [style.dash.length ? 'dashed' : '', e.quality_state === 'conflicting' ? 'conflicting' : ''].join(' '),
    }
  })
  return [...nodes, ...edges]
}

const STYLE: cytoscape.StylesheetJson = [
  { selector: 'node', style: {
    'background-color': 'data(color)', shape: 'data(shape)' as any, width: 22, height: 22, label: 'data(label)',
    'font-size': 11, 'font-family': '"Noto Sans CJK SC","Microsoft YaHei",sans-serif', color: '#18372f',
    'text-valign': 'bottom', 'text-margin-y': 4, 'text-wrap': 'ellipsis', 'text-max-width': '110px',
    'text-background-color': '#fffefa', 'text-background-opacity': 0.8, 'text-background-padding': '1px',
    'border-width': 1, 'border-color': '#fffefa',
  } },
  { selector: 'node.expanded', style: { 'border-width': 3, 'border-color': '#d9c7a5' } },
  { selector: 'node.center', style: { width: 34, height: 34, 'font-size': 13, 'font-weight': 'bold', 'border-width': 4, 'border-color': '#af8051' } },
  { selector: 'node:selected', style: { 'overlay-color': '#af8051', 'overlay-opacity': 0.25, 'overlay-padding': 6 } },
  { selector: 'edge', style: {
    width: 1.6, 'line-color': 'data(color)', 'target-arrow-color': 'data(color)', 'target-arrow-shape': 'triangle',
    'arrow-scale': 0.8, 'curve-style': 'bezier', opacity: 0.85,
  } },
  { selector: 'edge.dashed', style: { 'line-style': 'dashed', 'line-dash-pattern': 'data(dash)' as any } },
  { selector: 'edge.conflicting', style: { width: 3, label: '⚠', 'font-size': 14, color: '#a5591f', 'text-background-color': '#fff8ec', 'text-background-opacity': 1 } },
  { selector: 'edge:selected', style: { width: 4, opacity: 1, 'overlay-color': '#af8051', 'overlay-opacity': 0.2 } },
]

function layout(fit = true) {
  cy?.layout({ name: 'cose', animate: false, randomize: false, fit, padding: 30, nodeRepulsion: () => 60000,
    idealEdgeLength: () => 120, nodeOverlap: 20, gravity: 0.2, numIter: 2500, componentSpacing: 80 } as cytoscape.LayoutOptions).run()
}

function sync() {
  if (!cy) return
  const wanted = new Map(elements().map(e => [e.data.id as string, e]))
  const instance = cy
  let changed = false
  instance.batch(() => {
    instance.elements().forEach(el => {
      if (!wanted.has(el.id())) { el.remove(); changed = true }
    })
    const added: ElementDefinition[] = []
    for (const [id, def] of wanted) {
      const existing = instance.getElementById(id)
      if (existing.nonempty()) existing.classes(def.classes as string)
      else added.push(def)
    }
    // New neighbors start next to the node they were reached from, so the layout moves them less.
    for (const def of added.filter(d => d.group === 'nodes')) {
      const anchor = [...props.canvas.edges.values()]
        .map(e => e.source_id === def.data.id ? e.target_id : e.target_id === def.data.id ? e.source_id : null)
        .map(id => id && instance.getElementById(id))
        .find(el => el && el.nonempty())
      const at = anchor ? anchor.position() : { x: 0, y: 0 }
      def.position = { x: at.x + (Math.random() - 0.5) * 60, y: at.y + (Math.random() - 0.5) * 60 }
    }
    if (added.length) { instance.add(added); changed = true }
  })
  if (changed) layout()
  highlight()
}

function highlight() {
  if (!cy) return
  cy.elements(':selected').unselect()
  if (props.selected) cy.getElementById(props.selected.id).select()
}

onMounted(() => {
  cy = cytoscape({ container: container.value, style: STYLE, minZoom: 0.2, maxZoom: 3, boxSelectionEnabled: false,
    autounselectify: false, selectionType: 'single' })
  cy.on('tap', 'node', event => emit('node', event.target.id()))
  cy.on('tap', 'edge', event => emit('edge', event.target.id()))
  sync()
})
watch(() => props.canvas, sync)
watch(() => props.selected, highlight)
onBeforeUnmount(() => { cy?.destroy(); cy = null })

defineExpose({ relayout: () => layout(), fit: () => cy?.fit(undefined, 30) })
</script>

<template>
  <div ref="container" class="graph-canvas" role="img" aria-label="关系图画布；同样的内容见下方的关系列表，可以用键盘操作。"></div>
</template>
