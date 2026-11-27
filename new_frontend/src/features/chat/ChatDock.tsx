import { ChevronDown, ChevronUp, MessageSquareText, SendHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import type { ChatMessage } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import { usePlanStore } from "@/state/planStore";

import { MAX_QUESTION, useSendMessage } from "./useSendMessage";

function Sources({ sources }: { sources: NonNullable<ChatMessage["sources"]> }) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mt-2">
      <CollapsibleTrigger className="flex items-center gap-1 text-xs font-semibold text-link hover:underline">
        {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        Sources ({sources.length})
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="mt-1.5 space-y-1.5 border-l-2 border-green/40 pl-3 text-xs">
          {sources.map((source) => (
            <li key={source.id}>
              {source.kind === "skill_match" && source.label && <strong className="block">{source.label}</strong>}
              <strong>[{source.id}]</strong> {source.text}
            </li>
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}

function Bubble({ message }: { message: ChatMessage }) {
  const mine = message.role === "user";
  return (
    <div className={cn("flex", mine ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[min(48rem,90%)] rounded-card px-3.5 py-2.5 text-sm",
          mine ? "bg-selection text-on-selection" : "border bg-card-alt",
        )}
      >
        <div className="cw-markdown">
          <ReactMarkdown>{message.content}</ReactMarkdown>
        </div>
        {!mine && message.sources && message.sources.length > 0 && <Sources sources={message.sources} />}
      </div>
    </div>
  );
}

interface ChatDockProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onMaximize: () => void;
}

export function ChatDock({ collapsed, onToggleCollapsed, onMaximize }: ChatDockProps) {
  const messages = usePlanStore((s) => s.messages);
  const replying = usePlanStore((s) => s.replying);
  const send = useSendMessage();
  const [draft, setDraft] = useState("");
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, replying, collapsed]);

  const submit = () => {
    const text = draft.trim();
    if (!text || replying) return;
    setDraft("");
    void send(text);
  };

  return (
    <section aria-label="Plan assistant" className="flex h-full flex-col border-t bg-card">
      <header className="flex h-10 shrink-0 items-center gap-2 px-3">
        <MessageSquareText className="h-4 w-4 text-green" />
        <h2 className="text-sm font-bold">Plan assistant</h2>
        {replying && collapsed && <Spinner className="text-muted" />}
        <div className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onMaximize} aria-label="Expand chat" title="Expand chat">
            <ChevronUp />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={onToggleCollapsed}
            aria-label={collapsed ? "Show chat" : "Minimize chat"}
            title={collapsed ? "Show chat" : "Minimize chat"}
          >
            {collapsed ? <ChevronUp /> : <ChevronDown />}
          </Button>
        </div>
      </header>
      {!collapsed && (
        <>
          <div ref={scroller} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 pb-3" aria-live="polite">
            {messages.map((message, i) => (
              <Bubble key={i} message={message} />
            ))}
            {replying && (
              <div className="flex items-center gap-2 text-sm text-muted">
                <Spinner /> Finding the evidence and writing an answer…
              </div>
            )}
          </div>
          <form
            className="flex shrink-0 items-end gap-2 border-t p-2.5"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value.slice(0, MAX_QUESTION))}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
              rows={1}
              placeholder="Ask about this plan"
              aria-label="Ask about this plan"
              className="max-h-28 min-h-10 flex-1 resize-none rounded-btn border bg-bg px-3 py-2 text-sm outline-none placeholder:text-muted/70 focus-visible:ring-2 focus-visible:ring-green"
            />
            <Button type="submit" size="icon" className="h-10 w-10" disabled={!draft.trim() || replying} aria-label="Send">
              <SendHorizontal />
            </Button>
          </form>
        </>
      )}
    </section>
  );
}
