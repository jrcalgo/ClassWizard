import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Check, ChevronsUpDown } from "lucide-react";
import { memo, useEffect, useMemo, useState } from "react";

import { useConceptMap, useConceptMapCourses } from "@/api/queries";
import type { ConceptNode } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Spinner } from "@/components/ui/spinner";
import { defaultConceptCourse } from "@/lib/plan";
import { cn } from "@/lib/utils";
import { usePlanStore } from "@/state/planStore";
import { useThemeStore } from "@/theme/theme";

import { PREDICATE_LABEL, layoutConceptMap } from "./conceptLayout";

type ConceptFlowNode = Node<ConceptNode & { width: number } & Record<string, unknown>>;

const ConceptNodeView = memo(function ConceptNodeView({ data }: NodeProps<ConceptFlowNode>) {
  const inferred = data.status === "inferred";
  return (
    <div
      style={{ width: data.width }}
      title={`${data.label} · ${data.type}${inferred ? " · inferred" : ""}${data.occurrences ? ` · mentioned ${data.occurrences}×` : ""}`}
      className={cn(
        "rounded-[10px] border-[1.5px] bg-card-alt px-2.5 py-1.5 text-center text-xs leading-4 text-text shadow-sm",
        data.type === "topic" ? "border-green" : "border-gold",
        inferred && "border-dashed",
      )}
    >
      <Handle type="target" position={Position.Left} className="!h-1.5 !w-1.5 !border-0 !bg-muted" />
      {data.label}
      <Handle type="source" position={Position.Right} className="!h-1.5 !w-1.5 !border-0 !bg-muted" />
    </div>
  );
});

const nodeTypes = { concept: ConceptNodeView };

function CoursePicker({ courses, value, onChange }: { courses: string[]; value: string | null; onChange: (c: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" role="combobox" aria-expanded={open} aria-label="Course map" className="w-56 justify-between">
          {value ? value.replace(/_/g, " ") : "Choose a course"}
          <ChevronsUpDown className="opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64">
        <Command>
          <CommandInput placeholder="Search course concept maps…" />
          <CommandList>
            <CommandEmpty>No course found.</CommandEmpty>
            {courses.map((course) => (
              <CommandItem
                key={course}
                value={course.replace(/_/g, " ")}
                onSelect={() => {
                  onChange(course);
                  setOpen(false);
                }}
              >
                <Check className={cn("h-4 w-4", course === value ? "opacity-100" : "opacity-0")} />
                {course.replace(/_/g, " ")}
              </CommandItem>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

function ConceptCanvas({ course }: { course: string }) {
  const { data, isLoading, error } = useConceptMap(course);
  const resolved = useThemeStore((s) => s.resolved);

  const { nodes, edges } = useMemo(() => {
    if (!data) return { nodes: [] as ConceptFlowNode[], edges: [] as Edge[] };
    const positions = layoutConceptMap(data);
    const flowNodes: ConceptFlowNode[] = data.nodes.map((node) => {
      const p = positions.get(node.id) ?? { x: 0, y: 0, width: 140, height: 30 };
      return { id: node.id, type: "concept", position: { x: p.x, y: p.y }, data: { ...node, width: p.width } };
    });
    const flowEdges: Edge[] = data.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: PREDICATE_LABEL[edge.predicate] ?? edge.predicate.toLowerCase().replace(/_/g, " "),
      labelStyle: { fontSize: 10 },
      labelBgPadding: [4, 2] as [number, number],
      markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
      style: edge.predicate === "PREREQUISITE_OF" ? { stroke: "rgb(var(--cw-gold))" } : undefined,
    }));
    return { nodes: flowNodes, edges: flowEdges };
  }, [data]);

  if (isLoading)
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-muted">
        <Spinner /> Loading concept map…
      </div>
    );
  if (error || !data)
    return <div className="flex h-full items-center justify-center text-sm text-muted">This concept map could not be loaded.</div>;
  if (!data.nodes.length)
    return <div className="flex h-full items-center justify-center text-sm text-muted">This course has no concepts yet.</div>;

  return (
    <ReactFlow
      key={course}
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      colorMode={resolved}
      fitView
      fitViewOptions={{ padding: 0.1 }}
      minZoom={0.05}
      maxZoom={3}
      nodesConnectable={false}
      zoomOnDoubleClick={false}
      proOptions={{ hideAttribution: true }}
      aria-label={`Concept map for ${course.replace(/_/g, " ")}`}
    >
      <Background gap={24} size={1} color="rgb(var(--cw-border))" />
      <Controls showInteractive={false} />
      <MiniMap
        pannable
        zoomable
        nodeColor="rgb(var(--cw-muted))"
        nodeStrokeColor="rgb(var(--cw-green))"
        nodeStrokeWidth={2}
        nodeBorderRadius={4}
        maskColor="rgb(var(--cw-bg) / 0.55)"
        className="hidden sm:block"
      />
    </ReactFlow>
  );
}

export function ConceptMapDialog() {
  const open = usePlanStore((s) => s.conceptOpen);
  const requested = usePlanStore((s) => s.conceptCourse);
  const close = usePlanStore((s) => s.closeConceptMap);
  const openConceptMap = usePlanStore((s) => s.openConceptMap);
  const plan = usePlanStore((s) => s.plan);
  const audit = usePlanStore((s) => s.audit);
  const { data: courses = [], isLoading } = useConceptMapCourses();

  const course = useMemo(() => {
    if (requested && courses.includes(requested)) return requested;
    return defaultConceptCourse(courses, plan?.recommendation ?? null, audit);
  }, [requested, courses, plan, audit]);

  useEffect(() => {
    if (open && course && course !== requested) openConceptMap(course);
  }, [open, course, requested, openConceptMap]);

  return (
    <Dialog open={open} onOpenChange={(next) => !next && close()}>
      <DialogContent className="h-[calc(100dvh-2rem)] max-w-6xl">
        <DialogHeader className="flex-row flex-wrap items-center gap-3 space-y-0">
          <div className="mr-auto">
            <DialogTitle>Course concept map</DialogTitle>
            <DialogDescription>
              Scroll to zoom, drag to pan. Dashed outlines indicate inferred concepts.
            </DialogDescription>
          </div>
          <CoursePicker courses={courses} value={course} onChange={(c) => openConceptMap(c)} />
        </DialogHeader>
        <div className="mx-5 mb-5 min-h-0 flex-1 overflow-hidden rounded-zone border bg-bg">
          {isLoading ? (
            <div className="flex h-full items-center justify-center gap-2 text-sm text-muted">
              <Spinner /> Loading courses…
            </div>
          ) : course ? (
            <ReactFlowProvider>
              <ConceptCanvas course={course} />
            </ReactFlowProvider>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted">
              No course concept maps were found.
            </div>
          )}
        </div>
        <div className="-mt-3 mb-4 flex flex-wrap gap-4 px-5 text-xs text-muted">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-4 rounded-sm border-[1.5px] border-green" /> Topic
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-4 rounded-sm border-[1.5px] border-gold" /> Concept
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-4 rounded-sm border-[1.5px] border-dashed border-muted" /> Inferred
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 bg-gold" /> Prerequisite of
          </span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
