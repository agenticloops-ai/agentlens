import { CopyButton } from "./CopyButton";

interface CodeBlockProps {
  code: string;
  language?: string;
}

export function CodeBlock({ code, language }: CodeBlockProps) {
  return (
    <div className="relative group rounded-lg bg-gray-900 border border-gray-700">
      {/* Header bar with language label and copy button */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-gray-700">
        {language ? (
          <span className="text-[10px] font-medium uppercase tracking-wider text-gray-500">
            {language}
          </span>
        ) : (
          <span />
        )}
        <CopyButton text={code} />
      </div>

      {/* Code area */}
      <div className="overflow-x-auto max-h-96 overflow-y-auto">
        <pre className="p-3 text-sm leading-relaxed">
          <code className="font-mono text-gray-300 whitespace-pre">{code}</code>
        </pre>
      </div>
    </div>
  );
}
