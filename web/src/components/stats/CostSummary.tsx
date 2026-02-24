import type { SessionStats } from "../../types";
import type { LLMRequestSummary } from "../../types";

interface CostSummaryProps {
  stats: SessionStats;
  requests: LLMRequestSummary[];
}

interface ModelCost {
  model: string;
  cost: number;
  count: number;
}

export function CostSummary({ stats, requests }: CostSummaryProps) {
  // Compute cost breakdown by model
  const costByModel = new Map<string, ModelCost>();
  for (const req of requests) {
    const existing = costByModel.get(req.model);
    const reqCost = req.usage.estimated_cost_usd ?? 0;
    if (existing) {
      existing.cost += reqCost;
      existing.count += 1;
    } else {
      costByModel.set(req.model, { model: req.model, cost: reqCost, count: 1 });
    }
  }
  const modelBreakdown = Array.from(costByModel.values()).sort(
    (a, b) => b.cost - a.cost,
  );

  const avgCost =
    stats.total_requests > 0
      ? stats.estimated_cost_usd / stats.total_requests
      : 0;

  return (
    <div className="space-y-2">
      {/* Total + avg on one line */}
      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-500">Total</div>
          <div className="text-lg font-bold text-gray-100">
            ${stats.estimated_cost_usd.toFixed(2)}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wider text-gray-500">Avg / Req</div>
          <div className="text-sm font-medium text-gray-300">
            ${avgCost.toFixed(4)}
          </div>
        </div>
      </div>

      {/* Model breakdown */}
      {modelBreakdown.length > 1 && (
        <div className="pt-2 border-t border-gray-700">
          <div className="space-y-1">
            {modelBreakdown.map((m) => (
              <div key={m.model} className="flex items-center justify-between text-xs">
                <span className="text-gray-400 truncate mr-2">{m.model}</span>
                <span className="text-gray-300 font-mono shrink-0">
                  ${m.cost.toFixed(3)}
                  <span className="text-gray-600 ml-1">({m.count})</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
