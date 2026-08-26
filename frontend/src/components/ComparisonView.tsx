"use client";

import { PipelineResult } from "@/lib/types";
import FilterFunnel from "./FilterFunnel";
import CandidateSet from "./CandidateSet";

interface Props {
  results: PipelineResult[];
}

const ROLE_COLORS: Record<string, string> = {
  ADMIN: "bg-red-100 text-red-800 border-red-200",
  HOD: "bg-purple-100 text-purple-800 border-purple-200",
  EDITOR: "bg-blue-100 text-blue-800 border-blue-200",
  VIEWER: "bg-green-100 text-green-800 border-green-200",
  QUALITY: "bg-yellow-100 text-yellow-800 border-yellow-200",
  AUDITOR: "bg-orange-100 text-orange-800 border-orange-200",
};

export default function ComparisonView({ results }: Props) {
  if (results.length === 0) return null;

  if (results.length === 1) {
    const r = results[0];
    return (
      <div className="space-y-5">
        <FilterFunnel funnel={r.funnel} userName={r.user_name} />
        <CandidateSet nodes={r.candidate_set} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Side-by-side summary cards (spec style) ── */}
      <div
        className={`grid gap-4 ${
          results.length === 2 ? "grid-cols-2" : "grid-cols-3"
        }`}
      >
        {results.map((r) => (
          <UserComparisonCard key={r.user} result={r} allResults={results} />
        ))}
      </div>

      {/* ── Funnel comparison ── */}
      <div>
        <h2 className="text-xs font-semibold text-gray-600 uppercase tracking-widest mb-3">
          Filter Funnel Comparison
        </h2>
        <div
          className={`grid gap-4 ${
            results.length === 2 ? "grid-cols-2" : "grid-cols-3"
          }`}
        >
          {results.map((r) => (
            <FilterFunnel key={r.user} funnel={r.funnel} userName={r.user_name} />
          ))}
        </div>
      </div>

      {/* ── Numeric comparison table ── */}
      <div className="bg-white border border-gray-300 rounded overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200">
          <h2 className="text-xs font-semibold text-gray-700 uppercase tracking-widest">
            Stage-by-Stage Numbers
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide border-b border-gray-200">
                  Stage
                </th>
                {results.map((r) => (
                  <th
                    key={r.user}
                    className="px-4 py-2 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide border-b border-gray-200"
                  >
                    <div className="font-sans">{r.user_name}</div>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded border font-medium font-sans ${
                        ROLE_COLORS[r.role] ?? "bg-gray-100 text-gray-700 border-gray-200"
                      }`}
                    >
                      {r.role} · L{r.ceiling_level}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 font-mono">
              {(
                [
                  ["Total Graph", "total_nodes"],
                  ["After BFS", "after_bfs"],
                  ["+ Zone 2", "after_zone2"],
                  ["Check 1: Isolation", "after_check1"],
                  ["Check 2: Compliance", "after_check2"],
                  ["Check 3: Permission", "after_check3"],
                  ["Check 4: Temporal", "after_check4"],
                  ["Check 5: Derivability", "after_check5"],
                ] as [string, string][]
              ).map(([label, key]) => (
                <tr
                  key={key}
                  className={
                    key === "after_check5"
                      ? "bg-green-50 font-bold"
                      : "hover:bg-gray-50"
                  }
                >
                  <td className="px-4 py-2 text-xs text-gray-600 font-sans">
                    {label}
                  </td>
                  {results.map((r) => (
                    <td
                      key={r.user}
                      className={`px-4 py-2 text-right tabular-nums text-sm ${
                        key === "after_check5"
                          ? "text-green-700"
                          : "text-gray-800"
                      }`}
                    >
                      {r.funnel[key as keyof typeof r.funnel]}
                    </td>
                  ))}
                </tr>
              ))}
              <tr className="bg-blue-50">
                <td className="px-4 py-2 text-xs text-gray-600 font-sans">
                  Pipeline Time
                </td>
                {results.map((r) => (
                  <td
                    key={r.user}
                    className="px-4 py-2 text-right tabular-nums text-sm text-blue-700 font-bold"
                  >
                    {r.pipeline_timing.total_ms} ms
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Individual candidate sets ── */}
      {results.map((r) => (
        <div key={r.user}>
          <h3 className="text-xs font-semibold text-gray-600 uppercase tracking-widest mb-3 font-mono">
            {r.user_name} — Candidate Set ({r.candidate_set.length} nodes)
          </h3>
          <CandidateSet nodes={r.candidate_set} />
        </div>
      ))}
    </div>
  );
}

/* ─── Single user comparison card (matches the spec box) ─────────────── */
function UserComparisonCard({
  result,
  allResults,
}: {
  result: PipelineResult;
  allResults: PipelineResult[];
}) {
  // Collect all departments that appear in ANY result's candidate set (for silent exclusion check)
  const allDepts = new Set(
    allResults.flatMap((r) =>
      r.candidate_set.map((n) => n.department).filter(Boolean)
    )
  );
  const myDepts = new Set(
    result.candidate_set.map((n) => n.department).filter(Boolean)
  );

  // Determine which other users see MORE (for check markers)
  const otherMaxCeiling = Math.min(
    ...allResults
      .filter((r) => r.user !== result.user)
      .map((r) => r.ceiling_level)
  );

  const canSeeHOD = result.ceiling_level <= 4;
  const hasMNPI = result.candidate_set.some(
    (n) =>
      n.title.toLowerCase().includes("mnpi") ||
      n.content.toLowerCase().includes("mnpi")
  );

  return (
    <div className="bg-white border-2 border-gray-300 rounded font-mono text-xs">
      {/* Header */}
      <div className="px-3 py-2 border-b border-gray-200 bg-gray-50">
        <div className="font-bold text-gray-900 font-sans text-sm">
          {result.user_name}
        </div>
        <div className="text-gray-500 font-sans">
          {result.role}, L{result.ceiling_level} · {result.entry_point}
        </div>
      </div>

      {/* Counts */}
      <div className="px-3 py-2 space-y-1 border-b border-gray-200">
        <div className="flex justify-between">
          <span className="text-gray-500">BFS reach:</span>
          <span className="font-bold text-gray-900">{result.funnel.after_bfs}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">+Zone 2:</span>
          <span className="font-bold text-gray-900">{result.funnel.after_zone2}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">After 5ck:</span>
          <span className="font-bold text-green-700">{result.funnel.after_check5}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Time:</span>
          <span className="font-bold text-blue-700">
            {result.pipeline_timing.total_ms} ms
          </span>
        </div>
      </div>

      {/* Access markers */}
      <div className="px-3 py-2 space-y-1 font-sans">
        <AccessRow
          allowed={canSeeHOD}
          label={`L4 HOD nodes`}
        />
        <AccessRow
          allowed={result.ceiling_level <= 4}
          label="Admin nodes"
        />
        {Array.from(allDepts)
          .filter((d) => d)
          .slice(0, 4)
          .map((dept) => (
            <AccessRow
              key={dept}
              allowed={myDepts.has(dept)}
              label={`${dept} nodes`}
            />
          ))}
        <AccessRow allowed={true} label="Drug safety (Zone 2)" />
      </div>
    </div>
  );
}

function AccessRow({ allowed, label }: { allowed: boolean; label: string }) {
  return (
    <div className="flex items-center gap-1.5 text-[11px]">
      <span className={allowed ? "text-green-600 font-bold" : "text-red-500 font-bold"}>
        {allowed ? "✓" : "✗"}
      </span>
      <span className={allowed ? "text-gray-700" : "text-gray-400 line-through"}>
        {label}
      </span>
    </div>
  );
}
