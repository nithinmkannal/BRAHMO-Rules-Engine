"use client";

import { useEffect, useState } from "react";
import { User, PipelineResult } from "@/lib/types";
import FilterFunnel from "@/components/FilterFunnel";
import DAGViewer from "@/components/DAGViewer";
import CandidateSet from "@/components/CandidateSet";
import ComparisonView from "@/components/ComparisonView";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function HomePage() {
  const [users, setUsers] = useState<User[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [results, setResults] = useState<PipelineResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"single" | "compare">("single");

  useEffect(() => {
    fetch(`${API_BASE}/users`)
      .then((r) => r.json())
      .then(setUsers)
      .catch(() =>
        setError("Could not reach backend. Is FastAPI running on port 8000?")
      );
  }, []);

  function selectUser(id: string) {
    if (viewMode === "single") {
      setSelectedIds([id]);
    } else {
      setSelectedIds((prev) => {
        if (prev.includes(id)) return prev.filter((x) => x !== id);
        if (prev.length >= 3) return prev;
        return [...prev, id];
      });
    }
  }

  async function runPipeline() {
    if (selectedIds.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      if (selectedIds.length === 1) {
        const res = await fetch(`${API_BASE}/pipeline/${selectedIds[0]}`, {
          method: "POST",
        });
        const data = await res.json();
        setResults([data]);
      } else {
        const res = await fetch(`${API_BASE}/pipeline/compare`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_ids: selectedIds }),
        });
        const data = await res.json();
        setResults(data);
      }
    } catch {
      setError("Pipeline request failed. Check backend connection.");
    } finally {
      setLoading(false);
    }
  }

  const primaryResult = results[0] ?? null;
  const selectedUser = users.find((u) => u.id === selectedIds[0]);

  return (
    <main className="min-h-screen bg-gray-50 font-mono">
      {/* ── Header ── */}
      <div className="bg-white border-b border-gray-300">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <div>
            <h1 className="text-base font-bold text-gray-900 tracking-tight">
              BRAHMO Rules Engine — BFS + 5-Check Filter Pipeline
            </h1>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs bg-green-100 text-green-800 px-2 py-0.5 rounded border border-green-300 font-medium">
                Zero LLM
              </span>
              <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded border border-blue-300 font-medium">
                Deterministic
              </span>
              <span className="text-xs bg-red-100 text-red-800 px-2 py-0.5 rounded border border-red-300 font-medium">
                Silent Exclusion
              </span>
            </div>
          </div>
          {primaryResult && (
            <div className="text-right">
              <div className="text-3xl font-bold text-gray-900">
                {primaryResult.funnel.after_check5}
              </div>
              <div className="text-xs text-gray-500">final candidates</div>
              <div className="text-xs text-gray-400 mt-0.5">
                {primaryResult.pipeline_timing.total_ms} ms · Zero LLM ·
                Deterministic
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-5 space-y-5">
        {/* ── Error ── */}
        {error && (
          <div className="bg-red-50 border border-red-300 rounded px-4 py-3 text-sm text-red-700 font-sans">
            {error}
          </div>
        )}

        {/* ── Control Bar ── */}
        <div className="bg-white border border-gray-300 rounded p-4">
          {/* Mode toggle */}
          <div className="flex items-center gap-3 mb-4">
            <span className="text-xs text-gray-500 font-sans">Mode:</span>
            <button
              onClick={() => {
                setViewMode("single");
                setSelectedIds([]);
                setResults([]);
              }}
              className={`text-xs px-3 py-1 rounded border transition-colors font-sans ${
                viewMode === "single"
                  ? "bg-gray-900 text-white border-gray-900"
                  : "bg-white text-gray-600 border-gray-300 hover:border-gray-500"
              }`}
            >
              Single User
            </button>
            <button
              onClick={() => {
                setViewMode("compare");
                setSelectedIds([]);
                setResults([]);
              }}
              className={`text-xs px-3 py-1 rounded border transition-colors font-sans ${
                viewMode === "compare"
                  ? "bg-gray-900 text-white border-gray-900"
                  : "bg-white text-gray-600 border-gray-300 hover:border-gray-500"
              }`}
            >
              Compare (up to 3)
            </button>
          </div>

          <div className="flex flex-wrap items-end gap-4">
            {/* User dropdown (single mode) */}
            {viewMode === "single" && (
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-sans">
                  User
                </label>
                <select
                  value={selectedIds[0] ?? ""}
                  onChange={(e) => selectUser(e.target.value)}
                  className="text-sm border border-gray-300 rounded px-3 py-1.5 bg-white text-gray-900 font-sans focus:outline-none focus:border-gray-500"
                >
                  <option value="">▼ Select a user…</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name} — {u.role}, L{u.ceiling_level}, {u.department}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Multi-select cards (compare mode) */}
            {viewMode === "compare" && (
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-sans">
                  Select up to 3 users
                </label>
                <div className="flex flex-wrap gap-2">
                  {users.map((u) => {
                    const sel = selectedIds.includes(u.id);
                    return (
                      <button
                        key={u.id}
                        onClick={() => selectUser(u.id)}
                        className={`text-xs px-2 py-1 rounded border transition-colors font-sans ${
                          sel
                            ? "bg-gray-900 text-white border-gray-900"
                            : "bg-white text-gray-700 border-gray-300 hover:border-gray-500"
                        }`}
                      >
                        {u.name} ({u.role}, L{u.ceiling_level})
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Entry point display */}
            {selectedUser && viewMode === "single" && (
              <div className="text-xs text-gray-500 font-sans">
                <span className="text-gray-400">Entry Point:</span>{" "}
                <span className="font-medium text-gray-700">
                  {selectedUser.department} (Level {selectedUser.ceiling_level})
                </span>
              </div>
            )}

            {/* Run button */}
            <button
              onClick={runPipeline}
              disabled={selectedIds.length === 0 || loading}
              className="px-5 py-2 bg-gray-900 text-white text-sm font-sans rounded hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Running…" : "▶  Run Pipeline"}
            </button>
          </div>
        </div>

        {/* ── Pipeline Results ── */}
        {results.length > 0 && (
          <>
            {results.length === 1 && primaryResult ? (
              <SingleView result={primaryResult} />
            ) : (
              <ComparisonView results={results} />
            )}
          </>
        )}

        {/* ── Empty state ── */}
        {results.length === 0 && !loading && (
          <div className="text-center py-20 text-gray-400 font-sans">
            <p className="text-base font-medium text-gray-500">
              Select a user and run the pipeline
            </p>
            <p className="text-sm mt-1">
              Choose up to 3 users to compare results side-by-side
            </p>
          </div>
        )}
      </div>
    </main>
  );
}

/* ─── Single-User Full View ─────────────────────────────────────────────── */
function SingleView({ result }: { result: PipelineResult }) {
  return (
    <div className="space-y-5">
      {/* Flow Summary Boxes */}
      <FlowSummary result={result} />

      {/* Filter Funnel */}
      <FilterFunnel funnel={result.funnel} userName={result.user_name} />

      {/* Timing + metadata */}
      <div className="bg-white border border-gray-300 rounded p-4 text-xs text-gray-500 font-sans flex flex-wrap items-center gap-6">
        <span>
          Pipeline time:{" "}
          <strong className="text-gray-900">
            {result.pipeline_timing.total_ms} ms
          </strong>
        </span>
        <span className="text-green-700 font-semibold">✓ Zero LLM calls</span>
        <span className="text-blue-700 font-semibold">✓ Deterministic</span>
        <span className="text-red-700 font-semibold">✓ Silent Exclusion</span>
        <TimingBreakdown timing={result.pipeline_timing} />
      </div>

      {/* Bottom: DAG | Candidate Set */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <DAGViewer result={result} />
        <CandidateSet nodes={result.candidate_set} />
      </div>
    </div>
  );
}

/* ─── Flow Summary ──────────────────────────────────────────────────────── */
function FlowSummary({ result }: { result: PipelineResult }) {
  const { funnel } = result;
  const boxes = [
    { label: "TOTAL", value: funnel.total_nodes, sub: "nodes" },
    { label: "BFS", value: funnel.after_bfs, sub: "reachable" },
    { label: "+Zone 2", value: funnel.after_zone2, sub: "combined" },
    { label: "5-CHECK", value: funnel.after_check5, sub: "final" },
  ];

  return (
    <div className="bg-white border border-gray-300 rounded p-4">
      <div className="flex items-center justify-center gap-3 flex-wrap">
        {boxes.map((box, i) => (
          <div key={box.label} className="flex items-center gap-3">
            <div
              className={`border-2 rounded p-3 text-center min-w-[90px] ${
                i === boxes.length - 1
                  ? "border-gray-900 bg-gray-900 text-white"
                  : "border-gray-400 bg-white text-gray-900"
              }`}
            >
              <div className="text-xs font-semibold tracking-widest uppercase opacity-70">
                {box.label}
              </div>
              <div className="text-2xl font-bold tabular-nums mt-0.5">
                {box.value}
              </div>
              <div className="text-[10px] opacity-60 mt-0.5">{box.sub}</div>
            </div>
            {i < boxes.length - 1 && (
              <span className="text-gray-400 font-bold text-lg">→</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─── Timing Breakdown (inline) ─────────────────────────────────────────── */
function TimingBreakdown({ timing }: { timing: import("@/lib/types").PipelineTiming }) {
  const steps = [
    { label: "Permission compile", ms: timing.permission_compile_ms },
    { label: "BFS traversal", ms: timing.bfs_ms },
    { label: "Zone 2 inject", ms: timing.zone2_inject_ms },
    { label: "Check 1 Isolation", ms: timing.check1_isolation_ms },
    { label: "Check 2 Compliance", ms: timing.check2_compliance_ms },
    { label: "Check 3 Permission", ms: timing.check3_permission_ms },
    { label: "Check 4 Temporal", ms: timing.check4_temporal_ms },
    { label: "Check 5 Derivability", ms: timing.check5_derivability_ms },
  ];
  return (
    <details className="ml-auto">
      <summary className="cursor-pointer text-xs text-gray-400 hover:text-gray-700">
        timing breakdown ▾
      </summary>
      <div className="mt-2 space-y-1">
        {steps.map((s) => (
          <div key={s.label} className="flex items-center gap-2 text-[11px]">
            <span className="w-36 text-gray-500">{s.label}</span>
            <span className="font-mono text-gray-700">{s.ms} ms</span>
          </div>
        ))}
      </div>
    </details>
  );
}
