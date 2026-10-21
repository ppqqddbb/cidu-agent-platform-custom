'use client'

import type {
  Edge,
  EdgeProps,
  Node,
  NodeProps,
} from 'reactflow'
import type {
  KnowledgeGraphOverviewNode,
  KnowledgeGraphOverviewRelationship,
} from '@/models/knowledge-graph'
import { cn } from '@langgenius/dify-ui/cn'
import {
  memo,
  useCallback,
  useMemo,
} from 'react'
import ReactFlow, {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  getBezierPath,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
} from 'reactflow'
import 'reactflow/dist/style.css'

type GraphNodeData = {
  name: string
  type: string
  labels: string[]
  description: string
  highlighted: boolean
  dimmed: boolean
}

type GraphEdgeData = {
  label: string
  highlighted: boolean
  dimmed: boolean
}

type KnowledgeGraphCanvasProps = {
  nodes: KnowledgeGraphOverviewNode[]
  relationships: KnowledgeGraphOverviewRelationship[]
  selectedNodeId?: string
  highlightedNodeIds?: Set<string>
  highlightedRelationshipIds?: Set<string>
  onNodeSelect?: (nodeId: string | undefined) => void
  className?: string
}

const NODE_WIDTH = 196
const NODE_HEIGHT = 58
const COLUMN_GAP = 280
const ROW_GAP = 92

const TYPE_RANK: Record<string, number> = {
  SelectionRoot: 0,
  Catalog: 1,
  ProductModel: 2,
}

const TREE_RELATION_TYPES = new Set([
  'HAS_SELECTION_CATEGORY',
  'HAS_CHILD_CATEGORY',
  'HAS_PRODUCT_MODEL',
])

const getTypeRank = (type: string) => TYPE_RANK[type] ?? 7

const getLayeredPositions = (
  nodes: KnowledgeGraphOverviewNode[],
  relationships: KnowledgeGraphOverviewRelationship[],
) => {
  const nodeIds = new Set(nodes.map(node => node.id))
  const nodeById = new Map(nodes.map(node => [node.id, node]))
  const adjacency = new Map<string, string[]>()
  const indegree = new Map<string, number>()
  const levels = new Map<string, number>()

  nodes.forEach((node) => {
    adjacency.set(node.id, [])
    indegree.set(node.id, 0)
  })

  relationships.forEach((relationship) => {
    if (!TREE_RELATION_TYPES.has(relationship.relation_type))
      return
    const sourceId = relationship.source_id
    const targetId = relationship.target_id
    if (!sourceId || !targetId || !nodeIds.has(sourceId) || !nodeIds.has(targetId))
      return

    adjacency.get(sourceId)?.push(targetId)
    indegree.set(targetId, (indegree.get(targetId) ?? 0) + 1)
  })

  const roots = nodes
    .filter(node => (indegree.get(node.id) ?? 0) === 0)
    .sort((a, b) => getTypeRank(a.type) - getTypeRank(b.type) || a.name.localeCompare(b.name))
  const queue = roots.map((node) => {
    levels.set(node.id, getTypeRank(node.type) === 0 ? 0 : getTypeRank(node.type))
    return node.id
  })

  for (let index = 0; index < queue.length; index += 1) {
    const nodeId = queue[index]
    if (!nodeId)
      continue
    const sourceLevel = levels.get(nodeId) ?? 0
    ;(adjacency.get(nodeId) || []).forEach((targetId) => {
      if (levels.has(targetId))
        return
      const targetNode = nodeById.get(targetId)
      const nextLevel = Math.max(sourceLevel + 1, getTypeRank(targetNode?.type || ''))
      levels.set(targetId, nextLevel)
      queue.push(targetId)
    })
  }

  nodes.forEach((node) => {
    if (!levels.has(node.id))
      levels.set(node.id, getTypeRank(node.type))
  })

  const groups = new Map<number, KnowledgeGraphOverviewNode[]>()
  nodes.forEach((node) => {
    const level = levels.get(node.id) ?? 0
    groups.set(level, [...(groups.get(level) || []), node])
  })

  const positions = new Map<string, { x: number, y: number }>()
  Array.from(groups.entries())
    .sort(([levelA], [levelB]) => levelA - levelB)
    .forEach(([level, group]) => {
      const sortedGroup = [...group].sort((a, b) => {
        const rankDiff = getTypeRank(a.type) - getTypeRank(b.type)
        if (rankDiff)
          return rankDiff
        return a.name.localeCompare(b.name)
      })
      const startY = -((sortedGroup.length - 1) * ROW_GAP) / 2
      sortedGroup.forEach((node, index) => {
        positions.set(node.id, {
          x: level * COLUMN_GAP,
          y: startY + index * ROW_GAP,
        })
      })
    })

  return positions
}

