import { useRef, useEffect, useCallback } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { LLMRequestSummary } from "../../types";
import { RequestSummaryRow } from "./RequestSummaryRow";

const ROW_HEIGHT = 40;

interface RequestTimelineProps {
  requests: LLMRequestSummary[];
  sessionId: string;
  sessionStartedAt: string;
}

export function RequestTimeline({
  requests,
  sessionId,
  sessionStartedAt,
}: RequestTimelineProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const userScrolledUp = useRef(false);
  const prevCount = useRef(0);
  const initialLoad = useRef(true);

  // Sort by timestamp ascending
  const sorted = [...requests].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );

  // Find the maximum duration for proportional bar rendering
  const maxDurationMs = sorted.reduce(
    (max, r) => Math.max(max, r.duration_ms ?? 0),
    0,
  );

  const virtualizer = useVirtualizer({
    count: sorted.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  });

  // Auto-scroll when new requests arrive (skip the initial data load)
  useEffect(() => {
    if (initialLoad.current) {
      initialLoad.current = false;
      prevCount.current = sorted.length;
      return;
    }
    if (sorted.length > prevCount.current && !userScrolledUp.current) {
      virtualizer.scrollToIndex(sorted.length - 1);
    }
    prevCount.current = sorted.length;
  }, [sorted.length, virtualizer]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    userScrolledUp.current = !atBottom;
  }, []);

  if (sorted.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-500 text-sm">
        No requests recorded yet
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Header */}
      <div className="flex items-center gap-3 px-3 py-2 text-[10px] uppercase tracking-wider text-gray-500 border-b border-gray-700">
        <span className="w-14 text-right">Time</span>
        <span className="w-2" />
        <span className="w-20">Model</span>
        <span className="w-24">Duration</span>
        <span className="w-28">Tokens</span>
        <span className="w-16">Flags</span>
        <span className="flex-1">Preview</span>
      </div>

      {/* Scrollable virtualized rows */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
      >
        <div
          style={{ height: virtualizer.getTotalSize(), position: "relative" }}
        >
          {virtualizer.getVirtualItems().map((virtualRow) => {
            const req = sorted[virtualRow.index]!;
            return (
              <div
                key={req.id}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: virtualRow.size,
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              >
                <RequestSummaryRow
                  request={req}
                  sessionId={sessionId}
                  sessionStartedAt={sessionStartedAt}
                  maxDurationMs={maxDurationMs}
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
