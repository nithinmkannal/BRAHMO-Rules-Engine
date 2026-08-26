from dataclasses import dataclass, field
from typing import Optional


@dataclass
class User:
    id: str
    org_id: str
    name: str
    role: str  # ADMIN | HOD | EDITOR | VIEWER | QUALITY | AUDITOR
    department: str
    ceiling_level: int
    write_ceiling: Optional[int]
    compliance_clearance: list[str] = field(default_factory=list)
    status: str = "ACTIVE"
