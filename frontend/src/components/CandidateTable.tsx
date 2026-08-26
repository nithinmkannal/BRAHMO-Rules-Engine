"use client";

import { useState } from "react";
import { CandidateNode } from "@/lib/types";

interface Props {
  nodes: CandidateNode[];
}

const TYPE_COLORS: Record<string, string> = {
  CONSTRAINT:   "bg-red-100 text-red-800",
  DECISION:     "bg-blue-100 text-blue-800",
  ANTI_PATTERN: "bg-orange-100 text-orange-800",
  FACT:         "bg-gray-100 text-gray-700",
};

const TYPE_ICONS: Record<string, string> = {
  CONSTRAINT:   "🔴",
  DECISION:     "🔵",
  ANTI_PATTERN: "🟠",
  FACT:         "⚪",
};

const ZONE_BADGE: Record<number, string> = {
  1: "bg-gray-100 text-gray-600",
  2: "bg-purple-100 text-purple-700",
  3: "bg-yellow-100 text-yellow-700",
};

const ZONE_LABEL: Record<number, string> = {
  1: "Addressed",
  2: "Global",
  3: "Floating",
};

const COMPRESSION_STYLE: Record<string, { pill: string; label: string }> = {
  FULL:             { pill: "bg-green-100 text-green-800",  label: "FULL" },
  COMPRESSED:       { pill: "bg-yellow-100 text-yellow-800", label: "COMPRESSED" },
  CONSTRAINT_ONLY:  { pill: "bg-red-100 text-red-700",      label: "CONSTRAINT ONLY" },
};

export default function CandidateTable({ nodes }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (!nodes.length) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-400 text-sm">
        No candidate nodes. Run the pipeline to see results.
      </div>
    );
  }

  function toggleExpand(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  // Group by type for the summary line
  const typeCounts = nodes.reduce<Record<string, number>>((acc, n) => {
    acc[n.type] = (acc[n.type] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
          Candidate Set
          <span className="font-normal text-gray-400 ml-1.5">({nodes.length} nodes)</span>
        </h2>
        <div className="flex items-center gap-2">
          {Object.entries(typeCounts).map(([type, count]) => (
            <span
              key={type}
              className={`text-xs px-2 py-0.5 rounded font-medium ${TYPE_COLORS[type] ?? "bg-gray-100 text-gray-700"}`}
            >
              {TYPE_ICONS[type]} {count}
            </span>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 text-xs font-medium text-gray-500 uppercase tracking-wide">
            <tr>
              <th className="px-4 py-3 text-left w-8"></th>
              <th className="px-4 py-3 text-left">Title</th>
              <th className="px-4 py-3 text-left">Type</th>
              <th className="px-4 py-3 text-left">Zone</th>
              <th className="px-4 py-3 text-right">Importance</th>
              <th className="px-4 py-3 text-right">Dist</th>
              <th className="px-4 py-3 text-left">Hint</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {nodes.map((node) => {
              const isOpen = expanded.has(node.id);
              const cs = COMPRESSION_STYLE[node.compression_hint] ?? COMPRESSION_STYLE.CONSTRAINT_ONLY;
              return (
                <>
                  <tr
                    key={node.id}
                    onClick={() => toggleExpand(node.id)}
                    className="hover:bg-gray-50 cursor-pointer transition-colors"
                  >
                    {/* Expand toggle */}
                    <td className="px-4 py-3 text-gray-400 text-xs select-none">
                      {isOpen ? "▾" : "▸"}
                    </td>

                    {/* Title + ID */}
                    <td className="px-4 py-3 max-w-xs">
                      <div className="font-medium text-gray-900 truncate" title={node.title}>
                        {node.title}
                      </div>
                      <div className="text-[10px] font-mono text-gray-400 mt-0.5">{node.id}</div>
                    </td>

                    {/* Type */}
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${TYPE_COLORS[node.type] ?? "bg-gray-100 text-gray-700"}`}>
                        {node.type.replace("_", " ")}
                      </span>
                    </td>

                    {/* Zone */}
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs ${ZONE_BADGE[node.zone] ?? "bg-gray-100 text-gray-600"}`}>
                        {ZONE_LABEL[node.zone] ?? node.zone}
                      </span>
                    </td>

                    {/* Importance bar */}
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <div className="h-1.5 w-14 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className="h-1.5 bg-blue-500 rounded-full"
                            style={{ width: `${node.importance * 100}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-600 w-8 tabular-nums">
                          {node.importance.toFixed(2)}
                        </span>
                      </div>
                    </td>

                    {/* Distance */}
                    <td className="px-4 py-3 text-right text-gray-500 font-mono text-xs tabular-nums">
                      {node.distance_from_entry === 999 ? "∞" : node.distance_from_entry}
                    </td>

                    {/* Compression hint */}
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${cs.pill}`}>
                        {cs.label}
                      </span>
                    </td>
                  </tr>

                  {/* Expanded content row */}
                  {isOpen && (
                    <tr key={`${node.id}-expanded`} className="bg-blue-50/30">
                      <td />
                      <td colSpan={6} className="px-4 py-3">
                        <p className="text-xs text-gray-700 leading-relaxed whitespace-pre-wrap">
                          {node.content}
                        </p>
                        {node.department && (
                          <p className="text-[10px] text-gray-400 mt-1.5">
                            Dept: {node.department} · Level: {node.hierarchy_level ?? "—"}
                          </p>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
