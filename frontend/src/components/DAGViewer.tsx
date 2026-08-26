"use client";

import { PipelineResult } from "@/lib/types";

interface Props {
  result: PipelineResult;
}

interface TreeNode {
  id: string;
  label: string;
  dept: string | null;
  children: TreeNode[];
}

// Static DAG tree — matches seed.sql exactly
const DAG_TREE: TreeNode = {
  id: "HL-01", label: "Hospital Root", dept: null,
  children: [
    {
      id: "HL-03-CLIN", label: "Clinical Division", dept: null,
      children: [
        {
          id: "HL-05-ORTHO", label: "Orthopaedics", dept: "ortho",
          children: [
            {
              id: "HL-08-ORTHO-GEN", label: "Ortho General", dept: "ortho",
              children: [
                {
                  id: "HL-10-ORTHO-W", label: "Ortho Ward", dept: "ortho",
                  children: [
                    { id: "HL-12-RAJAN", label: "Patient: Rajan", dept: "ortho", children: [] },
                  ],
                },
              ],
            },
            { id: "HL-08-ORTHO-TKR", label: "Ortho TKR Unit", dept: "ortho", children: [] },
            { id: "HL-08-POST-TKR",  label: "Post-TKR Area ★ multi-parent", dept: "ortho", children: [] },
          ],
        },
        {
          id: "HL-05-MED", label: "General Medicine", dept: "medicine",
          children: [
            {
              id: "HL-08-MED-GEN", label: "Medicine General", dept: "medicine",
              children: [
                {
                  id: "HL-10-MED-W", label: "Medicine Ward", dept: "medicine",
                  children: [
                    { id: "HL-12-PADMA", label: "Patient: Padma", dept: "medicine", children: [] },
                  ],
                },
              ],
            },
          ],
        },
        {
          id: "HL-05-CARDIO", label: "Cardiology", dept: "cardiology",
          children: [
            { id: "HL-08-CARDIO-CCU", label: "Cardiac Care Unit", dept: "cardiology", children: [] },
          ],
        },
        {
          id: "HL-05-PAEDS", label: "Paediatrics", dept: "paediatrics",
          children: [
            { id: "HL-10-PAEDS-W", label: "Paediatrics Ward", dept: "paediatrics", children: [] },
          ],
        },
        { id: "HL-05-SURG", label: "Surgery", dept: "surgery", children: [] },
        { id: "HL-05-ICU",  label: "ICU", dept: "icu", children: [] },
        { id: "HL-10-PHARMACY", label: "Pharmacy (L10)", dept: "pharmacy", children: [] },
        { id: "HL-06-QUALITY", label: "Quality & Safety (L6)", dept: "quality", children: [] },
      ],
    },
    {
      id: "HL-03-ADMIN", label: "Administrative Division", dept: null, children: [],
    },
    {
      id: "HL-GLOBAL", label: "Global Constraints (Zone 2)", dept: null, children: [],
    },
  ],
};

// Derive which hierarchy level IDs are reachable from the candidate set.
// A level is "reachable" if at least one surviving node belongs to it.
// We infer the level from node.department + node.hierarchy_level and
// map back to level IDs using the same static DAG tree.
function buildReachableSet(result: PipelineResult): Set<string> {
  const reachable = new Set<string>();

  // Always mark the entry point itself
  reachable.add(result.entry_point);

  // Walk all candidate nodes — each carries hierarchy_level (number) + department.
  // Build a dept→level→id reverse lookup from the static tree.
  const levelToIds: Map<string, string[]> = new Map();
  function indexTree(node: TreeNode) {
    const key = `${node.dept ?? "__null__"}`;
    if (!levelToIds.has(key)) levelToIds.set(key, []);
    levelToIds.get(key)!.push(node.id);
    node.children.forEach(indexTree);
  }
  indexTree(DAG_TREE);

  // For each candidate node, find the matching tree node by id matching
  // what we know from the pipeline: entry_point is an HL-id, and the
  // candidate set nodes carry department + hierarchy_level.
  // We mark ALL ancestors of the entry point as reachable by walking the tree.
  function collectAncestors(node: TreeNode, target: string, path: string[]): string[] | null {
    const current = [...path, node.id];
    if (node.id === target) return current;
    for (const child of node.children) {
      const found = collectAncestors(child, target, current);
      if (found) return found;
    }
    return null;
  }

  // Mark the full ancestor path from root to entry point as reachable
  const ancestorPath = collectAncestors(DAG_TREE, result.entry_point, []);
  if (ancestorPath) ancestorPath.forEach((id) => reachable.add(id));

  // Also mark Zone 2 if any Global-zone nodes survived
  const hasZone2 = result.candidate_set.some((n) => n.zone === 2);
  if (hasZone2) reachable.add("HL-GLOBAL");

  return reachable;
}

