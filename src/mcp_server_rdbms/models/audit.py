"""
mcp-server-rdbms: 数据库写操作审计流水模型契约.

@author Ateng
@since 2026-10-04
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """写操作审计流水事件模型.

    @author Ateng
    @since 2026-10-04
    """

    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    operation: str
    db: str
    statements: list[str]
    status: Literal["SUCCESS", "FAILED"]
    rows_affected: int = 0
    duration_ms: float = 0.0
    error: str | None = None
