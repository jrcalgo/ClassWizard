import { Map as MapIcon, PanelRightOpen } from "lucide-react";
import { useRef, useState } from "react";
import type { ImperativePanelHandle } from "react-resizable-panels";

import { Button } from "@/components/ui/button";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { ChatDock } from "@/features/chat/ChatDock";
import { ConceptMapDialog } from "@/features/graph/ConceptMapDialog";
import { SkillGraph } from "@/features/graph/SkillGraph";
import { ResultsPanel } from "@/features/results/ResultsPanel";
import { cn } from "@/lib/utils";
import { usePlanStore } from "@/state/planStore";

const CHAT_DEFAULT = 32;
const CHAT_MAX = 85;

/** Empty until the first Search; then the skill graph with the chat dock under it. */
export function Canvas() {
  const plan = usePlanStore((s) => s.plan);
  const resultsOpen = usePlanStore((s) => s.resultsOpen);
  const setResultsOpen = usePlanStore((s) => s.setResultsOpen);
  const openConceptMap = usePlanStore((s) => s.openConceptMap);
  const chatPanel = useRef<ImperativePanelHandle>(null);
  const [chatCollapsed, setChatCollapsed] = useState(false);

  if (!plan) return <main className="h-full min-w-0 flex-1" aria-label="Canvas" />;

  return (
    <main className="relative flex h-full min-w-0 flex-1" aria-label="Canvas">
      <div className="h-full min-w-0 flex-1">
        <ResizablePanelGroup direction="vertical" autoSaveId="cw-canvas-split">
          <ResizablePanel id="graph" order={1} minSize={10} defaultSize={100 - CHAT_DEFAULT}>
            <div className="relative h-full">
              <SkillGraph
                actions={
                  <>
                    <Button variant="outline" size="sm" className="shadow-sm" onClick={() => openConceptMap(null)}>
                      <MapIcon /> Concept maps
                    </Button>
                    {!resultsOpen && (
                      <Button variant="outline" size="sm" className="shadow-sm" onClick={() => setResultsOpen(true)}>
                        <PanelRightOpen /> Results
                      </Button>
                    )}
                  </>
                }
              />
            </div>
          </ResizablePanel>
          <ResizableHandle />
          <ResizablePanel
            id="chat"
            order={2}
            ref={chatPanel}
            defaultSize={CHAT_DEFAULT}
            minSize={18}
            maxSize={CHAT_MAX}
            collapsible
            collapsedSize={6}
            onCollapse={() => setChatCollapsed(true)}
            onExpand={() => setChatCollapsed(false)}
            className="min-h-10"
          >
            <ChatDock
              collapsed={chatCollapsed}
              onToggleCollapsed={() => {
                const panel = chatPanel.current;
                if (!panel) return;
                if (panel.isCollapsed()) panel.expand(CHAT_DEFAULT);
                else panel.collapse();
              }}
              onMaximize={() => {
                const panel = chatPanel.current;
                if (!panel) return;
                if (panel.isCollapsed()) panel.expand(CHAT_DEFAULT);
                panel.resize(panel.getSize() >= CHAT_MAX - 1 ? CHAT_DEFAULT : CHAT_MAX);
              }}
            />
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
      <div
        className={cn(
          "h-full shrink-0",
          resultsOpen ? "absolute inset-y-0 right-0 z-20 w-full max-w-[400px] shadow-xl lg:static lg:shadow-none" : "hidden",
        )}
      >
        <ResultsPanel />
      </div>
      <ConceptMapDialog />
    </main>
  );
}
