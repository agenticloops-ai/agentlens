import { useState } from "react";
import type { ToolDefinition } from "../../types";
import { Badge } from "../common/Badge";

interface ToolDefinitionPanelProps {
  tools: ToolDefinition[];
}

export function ToolDefinitionPanel({ tools }: ToolDefinitionPanelProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg bg-gray-800 border border-gray-700 overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-gray-750 transition-colors"
      >
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 5l7 7-7 7"
          />
        </svg>
        <span className="text-sm font-medium text-gray-300">
          Tools
        </span>
        <Badge variant="default" size="sm">
          {tools.length}
        </Badge>
      </button>

      {expanded && (
        <div className="border-t border-gray-700 divide-y divide-gray-700">
          {tools.map((tool) => (
            <ToolDefinitionItem key={tool.name} tool={tool} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single tool accordion item
// ---------------------------------------------------------------------------

function ToolDefinitionItem({ tool }: { tool: ToolDefinition }) {
  const [open, setOpen] = useState(false);

  const schema = tool.input_schema;
  const properties =
    schema && typeof schema === "object" && "properties" in schema
      ? (schema.properties as Record<string, Record<string, unknown>>)
      : null;
  const required =
    schema && typeof schema === "object" && "required" in schema
      ? (schema.required as string[])
      : [];

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-gray-750 transition-colors"
      >
        <svg
          className={`w-3 h-3 text-gray-500 transition-transform duration-200 ${open ? "rotate-90" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 5l7 7-7 7"
          />
        </svg>
        <span className="text-xs font-mono text-blue-400">{tool.name}</span>
        {tool.is_mcp && (
          <Badge variant="blue" size="sm">
            MCP{tool.mcp_server_name ? `: ${tool.mcp_server_name}` : ""}
          </Badge>
        )}
      </button>

      {open && (
        <div className="px-4 pb-3 pl-9">
          {tool.description && (
            <p className="text-xs font-mono text-gray-400 mb-3 whitespace-pre-wrap break-words">
              {tool.description}
            </p>
          )}

          {properties && Object.keys(properties).length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-700">
                    <th className="text-left py-1.5 pr-3 font-medium">Parameter</th>
                    <th className="text-left py-1.5 pr-3 font-medium">Type</th>
                    <th className="text-left py-1.5 pr-3 font-medium">Required</th>
                    <th className="text-left py-1.5 font-medium">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(properties).map(([name, prop]) => (
                    <tr key={name} className="border-b border-gray-700/50 last:border-0">
                      <td className="py-1.5 pr-3 text-gray-300">{name}</td>
                      <td className="py-1.5 pr-3 text-gray-500">{String(prop?.["type"] ?? "any")}</td>
                      <td className="py-1.5 pr-3">
                        {required.includes(name) ? (
                          <span className="text-orange-400">yes</span>
                        ) : (
                          <span className="text-gray-600">no</span>
                        )}
                      </td>
                      <td className="py-1.5 text-gray-400">{String(prop?.["description"] ?? "")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {(!properties || Object.keys(properties).length === 0) && (
            <p className="text-xs font-mono text-gray-500 italic">No parameters</p>
          )}
        </div>
      )}
    </div>
  );
}
