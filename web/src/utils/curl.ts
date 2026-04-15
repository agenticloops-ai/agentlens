import type { RawCapture } from "../types";

const SKIP_HEADERS = new Set(["host", "content-length"]);

export function generateCurl(raw: RawCapture): string {
  const parts: string[] = ["curl"];

  if (raw.request_method !== "GET") {
    parts.push(`-X ${raw.request_method}`);
  }

  parts.push(`'${raw.request_url}'`);

  for (const [key, value] of Object.entries(raw.request_headers)) {
    if (SKIP_HEADERS.has(key.toLowerCase())) continue;
    parts.push(`-H '${key}: ${value}'`);
  }

  if (raw.request_body && raw.request_method !== "GET") {
    const bodyStr =
      typeof raw.request_body === "string"
        ? raw.request_body
        : JSON.stringify(raw.request_body);
    if (bodyStr) {
      parts.push(`-d '${bodyStr.replace(/'/g, "'\\''")}'`);
    }
  }

  return parts.join(" \\\n  ");
}
