from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KnowledgeNode:
    id: str
    org_id: str
    hierarchy_level_id: str
    type: str  # CONSTRAINT | DECISION | ANTI_PATTERN | FACT
    title: str
    content: str
    importance: float
    zone: int  # 1 | 2 | 3
    status: str  # ACTIVE | REVIEW_REQUIRED | SUPERSEDED | EXPIRED | LEGAL_HOLD
    derivability_score: float
    compliance_tags: list[str] = field(default_factory=list)
    valid_until: Optional[str] = None
    superseded_by: Optional[str] = None
    department: Optional[str] = None
    hierarchy_level_number: Optional[int] = None  # joined from hierarchy_levels
