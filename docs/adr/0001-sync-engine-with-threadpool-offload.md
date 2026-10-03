# 0001: 采用同步 SQLAlchemy 引擎配合线程池卸载而非纯异步驱动

FastMCP 运行在异步事件循环中，但传统关系型数据库（如 Oracle `oracledb`、SQL Server `pyodbc` 以及各类国产数据库）的纯异步驱动生态碎片化且安装门槛高。我们决定采用标准的同步 SQLAlchemy 2.0 Engine，并在异步工具层通过 `anyio.to_thread.run_sync` 卸载至工作线程池执行。这以微弱的并发开销换取了对数十种主流与遗留数据库驱动 100% 的极致生态兼容性。
