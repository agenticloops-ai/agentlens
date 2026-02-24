import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { LLMRequestSummary } from "../../types";
import { useProviderMeta } from "../../hooks/useProviderMeta";

interface LatencyChartProps {
  requests: LLMRequestSummary[];
}

interface ChartDataPoint {
  index: number;
  label: string;
  duration_ms: number;
  provider: string;
}

export function LatencyChart({ requests }: LatencyChartProps) {
  const getProvider = useProviderMeta();

  const sorted = [...requests].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );

  const data: ChartDataPoint[] = sorted
    .filter((r) => r.duration_ms != null)
    .map((req, i) => ({
      index: i + 1,
      label: `#${i + 1}`,
      duration_ms: req.duration_ms ?? 0,
      provider: req.provider,
    }));

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-24 text-gray-500 text-xs">
        No latency data
      </div>
    );
  }

  return (
    <div className="h-32">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
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
              v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${v}ms`
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
            formatter={(value: string | number) => {
              const v = Number(value);
              return [
                v >= 1000
                  ? `${(v / 1000).toFixed(2)}s`
                  : `${Math.round(v)}ms`,
                "Duration",
              ];
            }}
          />
          <Bar dataKey="duration_ms" radius={[2, 2, 0, 0]}>
            {data.map((entry, i) => (
              <Cell key={i} fill={getProvider(entry.provider).color} fillOpacity={0.7} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