const GraphNode = memo(({ data, selected }: NodeProps<GraphNodeData>) => {
  const label = data.labels[0] || data.type

  return (
    <div
      className={cn(
        'relative flex h-[58px] w-[196px] flex-col justify-center rounded-lg border border-components-card-border bg-components-card-bg px-3 text-left shadow-xs transition-all',
        data.dimmed && 'opacity-25',
        data.highlighted && 'border-util-colors-blue-blue-600 bg-util-colors-blue-blue-50 shadow-lg shadow-util-colors-blue-blue-200',
        selected && 'border-util-colors-blue-blue-600 shadow-lg shadow-util-colors-blue-blue-100',
      )}
      title={[data.name, label, data.description].filter(Boolean).join('\n')}
    >
      <Handle className="opacity-0" type="target" position={Position.Top} />
      <Handle className="opacity-0" type="target" position={Position.Left} />
      <Handle className="opacity-0" type="source" position={Position.Right} />
      <Handle className="opacity-0" type="source" position={Position.Bottom} />
      <div className="truncate system-sm-semibold text-text-primary">
        {data.name}
      </div>
      {!!label && (
        <div className="mt-0.5 truncate system-xs-regular text-text-tertiary">
          {label}
        </div>
      )}
    </div>
  )
})
GraphNode.displayName = 'GraphNode'

const GraphEdge = memo(({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  markerEnd,
}: EdgeProps<GraphEdgeData>) => {
  const [
    edgePath,
    labelX,
    labelY,
  ] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition: Position.Right,
    targetX,
    targetY,
    targetPosition: Position.Left,
    curvature: 0.2,
  })

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: data?.highlighted ? '#2563eb' : '#8e97a6',
          strokeWidth: data?.highlighted ? 2.4 : 1.6,
          opacity: data?.dimmed ? 0.18 : 1,
        }}
      />
      <EdgeLabelRenderer>
        <div
          className={cn(
            'rounded bg-background-default px-1.5 py-0.5 system-xs-medium text-text-tertiary opacity-0 shadow-xs transition-opacity',
            data?.highlighted && 'opacity-100',
            data?.highlighted && 'text-util-colors-blue-blue-600',
            data?.dimmed && 'opacity-30',
          )}
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: 'none',
          }}
        >
          {data?.label}
        </div>
      </EdgeLabelRenderer>
    </>
  )
})
GraphEdge.displayName = 'GraphEdge'

const nodeTypes = {
  graphNode: GraphNode,
}

const edgeTypes = {
  graphEdge: GraphEdge,
}

const buildFlowNodes = (
  nodes: KnowledgeGraphOverviewNode[],
  relationships: KnowledgeGraphOverviewRelationship[],
  highlightedNodeIds?: Set<string>,
): Node<GraphNodeData>[] => {
  const hasHighlights = !!highlightedNodeIds?.size
  const positions = getLayeredPositions(nodes, relationships)

  return nodes.map(node => ({
    id: node.id,
    type: 'graphNode',
    position: positions.get(node.id) || { x: 0, y: 0 },
    data: {
      name: node.name || node.id,
      type: node.type,
      labels: node.labels,
      description: node.description,
      highlighted: !!highlightedNodeIds?.has(node.id),
      dimmed: hasHighlights && !highlightedNodeIds?.has(node.id),
    },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  }))
}

const applySelectedNode = (
  nodes: Node<GraphNodeData>[],
  selectedNodeId?: string,
): Node<GraphNodeData>[] => {
  return nodes.map(node => ({
    ...node,
    selected: node.id === selectedNodeId,
  }))
}

