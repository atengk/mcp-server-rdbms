"""
mcp-server-rdbms: 数据库管理与活动查询观测模型契约.

@author Ateng
@since 2026-10-04
"""

from typing import Any

from pydantic import BaseModel, Field


class RunningQuery(BaseModel):
    """活动查询进程明细模型.

    @author Ateng
    @since 2026-10-04
    """

    pid: str | int | None = Field(default=None, description="进程/会话标识")
    user: str | None = Field(default=None, description="执行用户")
    db: str | None = Field(default=None, description="所属数据库名")
    duration_seconds: float | None = Field(default=None, description="已运行耗时（秒）")
    state: str | None = Field(default=None, description="连接/线程状态")
    query: str | None = Field(default=None, description="当前执行的 SQL 语句")


class RunningQueriesResult(BaseModel):
    """活动查询观测结果载荷模型.

    @author Ateng
    @since 2026-10-04
    """

    supported: bool = Field(description="当前数据库方言是否支持活动查询观测")
    dialect: str = Field(description="数据库方言标识")
    queries: list[RunningQuery] = Field(default_factory=list, description="活动进程查询列表（无结果时为空列表）")
    message: str | None = Field(default=None, description="优雅降级说明或状态信息")

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典载荷."""
        return self.model_dump()
