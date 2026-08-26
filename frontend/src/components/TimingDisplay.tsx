"use client";

import { PipelineTiming } from "@/lib/types";

interface Props {
  timing: PipelineTiming;
}

const STEPS = [
  { key: "permission_compile_ms", label: "Permission Compile" },
  { key: "bfs_ms", label: "BFS Traversal" },
  { key: "zone2_inject_ms", label: "Zone 2 Inject" },
  { key: "check1_isolation_ms", label: "Check 1: Isolation" },
  { key: "check2_compliance_ms", label: "Check 2: Compliance" },
  { key: "check3_permission_ms", label: "Check 3: Permission" },
  { key: "check4_temporal_ms", label: "Check 4: Temporal" },
  { key: "check5_derivability_ms", label: "Check 5: Derivability" },
] as const;

export default function TimingDisplay({ timing }: Props) {
  const max = Math.max(...STEPS.map((s) => timing[s.key as keyof PipelineTiming] as number), 1);

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
          Pipeline Timing
        </h2>
        <span className="text-lg font-bold text-blue-600">{timing.total_ms} ms total</span>
      </div>
      <div className="space-y-2">
        {STEPS.map(({ key, label }) => {
          const ms = timing[key as keyof PipelineTiming] as number;
          const pct = Math.round((ms / max) * 100);
          return (
            <div key={key} className="flex items-center gap-3">
              <div className="w-44 text-xs text-gray-600 shrink-0">{label}</div>
              <div className="flex-1 bg-gray-100 rounded-full h-4 overflow-hidden">
                <div
                  className="h-4 bg-indigo-400 rounded-full transition-all duration-300"
                  style={{ width: `${Math.max(pct, 2)}%` }}
                />
              </div>
              <div className="w-16 text-right text-xs font-mono text-gray-600">{ms} ms</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
