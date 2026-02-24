import { useState, useRef, useEffect, useCallback } from "react";

interface ExportMenuProps {
  sessionId: string;
  sessionName: string;
}

const FORMATS = [
  {
    value: "json" as const,
    label: "JSON",
    description: "Full data dump",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M17 8h2a2 2 0 012 2v6a2 2 0 01-2 2h-2m-2-10H9a2 2 0 00-2 2v6a2 2 0 002 2h6m4-10V6a2 2 0 00-2-2H9a2 2 0 00-2 2v2" />
      </svg>
    ),
  },
  {
    value: "markdown" as const,
    label: "Markdown",
    description: "Conversation log",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    value: "csv" as const,
    label: "CSV",
    description: "Tabular metrics",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
      </svg>
    ),
  },
];

export function ExportMenu({ sessionId, sessionName }: ExportMenuProps) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const handleClickOutside = useCallback(
    (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open, handleClickOutside]);

  const handleExport = (format: string) => {
    const url = `/api/sessions/${sessionId}/export?format=${format}`;
    const a = document.createElement("a");
    a.href = url;
    const safeName = (sessionName || "session").replace(/[^a-zA-Z0-9 _-]/g, "_").trim() || "session";
    const ext = format === "markdown" ? "md" : format;
    a.download = `${safeName}.${ext}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setOpen(false);
  };

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="inline-flex items-center justify-center p-1.5 rounded text-gray-400 hover:text-gray-200 hover:bg-gray-700 transition-colors"
        title="Export session"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
          />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-52 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 py-1">
          {FORMATS.map((fmt) => (
            <button
              key={fmt.value}
              onClick={() => handleExport(fmt.value)}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-gray-700 transition-colors"
            >
              <span className="text-gray-400">{fmt.icon}</span>
              <div className="min-w-0">
                <div className="text-sm text-gray-200">{fmt.label}</div>
                <div className="text-[11px] text-gray-500">{fmt.description}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
