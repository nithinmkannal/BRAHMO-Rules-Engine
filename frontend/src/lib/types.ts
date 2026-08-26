export interface User {
  id: string;
  org_id: string;
  name: string;
  role: string;
  department: string;
  ceiling_level: number;
  write_ceiling: number | null;
  compliance_clearance: string[];
  status: string;
}

export interface CandidateNode {
  id: string;
  type: "CONSTRAINT" | "DECISION" | "ANTI_PATTERN" | "FACT";
  title: string;
  content: string;
  importance: number;
  zone: 1 | 2 | 3;
  hierarchy_level: number | null;
  department: string | null;
  distance_from_entry: number;
  compression_hint: "FULL" | "COMPRESSED" | "CONSTRAINT_ONLY";
}

export interface PipelineTiming {
  permission_compile_ms: number;
  bfs_ms: number;
  zone2_inject_ms: number;
  check1_isolation_ms: number;
  check2_compliance_ms: number;
  check3_permission_ms: number;
  check4_temporal_ms: number;
  check5_derivability_ms: number;
  total_ms: number;
}

export interface PipelineFunnel {
  total_nodes: number;
  after_bfs: number;
  after_zone2: number;
  after_check1: number;
  after_check2: number;
  after_check3: number;
  after_check4: number;
  after_check5: number;
}

export interface PipelineResult {
  user: string;
  user_name: string;
  role: string;
  ceiling_level: number;
  entry_point: string;
  pipeline_timing: PipelineTiming;
  funnel: PipelineFunnel;
  candidate_set: CandidateNode[];
}