const buildFlowEdges = (
  relationships: KnowledgeGraphOverviewRelationship[],
  nodeLookup: Map<string, KnowledgeGraphOverviewNode>,
  highlightedRelationshipIds?: Set<string>,
): Edge<GraphEdgeData>[] => {
  const hasHighlights = !!highlightedRelationshipIds?.size

  return relationships.reduce<Edge<GraphEdgeData>[]>((edges, relationship) => {
    const sourceId = relationship.source_id || nodeLookup.get(relationship.source_name)?.id
    const targetId = relationship.target_id || nodeLookup.get(relationship.target_name)?.id

    if (!sourceId || !targetId || !nodeLookup.has(sourceId) || !nodeLookup.has(targetId))
      return edges

    edges.push({
      id: relationship.id,
      source: sourceId,
      target: targetId,
      type: 'graphEdge',
      data: {
        label: relationship.relation_type,
        highlighted: highlightedRelationshipIds?.has(relationship.id) || false,
        dimmed: hasHighlights && !highlightedRelationshipIds?.has(relationship.id),
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 18,
        height: 18,
        color: '#8e97a6',
      },
    })
    return edges
  }, [])
}

const KnowledgeGraphCanvasInner = ({
  nodes,
  relationships,
  selectedNodeId,
  highlightedNodeIds,
  highlightedRelationshipIds,
  onNodeSelect,
  className,
}: KnowledgeGraphCanvasProps) => {
  const nodeLookup = useMemo(() => {
    const lookup = new Map<string, KnowledgeGraphOverviewNode>()
    nodes.forEach((node) => {
      lookup.set(node.id, node)
      lookup.set(node.name, node)
    })
    return lookup
  }, [nodes])
  const initialNodes = useMemo(() => {
    return applySelectedNode(buildFlowNodes(nodes, relationships, highlightedNodeIds), selectedNodeId)
  }, [highlightedNodeIds, nodes, relationships, selectedNodeId])
  const initialEdges = useMemo(() => {
    return buildFlowEdges(relationships, nodeLookup, highlightedRelationshipIds)
  }, [highlightedRelationshipIds, nodeLookup, relationships])
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState(initialNodes)
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState(initialEdges)
  const flowKey = useMemo(() => {
    return [
      nodes.map(node => node.id).join('|'),
      relationships.map(relationship => relationship.id).join('|'),
      selectedNodeId || '',
      Array.from(highlightedNodeIds || []).join('|'),
      Array.from(highlightedRelationshipIds || []).join('|'),
    ].join('::')
  }, [highlightedNodeIds, highlightedRelationshipIds, nodes, relationships, selectedNodeId])

  const handleInit = useCallback(() => {
    setFlowNodes(initialNodes)
    setFlowEdges(initialEdges)
  }, [initialEdges, initialNodes, setFlowEdges, setFlowNodes])

  return (
    <div className={cn('h-[560px] overflow-hidden rounded-xl border-[0.5px] border-components-card-border bg-background-default shadow-xs', className)}>
      <ReactFlow
        key={flowKey}
        fitView
        fitViewOptions={{
          padding: 0.18,
        }}
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onInit={handleInit}
        onNodeClick={(_, node) => onNodeSelect?.(node.id)}
        onPaneClick={() => onNodeSelect?.(undefined)}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
        minZoom={0.25}
        maxZoom={1.8}
        proOptions={{
          hideAttribution: true,
        }}
      >
        <Background gap={18} size={1.5} color="#d7dde6" />
        <MiniMap
          pannable
          zoomable
          nodeColor="#c58abd"
          maskColor="rgba(245, 247, 250, 0.72)"
          className="rounded-lg! border-[0.5px]! border-divider-subtle! bg-background-default-subtle! shadow-md!"
        />
        <Controls showInteractive={false} className="rounded-lg! border-[0.5px]! border-divider-subtle! shadow-md!" />
      </ReactFlow>
    </div>
  )
}

const KnowledgeGraphCanvas = (props: KnowledgeGraphCanvasProps) => {
  return (
    <ReactFlowProvider>
      <KnowledgeGraphCanvasInner {...props} />
    </ReactFlowProvider>
  )
}

export default KnowledgeGraphCanvas
