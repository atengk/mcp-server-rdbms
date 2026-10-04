"""
mcp-server-rdbms: 表结构定义变更 (DDL) 结果模型契约.

@author Ateng
@since 2026-10-04
"""

from typing import Any

from pydantic import BaseModel, Field


class DdlResult(BaseModel):
    """表结构变更执行结果契约模型.

    @author Ateng
    @since 2026-10-04
    """

    success: bool = Field(description="DDL 语句是否执行成功")
    statement: str = Field(description="实际执行的规范化 DDL 语句")
    duration_ms: float = Field(description="操作执行耗时（毫秒）")
    message: str = Field(description="操作结果可读描述")

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典载荷."""
        return self.model_dump()
