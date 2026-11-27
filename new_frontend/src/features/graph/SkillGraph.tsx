import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { GraduationCap, Map as MapIcon, Minus, Plus } from "lucide-react";
import { memo, useEffect, useMemo, useState } from "react";

import { useConceptMapCourses } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn, mapKey } from "@/lib/utils";
import { usePlanStore } from "@/state/planStore";
import { useThemeStore } from "@/theme/theme";

import { DEFAULT_NEEDED, buildSkillGraph, positionFor, type SkillNodeData } from "./buildSkillGraph";

type SkillNode = Node<SkillNodeData & { hasMap: boolean }>;

const SkillNodeView = memo(function SkillNodeView({ data }: NodeProps<SkillNode>) {
  const isCourse = data.kind !== "career";
  const body = (
    <div
      className={cn(
        "w-[220px] rounded-[10px] border-[1.5px] px-3 py-2 text-left shadow-sm transition-shadow",
        data.kind === "current" && "border-green bg-card-alt",
        data.kind === "needed" && "border-gold bg-card-alt",
        data.kind === "career" && "border-green bg-green text-on-green",
        isCourse && data.hasMap && "cursor-pointer hover:shadow-md hover:ring-2 hover:ring-green/40",
      )}
    >
      <div className="flex items-center gap-1.5">
        {data.kind === "career" && <GraduationCap className="h-3.5 w-3.5 shrink-0" />}
        <span className="truncate text-[13px] font-bold">{data.label}</span>
        {isCourse && data.hasMap && <MapIcon className="ml-auto h-3.5 w-3.5 shrink-0 text-muted" aria-hidden />}
      </div>
      {data.subtitle && (
        <div className={cn("truncate text-xs", data.kind === "career" ? "opacity-80" : "text-muted")}>
          {data.subtitle}
        </div>
      )}
      {data.detail && <div className="mt-0.5 truncate text-[11px] font-medium text-muted">{data.detail}</div>}
      {data.kind !== "current" && <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-muted" />}
      {data.kind !== "career" && <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-muted" />}
    </div>
  );
  const tip = isCourse
    ? data.hasMap
      ? "Open this course's concept map"
      : "No concept map for this course"
    : data.label;
  return (
    <Tooltip delayDuration={400}>
      <TooltipTrigger asChild>{body}</TooltipTrigger>
      <TooltipContent side="top">
        <div className="font-semibold">{data.label}</div>
        {data.subtitle && data.kind !== "career" && <div>{data.subtitle}</div>}
        <div className="text-muted">{tip}</div>
      </TooltipContent>
    </Tooltip>
  );
});

const nodeTypes = { skill: SkillNodeView };

const HEADINGS = ["Current courses", "Courses needed", "Careers"];

function GraphInner({ actions }: { actions?: React.ReactNode }) {
  const plan = usePlanStore((s) => s.plan);
  const audit = usePlanStore((s) => s.audit);
  const openConceptMap = usePlanStore((s) => s.openConceptMap);
  const resolved = useThemeStore((s) => s.resolved);
  const { data: mapCourses } = useConceptMapCourses();
  const [neededCount, setNeededCount] = useState(DEFAULT_NEEDED);
  const { fitView } = useReactFlow();

  const available = useMemo(() => new Set(mapCourses ?? []), [mapCourses]);
  const total = plan?.recommendation?.recommendations.length ?? 0;
  const graph = useMemo(
    () => buildSkillGraph(plan?.recommendation ?? null, audit, plan?.prefs.careers ?? [], neededCount),
    [plan, audit, neededCount],
  );

  const { nodes, edges } = useMemo(() => {
    const sizes: [number, number, number] = [0, 0, 0];
    for (const node of graph.nodes) sizes[node.column] += 1;
    const flowNodes: SkillNode[] = graph.nodes.map((node) => ({
      id: node.id,
      type: "skill",
      position: positionFor(node, sizes),
      data: { ...node.data, hasMap: Boolean(node.data.code && available.has(mapKey(node.data.code))) },
      draggable: true,
      connectable: false,
    }));
    const flowEdges: Edge[] = graph.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: "default",
      animated: edge.kind === "prerequisite",
      style: {
        stroke: edge.kind === "prerequisite" ? "rgb(var(--cw-green))" : "rgb(var(--cw-muted))",
        strokeWidth: 1 + edge.weight * 2,
        opacity: 0.35 + edge.weight * 0.6,
      },
    }));
    return { nodes: flowNodes, edges: flowEdges };
  }, [graph, available]);

  useEffect(() => {
    const id = window.requestAnimationFrame(() => fitView({ padding: 0.15, duration: 200 }));
    return () => window.cancelAnimationFrame(id);
  }, [nodes.length, edges.length, fitView]);

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        colorMode={resolved}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.2}
        maxZoom={2}
        nodesConnectable={false}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => {
          const data = node.data as SkillNode["data"];
          if (data.code && data.hasMap) openConceptMap(mapKey(data.code));
        }}
        aria-label="Skill graph: current courses, courses needed, and careers"
      >
        <Background gap={24} size={1} color="rgb(var(--cw-border))" />
        <Controls showInteractive={false} position="bottom-left" />
      </ReactFlow>

      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 p-3">
        <div className="pointer-events-auto flex flex-wrap items-center gap-2 rounded-btn border bg-card/90 px-3 py-1.5 text-xs text-muted shadow-sm backdrop-blur">
          {HEADINGS.map((heading, i) => (
            <span key={heading} className="flex items-center gap-1.5">
              <span
                className={cn(
                  "inline-block h-2.5 w-2.5 rounded-sm border-[1.5px]",
                  i === 0 && "border-green bg-card-alt",
                  i === 1 && "border-gold bg-card-alt",
                  i === 2 && "border-green bg-green",
                )}
              />
              {heading}
            </span>
          ))}
          {graph.sample && <span className="font-semibold text-gold">Sample data</span>}
        </div>
        <div className="pointer-events-auto flex flex-wrap items-center justify-end gap-2">
        {!graph.sample && total > 1 && (
          <div className="flex items-center gap-1 rounded-btn border bg-card/90 px-1.5 py-1 text-xs shadow-sm backdrop-blur">
            <span className="px-1 text-muted">Courses shown</span>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              aria-label="Show fewer courses"
              disabled={neededCount <= 1}
              onClick={() => setNeededCount((n) => Math.max(1, n - 1))}
            >
              <Minus />
            </Button>
            <span className="w-5 text-center font-semibold tabular-nums">{Math.min(neededCount, total)}</span>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              aria-label="Show more courses"
              disabled={neededCount >= total}
              onClick={() => setNeededCount((n) => Math.min(total, n + 1))}
            >
              <Plus />
            </Button>
          </div>
        )}
        {actions}
        </div>
      </div>
    </div>
  );
}

export function SkillGraph({ actions }: { actions?: React.ReactNode }) {
  return (
    <ReactFlowProvider>
      <GraphInner actions={actions} />
    </ReactFlowProvider>
  );
}
