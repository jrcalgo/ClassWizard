import dagre from "@dagrejs/dagre";

import type { ConceptMap } from "@/api/types";

export const PREDICATE_LABEL: Record<string, string> = {
  PART_OF: "part of",
  PREREQUISITE_OF: "prerequisite of",
  USED_FOR: "used for",
  SUBTYPE_OF: "subtype of",
};

export function nodeSize(label: string): { width: number; height: number } {
  const width = Math.min(240, Math.max(110, label.length * 7 + 28));
  const lines = Math.ceil((label.length * 7 + 28) / 240);
  return { width, height: 22 + lines * 16 };
}

/** Left-to-right dagre layout; isolated concepts (no triples) are gridded underneath. */
export function layoutConceptMap(map: ConceptMap): Map<string, { x: number; y: number; width: number; height: number }> {
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({ rankdir: "LR", nodesep: 18, ranksep: 70, marginx: 20, marginy: 20 });
  graph.setDefaultEdgeLabel(() => ({}));
  const connected = new Set<string>();
  for (const edge of map.edges) {
    connected.add(edge.source);
    connected.add(edge.target);
  }
  const positions = new Map<string, { x: number; y: number; width: number; height: number }>();
  for (const node of map.nodes) {
    if (!connected.has(node.id)) continue;
    graph.setNode(node.id, nodeSize(node.label));
  }
  for (const edge of map.edges) graph.setEdge(edge.source, edge.target);
  dagre.layout(graph);

  let maxY = 0;
  let maxX = 0;
  for (const id of graph.nodes()) {
    const n = graph.node(id);
    if (!n) continue;
    positions.set(id, { x: n.x - n.width / 2, y: n.y - n.height / 2, width: n.width, height: n.height });
    maxY = Math.max(maxY, n.y + n.height / 2);
    maxX = Math.max(maxX, n.x + n.width / 2);
  }

  const isolated = map.nodes.filter((n) => !connected.has(n.id));
  const columns = Math.max(3, Math.floor(Math.max(maxX, 760) / 260));
  const top = positions.size ? maxY + 60 : 0;
  isolated.forEach((node, i) => {
    const size = nodeSize(node.label);
    positions.set(node.id, {
      x: 20 + (i % columns) * 260,
      y: top + Math.floor(i / columns) * 70,
      ...size,
    });
  });
  return positions;
}
