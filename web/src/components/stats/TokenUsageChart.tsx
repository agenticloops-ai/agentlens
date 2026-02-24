import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { LLMRequestSummary } from "../../types";

interface TokenUsageChartProps {
  requests: LLMRequestSummary[];
}

interface ChartDataPoint {
  index: number;
  label: string;
  input_tokens: number;
  output_tokens: number;
}

export function TokenUsageChart({ requests }: TokenUsageChartProps) {
  const sorted = [...requests].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );

  const data: ChartDataPoint[] = sorted.map((req, i) => ({
    index: i + 1,
    label: `#${i + 1}`,
    input_tokens: req.usage.input_tokens,
    output_tokens: req.usage.output_tokens,
  }));

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-24 text-gray-500 text-xs">
        No data
      </div>
    );
  }

  return (
    <div className="h-32">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="label"
            tick={{ fill: "#6b7280", fontSize: 10 }}
            axisLine={{ stroke: "#374151" }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#6b7280", fontSize: 10 }}
            axisLine={{ stroke: "#374151" }}
            tickLine={false}
            tickFormatter={(v: number) =>
              v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)
            }
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1f2937",
              border: "1px solid #374151",
              borderRadius: "6px",
              fontSize: "12px",
            }}
            labelStyle={{ color: "#9ca3af" }}
            itemStyle={{ padding: 0 }}
            formatter={(value: string | number, name: string) => [
              Number(value).toLocaleString(),
              name === "input_tokens" ? "Input" : "Output",
            ]}
          />
          <Area
            type="monotone"
            dataKey="input_tokens"
            stackId="1"
            stroke="#3b82f6"
            fill="#3b82f6"
            fillOpacity={0.3}
          />
          <Area
            type="monotone"
            dataKey="output_tokens"
            stackId="1"
            stroke="#a855f7"
            fill="#a855f7"
            fillOpacity={0.3}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
