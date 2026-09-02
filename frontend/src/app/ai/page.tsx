"use client";

import { useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ── Types ─────────────────────────────────────────────────────────────── */

interface User {
  id: string;
  name: string;
  role: string;
  department: string;
  ceiling_level: number;
}

interface ContextNode {
  id: string;
  type: "CONSTRAINT" | "DECISION" | "ANTI_PATTERN" | "FACT";
  title: string;
  content: string;
  importance: number;
  zone: number;
  department: string | null;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  contextNodes?: ContextNode[];
  candidateSetSize?: number;
  pipelineMs?: number;
  llmMs?: number;
  rawAnswer?: string;         // parallel raw response for comparison
  rawLlmMs?: number;
  isLoading?: boolean;
}

/* ── Test queries from the assessment ───────────────────────────────────── */

const TEST_QUERIES = [
  "What pain medication should I give a post-TKR patient?",
  "Patient Rajan has knee pain, what should I prescribe?",
  "When should I start DVT prophylaxis after surgery?",
  "What's our sepsis protocol?",
  "Tell me about Mrs. Padma's medication management",
];

/* ── Type styling ───────────────────────────────────────────────────────── */

const TYPE_STYLE: Record<string, { bg: string; text: string; border: string; label: string }> = {
  CONSTRAINT: { bg: "bg-red-50", text: "text-red-800", border: "border-red-200", label: "CONSTRAINT" },
  ANTI_PATTERN: { bg: "bg-orange-50", text: "text-orange-800", border: "border-orange-200", label: "ANTI-PATTERN" },
  DECISION: { bg: "bg-yellow-50", text: "text-yellow-800", border: "border-yellow-200", label: "DECISION" },
  FACT: { bg: "bg-blue-50", text: "text-blue-800", border: "border-blue-200", label: "FACT" },
};

/* ════════════════════════════════════════════════════════════════════════ */
export default function AIAssistantPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(true);
  const [activeContextMsg, setActiveContextMsg] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${API_BASE}/ai/users`)
      .then((r) => r.json())
      .then((data) => {
        setUsers(data);
        if (data.length > 0) setSelectedUserId(data[0].id);
      })
      .catch(() => setError("Cannot reach backend. Is FastAPI running on port 8000?"));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const selectedUser = users.find((u) => u.id === selectedUserId);

  async function sendMessage(query: string) {
    if (!query.trim() || !selectedUserId || loading) return;

    const userMsg: ChatMessage = { role: "user", content: query };
    const loadingMsg: ChatMessage = { role: "assistant", content: "", isLoading: true };

    setMessages((prev) => [...prev, userMsg, loadingMsg]);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      // Fire both requests in parallel: context-aware + raw
      const [contextRes, rawRes] = await Promise.all([
        fetch(`${API_BASE}/ai/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: selectedUserId, query }),
        }),
        fetch(`${API_BASE}/ai/chat/raw`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query }),
        }),
      ]);

      const contextData = await contextRes.json();
      const rawData = await rawRes.json();

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: contextData.answer,
        contextNodes: contextData.context_nodes_used,
        candidateSetSize: contextData.candidate_set_size,
        pipelineMs: contextData.pipeline_ms,
        llmMs: contextData.llm_ms,
        rawAnswer: rawData.answer,
        rawLlmMs: rawData.llm_ms,
      };

      setMessages((prev) => [...prev.slice(0, -1), assistantMsg]);
    } catch {
      setMessages((prev) => [
        ...prev.slice(0, -1),
        {
          role: "assistant",
          content: "Failed to get a response. Check backend connection.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    sendMessage(input);
  }

  function changeUser(id: string) {
    setSelectedUserId(id);
    setMessages([]);
    setActiveContextMsg(null);
  }

  /* ── Render ─────────────────────────────────────────────────────────── */

  return (
    <div className="flex h-screen bg-gray-50 font-sans overflow-hidden">

      {/* ── LEFT SIDEBAR ── */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col flex-shrink-0">
        {/* Header */}
        <div className="px-4 py-3 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-gray-900">Supra Hospital AI</span>
          </div>
          <div className="flex items-center gap-1 mt-1">
            <span className="text-[10px] bg-green-100 text-green-800 px-1.5 py-0.5 rounded border border-green-300 font-medium">
              BRAHMO Context
            </span>
            <span className="text-[10px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded border border-gray-300">
              GPT-4o-mini
            </span>
          </div>
        </div>

        {/* Doctor selector */}
        <div className="px-4 py-3 border-b border-gray-200">
          <label className="block text-[10px] font-semibold text-gray-500 uppercase tracking-widest mb-2">
            Active Doctor
          </label>
          <div className="space-y-1">
            {users.map((u) => (
              <button
                key={u.id}
                onClick={() => changeUser(u.id)}
                className={`w-full text-left px-3 py-2 rounded text-xs transition-colors ${
                  u.id === selectedUserId
                    ? "bg-gray-900 text-white"
                    : "bg-gray-50 text-gray-700 hover:bg-gray-100 border border-gray-200"
                }`}
              >
                <div className="font-semibold">{u.name}</div>
                <div className={`text-[10px] mt-0.5 ${u.id === selectedUserId ? "text-gray-300" : "text-gray-400"}`}>
                  {u.role} · L{u.ceiling_level} · {u.department}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Test queries */}
        <div className="px-4 py-3 flex-1 overflow-y-auto">
          <label className="block text-[10px] font-semibold text-gray-500 uppercase tracking-widest mb-2">
            Assessment Queries
          </label>
          <div className="space-y-1">
            {TEST_QUERIES.map((q, i) => (
              <button
                key={i}
                onClick={() => sendMessage(q)}
                disabled={loading || !selectedUserId}
                className="w-full text-left px-2 py-2 rounded text-[11px] text-gray-600 hover:bg-gray-50 hover:text-gray-900 border border-transparent hover:border-gray-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed leading-snug"
              >
                {q}
              </button>
            ))}
          </div>
        </div>

        {/* Nav link back */}
        <div className="px-4 py-3 border-t border-gray-200">
          <a
            href="/"
            className="block text-center text-xs text-gray-400 hover:text-gray-700 transition-colors"
          >
            ← BRAHMO Rules Engine
          </a>
        </div>
      </aside>

      {/* ── MAIN CHAT AREA ── */}
      <div className="flex-1 flex flex-col min-w-0">

        {/* Top bar */}
        <div className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between flex-shrink-0">
          <div>
            {selectedUser ? (
              <div>
                <span className="text-sm font-semibold text-gray-900">{selectedUser.name}</span>
                <span className="text-xs text-gray-400 ml-2">
                  {selectedUser.role} · {selectedUser.department} · Level {selectedUser.ceiling_level}
                </span>
              </div>
            ) : (
              <span className="text-sm text-gray-400">Select a user to begin</span>
            )}
          </div>
          <label className="flex items-center gap-2 text-xs text-gray-500 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showRaw}
              onChange={(e) => setShowRaw(e.target.checked)}
              className="rounded"
            />
            Show raw ChatGPT comparison
          </label>
        </div>

        {/* Error */}
        {error && (
          <div className="mx-6 mt-4 bg-red-50 border border-red-200 rounded px-4 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Message thread */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
          {messages.length === 0 && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md">
                <div className="text-4xl mb-3">🏥</div>
                <h2 className="text-lg font-semibold text-gray-700 mb-2">
                  Supra Hospital AI Assistant
                </h2>
                <p className="text-sm text-gray-500 mb-4">
                  This AI knows Supra Hospital's protocols, drug preferences, patient-specific
                  constraints, and departmental decisions — filtered specifically for{" "}
                  <strong>{selectedUser?.name ?? "the selected doctor"}</strong>.
                </p>
                <p className="text-xs text-gray-400">
                  Ask a clinical question or click one of the assessment queries on the left.
                </p>
              </div>
            </div>
          )}

          {messages.map((msg, idx) => (
            <MessageBubble
              key={idx}
              msg={msg}
              index={idx}
              showRaw={showRaw}
              isContextOpen={activeContextMsg === idx}
              onToggleContext={() =>
                setActiveContextMsg(activeContextMsg === idx ? null : idx)
              }
            />
          ))}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="bg-white border-t border-gray-200 px-6 py-4 flex-shrink-0">
          <form onSubmit={handleSubmit} className="flex gap-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                selectedUserId
                  ? "Ask a clinical question…"
                  : "Select a doctor first…"
              }
              disabled={!selectedUserId || loading}
              className="flex-1 border border-gray-300 rounded-lg px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:border-gray-500 disabled:opacity-50 disabled:bg-gray-50"
            />
            <button
              type="submit"
              disabled={!input.trim() || !selectedUserId || loading}
              className="px-5 py-2.5 bg-gray-900 text-white text-sm rounded-lg hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "…" : "Send"}
            </button>
          </form>
        </div>
      </div>

      {/* ── RIGHT PANEL: Context nodes ── */}
      {activeContextMsg !== null && messages[activeContextMsg]?.contextNodes && (
        <ContextPanel
          nodes={messages[activeContextMsg]!.contextNodes!}
          candidateSetSize={messages[activeContextMsg]!.candidateSetSize ?? 0}
          pipelineMs={messages[activeContextMsg]!.pipelineMs ?? 0}
          onClose={() => setActiveContextMsg(null)}
        />
      )}
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════════ */
/* MessageBubble                                                            */
/* ════════════════════════════════════════════════════════════════════════ */

function MessageBubble({
  msg,
  index,
  showRaw,
  isContextOpen,
  onToggleContext,
}: {
  msg: ChatMessage;
  index: number;
  showRaw: boolean;
  isContextOpen: boolean;
  onToggleContext: () => void;
}) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-lg bg-gray-900 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed">
          {msg.content}
        </div>
      </div>
    );
  }

  if (msg.isLoading) {
    return (
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 rounded-full bg-blue-100 flex items-center justify-center text-xs">🏥</div>
        <div className="flex gap-1">
          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* ── Supra-aware answer ── */}
      <div className="flex gap-3">
        <div className="w-6 h-6 rounded-full bg-blue-100 flex items-center justify-center text-xs flex-shrink-0 mt-0.5">
          🏥
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold text-gray-700">Supra Hospital AI</span>
            <span className="text-[10px] bg-green-100 text-green-700 px-1.5 py-0.5 rounded border border-green-200">
              {msg.candidateSetSize} context nodes
            </span>
            {msg.pipelineMs !== undefined && (
              <span className="text-[10px] text-gray-400">
                pipeline {msg.pipelineMs}ms
              </span>
            )}
          </div>
          <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
            {msg.content}
          </div>
          {/* Context toggle */}
          {msg.contextNodes && msg.contextNodes.length > 0 && (
            <button
              onClick={onToggleContext}
              className={`mt-1.5 text-[11px] px-2 py-1 rounded border transition-colors ${
                isContextOpen
                  ? "bg-gray-900 text-white border-gray-900"
                  : "text-gray-500 border-gray-200 hover:border-gray-400 hover:text-gray-700"
              }`}
            >
              {isContextOpen ? "▸ hide context" : "▾ view Supra context used"}
            </button>
          )}
        </div>
      </div>

      {/* ── Raw ChatGPT comparison ── */}
      {showRaw && msg.rawAnswer && (
        <div className="flex gap-3 ml-9">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-semibold text-gray-400">Raw ChatGPT</span>
              <span className="text-[10px] bg-red-50 text-red-600 px-1.5 py-0.5 rounded border border-red-200">
                0 context nodes
              </span>
              <span className="text-[10px] text-gray-300">no hospital knowledge</span>
            </div>
            <div className="bg-red-50 border border-red-200 rounded-2xl px-4 py-3 text-sm text-gray-700 leading-relaxed opacity-80 whitespace-pre-wrap">
              {msg.rawAnswer}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════════ */
/* ContextPanel — right drawer showing which nodes were used               */
/* ════════════════════════════════════════════════════════════════════════ */

function ContextPanel({
  nodes,
  candidateSetSize,
  pipelineMs,
  onClose,
}: {
  nodes: ContextNode[];
  candidateSetSize: number;
  pipelineMs: number;
  onClose: () => void;
}) {
  const sortedNodes = [...nodes].sort((a, b) => {
    const typeOrder = { CONSTRAINT: 0, ANTI_PATTERN: 1, DECISION: 2, FACT: 3 };
    const ta = typeOrder[a.type] ?? 3;
    const tb = typeOrder[b.type] ?? 3;
    if (ta !== tb) return ta - tb;
    return b.importance - a.importance;
  });

  return (
    <aside className="w-80 bg-white border-l border-gray-200 flex flex-col flex-shrink-0 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between flex-shrink-0">
        <div>
          <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-widest">
            Supra Context Used
          </h3>
          <p className="text-[10px] text-gray-400 mt-0.5">
            {candidateSetSize} nodes · {pipelineMs}ms BRAHMO pipeline
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-700 text-sm transition-colors"
        >
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto divide-y divide-gray-100">
        {sortedNodes.map((node) => {
          const style = TYPE_STYLE[node.type] ?? TYPE_STYLE.FACT;
          return (
            <div key={node.id} className="px-4 py-3">
              <div className="flex items-start gap-2">
                <span
                  className={`text-[9px] font-bold px-1.5 py-0.5 rounded border flex-shrink-0 mt-0.5 ${style.bg} ${style.text} ${style.border}`}
                >
                  {style.label}
                </span>
                {node.zone === 2 && (
                  <span className="text-[9px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded border border-purple-200 flex-shrink-0 mt-0.5">
                    GLOBAL
                  </span>
                )}
              </div>
              <p className="text-xs font-semibold text-gray-800 mt-1.5 leading-snug">
                {node.title}
              </p>
              <p className="text-[11px] text-gray-500 mt-1 leading-relaxed">
                {node.content.length > 160
                  ? node.content.slice(0, 160) + "…"
                  : node.content}
              </p>
              <div className="flex items-center gap-3 mt-1.5 text-[10px] text-gray-400">
                <span>imp {node.importance.toFixed(2)}</span>
                {node.department && <span>{node.department}</span>}
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
