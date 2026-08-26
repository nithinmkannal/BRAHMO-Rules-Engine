"use client";

import { PipelineFunnel } from "@/lib/types";

interface Props {
  funnel: PipelineFunnel;
  userName: string;
}

const STAGES: {
  key: keyof PipelineFunnel;
  label: string;
  checkLabel?: string;
  color: string;
}[] = [
  {
    key: "after_bfs",
    label: "BFS + Zone 2",
    checkLabel: "after BFS+Zone2",
    color: "bg-gray-500",
  },
  {
    key: "after_check1",
    label: "ISOLATION",
    checkLabel: "after ISOLATION",
    color: "bg-blue-500",
  },
  {
    key: "after_check2",
    label: "COMPLIANCE",
    checkLabel: "after COMPLIANCE",
    color: "bg-blue-500",
  },
  {
    key: "after_check3",
    label: "PERMISSION",
    checkLabel: "after PERMISSION",
    color: "bg-blue-500",
  },
  {
    key: "after_check4",
    label: "TEMPORAL",
    checkLabel: "after TEMPORAL",
    color: "bg-blue-500",
  },
  {
    key: "after_check5",
    label: "DERIVABILITY",
    checkLabel: "after DERIVABILITY",
    color: "bg-green-600",
  },
];

export default function FilterFunnel({ funnel, userName }: Props) {
  // Use after_zone2 as the reference "100%" width (widest filtered bar)
  const maxCount = funnel.after_zone2 || funnel.total_nodes || 1;

  // The combined after-BFS+Zone2 count is after_zone2
  const rows = [
    {
      count: funnel.after_zone2,
      label: "BFS + Zone 2",
      checkLabel: "after BFS+Zone2",
      color: "bg-gray-600",
    },
    {
      count: funnel.after_check1,
      label: "ISOLATION",
      checkLabel: "after ISOLATION",
      color: "bg-blue-500",
    },
    {
      count: funnel.after_check2,
      label: "COMPLIANCE",
      checkLabel: "after COMPLIANCE",
      color: "bg-blue-500",
    },
    {
      count: funnel.after_check3,
      label: "PERMISSION",
      checkLabel: "after PERMISSION",
      color: "bg-blue-500",
    },
    {
      count: funnel.after_check4,
      label: "TEMPORAL",
      checkLabel: "after TEMPORAL",
      color: "bg-blue-500",
    },
    {
      count: funnel.after_check5,
      label: "DERIVABILITY",
      checkLabel: "after DERIVABILITY",
      color: "bg-green-600",
    },
  ];

  return (
    <div className="bg-white border border-gray-300 rounded p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-semibold text-gray-700 uppercase tracking-widest">
          FILTER FUNNEL
        </h2>
        <span className="text-xs text-gray-400 font-sans">{userName}</span>
      </div>

      <div className="space-y-2">
        {rows.map((row) => {
          const pct = Math.round((row.count / maxCount) * 100);
          const isFinal = row.label === "DERIVABILITY";
          return (
            <div key={row.label} className="flex items-center gap-2">
              {/* Bar */}
              <div className="flex-1 bg-gray-100 h-6 rounded-sm overflow-hidden relative">
                <div
                  className={`h-6 rounded-sm transition-all duration-500 ${row.color}`}
                  style={{ width: `${Math.max(pct, 1)}%` }}
                />
              </div>
              {/* Count + label */}
              <div className="text-right min-w-[200px] flex items-center justify-end gap-2">
                <span
                  className={`text-sm font-bold tabular-nums ${
                    isFinal ? "text-green-700" : "text-gray-800"
                  }`}
                >
                  {row.count}
                </span>
                <span className="text-xs text-gray-500 font-sans">
                  {row.checkLabel}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary */}
      <div className="mt-4 pt-3 border-t border-gray-200 flex items-center justify-between text-xs font-sans text-gray-500">
        <span>
          {funnel.total_nodes} total →{" "}
          <span className="text-red-600 font-medium">
            −{funnel.total_nodes - funnel.after_check5} filtered
          </span>
        </span>
        <span className="font-semibold text-green-700">
          {funnel.after_check5} final candidates
        </span>
      </div>
    </div>
  );
}
