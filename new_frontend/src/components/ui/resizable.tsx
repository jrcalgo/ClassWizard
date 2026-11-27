import { GripHorizontal } from "lucide-react";
import * as ResizablePrimitive from "react-resizable-panels";

import { cn } from "@/lib/utils";

export const ResizablePanelGroup = ({
  className,
  ...props
}: React.ComponentProps<typeof ResizablePrimitive.PanelGroup>) => (
  <ResizablePrimitive.PanelGroup className={cn("flex h-full w-full", className)} {...props} />
);

export const ResizablePanel = ResizablePrimitive.Panel;

export const ResizableHandle = ({
  className,
  ...props
}: React.ComponentProps<typeof ResizablePrimitive.PanelResizeHandle>) => (
  <ResizablePrimitive.PanelResizeHandle
    className={cn(
      "group relative flex h-2 w-full shrink-0 items-center justify-center bg-transparent outline-none transition-colors hover:bg-green/10 focus-visible:bg-green/20 data-[resize-handle-state=drag]:bg-green/20",
      className,
    )}
    {...props}
  >
    <div className="z-10 flex h-3 w-8 items-center justify-center rounded-sm border bg-card text-muted group-hover:text-text">
      <GripHorizontal className="h-3 w-3" />
    </div>
  </ResizablePrimitive.PanelResizeHandle>
);
