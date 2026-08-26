from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CandidateNode:
    id: str
    type: str
    title: str
    content: str
    importance: float
    zone: int
    hierarchy_level: Optional[int]
    department: Optional[str]
    distance_from_entry: int
    compression_hint: str  # FULL | COMPRESSED | CONSTRAINT_ONLY


@dataclass
class PipelineTiming:
    permission_compile_ms: float = 0
    bfs_ms: float = 0
    zone2_inject_ms: float = 0
    check1_isolation_ms: float = 0
    check2_compliance_ms: float = 0
    check3_permission_ms: float = 0
    check4_temporal_ms: float = 0
    check5_derivability_ms: float = 0
    total_ms: float = 0


@dataclass
class PipelineFunnel:
    total_nodes: int = 0
    after_bfs: int = 0
    after_zone2: int = 0
    after_check1: int = 0
    after_check2: int = 0
    after_check3: int = 0
    after_check4: int = 0
    after_check5: int = 0


@dataclass
class CandidateSet:
    user: str
    user_name: str
    role: str
    ceiling_level: int
    entry_point: str
    pipeline_timing: PipelineTiming
    funnel: PipelineFunnel
    candidate_set: list[CandidateNode] = field(default_factory=list)
