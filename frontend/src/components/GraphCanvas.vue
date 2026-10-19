<script setup lang="ts">
import cytoscape from 'cytoscape'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { GraphEdge, Node } from '../api/types'
import { relationStyles, typeColors } from '../labels'

const props = defineProps<{ nodes: Node[]; edges: GraphEdge[]; center: string; selectedNode: string | null; selectedEdge: string | null }>()
const emit = defineEmits<{ 'select-node': [id: string]; 'select-edge': [id: string] }>()

const host = ref<HTMLDivElement>()
let cy: cytoscape.Core | undefined

const SHAPES: Record<string, cytoscape.Css.NodeShape> = { formula: 'round-rectangle', pattern: 'diamond', text: 'rectangle' }

function style(): cytoscape.StylesheetJson {
  const rules: cytoscape.StylesheetJson = [
    { selector: 'node', style: {
      label: 'data(label)', 'font-size': 12, 'text-valign': 'bottom', 'text-margin-y': 4, 'text-wrap': 'ellipsis',
      'text-max-width': '90px', color: '#18372f', 'background-color': 'data(color)', width: 26, height: 26,
      shape: 'data(shape)' as unknown as cytoscape.Css.NodeShape, 'border-width': 0 } },
    { selector: 'node.center', style: { width: 38, height: 38, 'border-width': 3, 'border-color': '#af8051', 'font-weight': 700 } },
    { selector: 'node:selected', style: { 'border-width': 4, 'border-color': '#102f25' } },
    { selector: 'edge', style: {
      width: 2, 'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'arrow-scale': 0.9,
      'line-color': 'data(color)', 'target-arrow-color': 'data(color)', 'line-style': 'data(line)' as unknown as 'solid' } },
    { selector: 'edge[quality = "conflicting"]', style: { width: 4 } },
    { selector: 'edge:selected', style: { width: 5, 'overlay-color': '#102f25', 'overlay-opacity': 0.12 } },
  ]
  return rules
}

function nodeData(n: Node) {
  return { id: n.id, label: n.label, color: typeColors[n.type] ?? '#7d8a82', shape: SHAPES[n.type] ?? 'ellipse' }
}

function edgeData(e: GraphEdge) {
  const s = relationStyles[e.relation]
  return { id: e.id, source: e.source_id, target: e.target_id, color: s?.color ?? '#7d8a82', line: s?.line ?? 'solid', quality: e.quality_state }
}

// Add what is new and drop what is gone; only lay out again when the element set changed.
function sync() {
  if (!cy) return
  const nodeIds = new Set(props.nodes.map(n => n.id))
  const edgeIds = new Set(props.edges.map(e => e.id))
  let changed = false
  cy.batch(() => {
    cy!.edges().filter(e => !edgeIds.has(e.id())).forEach(e => { e.remove(); changed = true })
    cy!.nodes().filter(n => !nodeIds.has(n.id())).forEach(n => { n.remove(); changed = true })
    for (const n of props.nodes) if (cy!.getElementById(n.id).empty()) { cy!.add({ group: 'nodes', data: nodeData(n) }); changed = true }
    for (const e of props.edges) if (cy!.getElementById(e.id).empty()) { cy!.add({ group: 'edges', data: edgeData(e) }); changed = true }
    cy!.nodes().removeClass('center')
    cy!.getElementById(props.center).addClass('center')
  })
  if (changed) cy.layout({ name: 'cose', animate: false, fit: true, padding: 30, nodeDimensionsIncludeLabels: true, randomize: false } as cytoscape.LayoutOptions).run()
}

function select() {
  if (!cy) return
  cy.elements().unselect()
  if (props.selectedEdge) cy.getElementById(props.selectedEdge).select()
  else if (props.selectedNode) cy.getElementById(props.selectedNode).select()
}

onMounted(() => {
  cy = cytoscape({ container: host.value, style: style(), minZoom: 0.2, maxZoom: 3, boxSelectionEnabled: false })
  cy.on('tap', 'node', event => emit('select-node', event.target.id()))
  cy.on('tap', 'edge', event => emit('select-edge', event.target.id()))
  sync()
  select()
})
watch(() => [props.nodes, props.edges, props.center], sync)
watch(() => [props.selectedNode, props.selectedEdge], select)
onBeforeUnmount(() => cy?.destroy())

const summary = () => `关系图：${props.nodes.length} 个节点，${props.edges.length} 条关系。下方文字列表提供相同内容。`
defineExpose({ fit: () => cy?.fit(undefined, 30) })
</script>

<template>
  <div ref="host" class="graph-canvas" role="img" :aria-label="summary()"></div>
</template>
