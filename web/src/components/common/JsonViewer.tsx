import { useState, useCallback } from "react";

interface JsonViewerProps {
  data: unknown;
  defaultExpandDepth?: number;
}

export function JsonViewer({ data, defaultExpandDepth = 2 }: JsonViewerProps) {
  return (
    <div className="font-mono text-sm leading-relaxed">
      <JsonNode value={data} depth={0} defaultExpandDepth={defaultExpandDepth} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal recursive node
// ---------------------------------------------------------------------------

interface JsonNodeProps {
  value: unknown;
  depth: number;
  defaultExpandDepth: number;
  keyName?: string;
  isLast?: boolean;
}

function JsonNode({
  value,
  depth,
  defaultExpandDepth,
  keyName,
  isLast = true,
}: JsonNodeProps) {
  const isExpandable =
    value !== null && typeof value === "object" && value !== undefined;
  const [expanded, setExpanded] = useState(depth < defaultExpandDepth);

  const toggle = useCallback(() => setExpanded((v) => !v), []);

  const indent = depth * 16;
  const comma = isLast ? "" : ",";

  // Key prefix (for object properties)
  const keyPrefix = keyName !== undefined && (
    <span className="text-gray-400">
      &quot;<span className="text-gray-300">{keyName}</span>&quot;
      <span className="text-gray-500">: </span>
    </span>
  );

  // ---------- Primitive values ----------

  if (!isExpandable) {
    return (
      <div style={{ paddingLeft: indent }}>
        {keyPrefix}
        <PrimitiveValue value={value} />
        <span className="text-gray-500">{comma}</span>
      </div>
    );
  }

  // ---------- Array / Object ----------

  const isArray = Array.isArray(value);
  const entries = isArray
    ? (value as unknown[]).map((v, i) => [String(i), v] as const)
    : Object.entries(value as Record<string, unknown>);

  const openBrace = isArray ? "[" : "{";
  const closeBrace = isArray ? "]" : "}";

  if (entries.length === 0) {
    return (
      <div style={{ paddingLeft: indent }}>
        {keyPrefix}
        <span className="text-gray-500">
          {openBrace}
          {closeBrace}
        </span>
        <span className="text-gray-500">{comma}</span>
      </div>
    );
  }

  if (!expanded) {
    return (
      <div style={{ paddingLeft: indent }}>
        <button
          onClick={toggle}
          className="text-gray-500 hover:text-gray-300 transition-colors mr-1"
        >
          <ChevronRight />
        </button>
        {keyPrefix}
        <span className="text-gray-500">
          {openBrace}
          <span className="text-gray-600 mx-1">
            {entries.length} {entries.length === 1 ? "item" : "items"}
          </span>
          {closeBrace}
        </span>
        <span className="text-gray-500">{comma}</span>
      </div>
    );
  }

  return (
    <div>
      <div style={{ paddingLeft: indent }}>
        <button
          onClick={toggle}
          className="text-gray-500 hover:text-gray-300 transition-colors mr-1"
        >
          <ChevronDown />
        </button>
        {keyPrefix}
        <span className="text-gray-500">{openBrace}</span>
      </div>

      {entries.map(([k, v], idx) => (
        <JsonNode
          key={k}
          keyName={isArray ? undefined : k}
          value={v}
          depth={depth + 1}
          defaultExpandDepth={defaultExpandDepth}
          isLast={idx === entries.length - 1}
        />
      ))}

      <div style={{ paddingLeft: indent }}>
        <span className="text-gray-500">{closeBrace}</span>
        <span className="text-gray-500">{comma}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Primitive value renderer
// ---------------------------------------------------------------------------

function PrimitiveValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-gray-500 italic">null</span>;
  }
  if (typeof value === "boolean") {
    return (
      <span className="text-orange-400">{value ? "true" : "false"}</span>
    );
  }
  if (typeof value === "number") {
    return <span className="text-blue-400">{String(value)}</span>;
  }
  if (typeof value === "string") {
    return (
      <span className="text-green-400 whitespace-pre-wrap break-words">
        &quot;{value}&quot;
      </span>
    );
  }
  return <span className="text-gray-400">{String(value)}</span>;
}

// ---------------------------------------------------------------------------
// Chevron icons
// ---------------------------------------------------------------------------

function ChevronRight() {
  return (
    <svg
      className="w-3 h-3 inline-block"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}

function ChevronDown() {
  return (
    <svg
      className="w-3 h-3 inline-block"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
  );
}
