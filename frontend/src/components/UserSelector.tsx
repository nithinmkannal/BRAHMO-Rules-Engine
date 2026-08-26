"use client";

import { User } from "@/lib/types";

interface Props {
  users: User[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  onRun: () => void;
  loading: boolean;
}

const ROLE_COLORS: Record<string, string> = {
  ADMIN: "bg-red-100 text-red-800",
  HOD: "bg-purple-100 text-purple-800",
  EDITOR: "bg-blue-100 text-blue-800",
  VIEWER: "bg-green-100 text-green-800",
  QUALITY: "bg-yellow-100 text-yellow-800",
  AUDITOR: "bg-orange-100 text-orange-800",
};

export default function UserSelector({ users, selectedIds, onToggle, onRun, loading }: Props) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-4">
        Select Users (up to 3 for comparison)
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 mb-5">
        {users.map((user) => {
          const selected = selectedIds.includes(user.id);
          return (
            <button
              key={user.id}
              onClick={() => onToggle(user.id)}
              className={`text-left p-3 rounded-lg border-2 transition-all ${
                selected
                  ? "border-blue-500 bg-blue-50"
                  : "border-gray-200 hover:border-gray-300 bg-white"
              }`}
            >
              <div className="font-medium text-gray-900 text-sm">{user.name}</div>
              <div className="flex items-center gap-2 mt-1">
                <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${ROLE_COLORS[user.role] || "bg-gray-100 text-gray-700"}`}>
                  {user.role}
                </span>
                <span className="text-xs text-gray-500">L{user.ceiling_level}</span>
                <span className="text-xs text-gray-500">{user.department}</span>
              </div>
            </button>
          );
        })}
      </div>
      <button
        onClick={onRun}
        disabled={selectedIds.length === 0 || loading}
        className="px-5 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? "Running Pipeline…" : "▶ Run Pipeline"}
      </button>
    </div>
  );
}