function LevelRow({
  node,
  reachable,
  entryPoint,
  depth,
}: {
  node: TreeNode;
  reachable: Set<string>;
  entryPoint: string;
  depth: number;
}) {
  const isEntry   = node.id === entryPoint;
  const isZone2   = node.id === "HL-GLOBAL";
  const isReach   = reachable.has(node.id);

  let dot = "○";
  let dotColor = "text-gray-300";
  let labelColor = "text-gray-400";
  let bg = "";

  if (isZone2) {
    dot = "◆"; dotColor = "text-purple-500"; labelColor = "text-purple-700"; bg = "bg-purple-50";
  } else if (isEntry) {
    dot = "●"; dotColor = "text-green-600 font-bold"; labelColor = "text-green-800 font-semibold"; bg = "bg-green-50";
  } else if (isReach) {
    dot = "●"; dotColor = "text-blue-500"; labelColor = "text-gray-800"; bg = "bg-blue-50/40";
  }

  return (
    <>
      <div
        className={`flex items-center gap-1.5 py-0.5 px-1 rounded text-xs ${bg}`}
        style={{ paddingLeft: `${depth * 16 + 4}px` }}
      >
        <span className={`font-mono text-[11px] ${dotColor}`}>{dot}</span>
        <span className={labelColor}>{node.label}</span>
        {isEntry && (
          <span className="ml-1 text-[10px] bg-green-200 text-green-800 px-1 rounded font-medium">
            ENTRY
          </span>
        )}
        {isZone2 && (
          <span className="ml-1 text-[10px] bg-purple-200 text-purple-800 px-1 rounded font-medium">
            ZONE 2
          </span>
        )}
      </div>
      {node.children.map((child) => (
        <LevelRow
          key={child.id}
          node={child}
          reachable={reachable}
          entryPoint={entryPoint}
          depth={depth + 1}
        />
      ))}
    </>
  );
}

export default function DAGViewer({ result }: Props) {
  const reachable = buildReachableSet(result);
  const reachableCount = Array.from(reachable).filter((id) => id !== "HL-GLOBAL").length;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
          DAG Hierarchy
        </h2>
        <span className="text-xs text-gray-400">
          {reachableCount} levels reachable
        </span>
      </div>
      <p className="text-xs text-gray-500 mb-3">
        Entry:{" "}
        <code className="bg-gray-100 px-1.5 py-0.5 rounded font-mono text-gray-700">
          {result.entry_point}
        </code>
      </p>

      {/* Legend */}
      <div className="flex items-center gap-4 mb-3 text-[11px] text-gray-500">
        <span><span className="text-green-600 font-bold">●</span> Entry</span>
        <span><span className="text-blue-500">●</span> Reachable</span>
        <span><span className="text-gray-300">○</span> Not reachable</span>
        <span><span className="text-purple-500">◆</span> Zone 2 (global)</span>
      </div>

      <div className="overflow-auto max-h-72 border border-gray-100 rounded-lg p-2 bg-gray-50 space-y-0.5">
        <LevelRow
          node={DAG_TREE}
          reachable={reachable}
          entryPoint={result.entry_point}
          depth={0}
        />
      </div>
    </div>
  );
}
