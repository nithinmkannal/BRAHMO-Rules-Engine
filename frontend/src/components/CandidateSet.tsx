"use client";

import { useState } from "react";
import { CandidateNode } from "@/lib/types";

interface Props {
  nodes: CandidateNode[];
}

const TYPE_CONFIG: Record<
  string,
  { emoji: string; label: string; headerBg: string; headerText: string }
> = {
  CONSTRAINT: {
    emoji: "🔴",
    label: "CONSTRAINT",
    headerBg: "bg-red-50 border-red-200",
    headerText: "text-red-800",
  },
  DECISION: {
    emoji: "🟡",
    label: "DECISION",
    headerBg: "bg-yellow-50 border-yellow-200",
    headerText: "text-yellow-800",
  },
  ANTI_PATTERN: {
    emoji: "🟠",
    label: "ANTI_PATTERN",
    headerBg: "bg-orange-50 border-orange-200",
    headerText: "text-orange-800",
  },
  FACT: {
    emoji: "🔵",
    label: "FACT",
    headerBg: "bg-blue-50 border-blue-200",
    headerText: "text-blue-800",
  },
};

const TYPE_ORDER = ["CONSTRAINT", "DECISION", "ANTI_PATTERN", "FACT"];

const ZONE_LABEL: Record<number, string> = {
  1: "addressed",
  2: "global",
  3: "floating",
};

export default function CandidateSet({ nodes }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (!nodes.length) {
    return (
      <div className="bg-white border border-gray-300 rounded p-8 text-center text-gray-400 text-sm font-sans">
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

  // Group by type
  const grouped: Record<string, CandidateNode[]> = {};
  for (const type of TYPE_ORDER) grouped[type] = [];
  for (const node of nodes) {
    if (grouped[node.type]) grouped[node.type].push(node);
    else grouped[node.type] = [node];
  }

  return (
    <div className="bg-white border border-gray-300 rounded overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-300 flex items-center justify-between">
        <h2 className="text-xs font-semibold text-gray-700 uppercase tracking-widest">
          CANDIDATE SET
        </h2>
        <span className="text-xs text-gray-500 font-sans">
          {nodes.length} nodes
        </span>
      </div>

      {/* Grouped sections */}
      <div className="divide-y divide-gray-200">
        {TYPE_ORDER.map((type) => {
          const group = grouped[type] ?? [];
          if (group.length === 0) return null;
          const cfg = TYPE_CONFIG[type] ?? {
            emoji: "⚪",
            label: type,
            headerBg: "bg-gray-50 border-gray-200",
            headerText: "text-gray-700",
          };

          return (
            <div key={type}>
              {/* Group header */}
              <div
                className={`px-4 py-2 border-b ${cfg.headerBg} flex items-center gap-2`}
              >
                <span>{cfg.emoji}</span>
                <span
                  className={`text-xs font-semibold uppercase tracking-wide ${cfg.headerText}`}
                >
                  {cfg.label}
                </span>
                <span className="text-xs text-gray-400 font-sans ml-1">
                  ({group.length} nodes)
                </span>
              </div>

              {/* Nodes in group */}
              <ul className="divide-y divide-gray-100">
                {group.map((node) => {
                  const isOpen = expanded.has(node.id);
                  return (
                    <li key={node.id}>
                      <button
                        onClick={() => toggleExpand(node.id)}
                        className="w-full text-left px-4 py-2.5 hover:bg-gray-50 transition-colors"
                      >
                        <div className="flex items-start gap-2">
                          <span className="text-gray-400 text-[10px] mt-0.5 select-none font-mono">
                            {isOpen ? "▾" : "▸"}
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-xs font-medium text-gray-900 font-sans">
                                {node.title}
                              </span>
                              {node.zone === 2 && (
                                <span className="text-[10px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded border border-purple-200 font-sans">
                                  GLOBAL
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-3 mt-0.5 text-[10px] text-gray-400 font-sans">
                              <span>
                                importance{" "}
                                <strong className="text-gray-600">
                                  {node.importance.toFixed(2)}
                                </strong>
                              </span>
                              <span>
                                distance{" "}
                                <strong className="text-gray-600">
                                  {node.distance_from_entry === 999
                                    ? "∞"
                                    : node.distance_from_entry}
                                </strong>
                              </span>
                              <span>
                                zone{" "}
                                <strong className="text-gray-600">
                                  {ZONE_LABEL[node.zone] ?? node.zone}
                                </strong>
                              </span>
                              <span className="uppercase font-mono">
                                {node.compression_hint}
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Expanded content */}
                        {isOpen && (
                          <div className="mt-2 ml-4 text-xs text-gray-600 font-sans leading-relaxed bg-gray-50 rounded p-2 border border-gray-200">
                            <p className="whitespace-pre-wrap">{node.content}</p>
                            {node.department && (
                              <p className="text-[10px] text-gray-400 mt-1.5">
                                Dept: {node.department} · Level:{" "}
                                {node.hierarchy_level ?? "—"}
                              </p>
                            )}
                          </div>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
    </div>
  );
}
