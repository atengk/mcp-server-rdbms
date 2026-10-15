# 0028: 网络边缘加固、CORS 预检免密穿透、健康探针与全量连接池优雅回收

- **状态**: Accepted
- **日期**: 2026-10-15
- **决定者**: 阿腾 (Ateng)

## 背景与痛点

在 ADR-0027 确立了远端传输双层防御架构后，对真实生产环境（Docker 容器编排、Kubernetes 集群、反向代理自定义域名及浏览器端 Web AI 客户端接入）的深度攻防推演揭示了 4 项关键边缘缺陷：

1. **FastMCP DNS Rebinding 防御误杀**：FastMCP 默认开启 `TransportSecurityMiddleware`，硬编码主机与来源白名单仅限 `localhost`、`127.0.0.1` 和 `[::1]`。当在多容器网络（如 `http://mcp-rdbms:8000`）、局域网 IP（`192.168.x.x`）或由 Nginx 配置 `proxy_set_header Host $host` 携带自定义域名访问时，FastMCP 判定 Host 非法并抛出 `ValueError` 导致请求全面中断；
2. **浏览器 CORS Preflight（OPTIONS 预检）被令牌门禁阻断**：当 Web 端客户端（如基于浏览器的 Agent WebUI、Chatbox Web 版）跨域发起带 `Authorization` 头的请求时，浏览器根据 W3C 规范先发送无凭据的 `OPTIONS` 预检请求。若令牌门禁未经区分一律拦截，将导致返回 401 并使前端跨域握手永久失败；同时 FastMCP 默认缺乏跨域响应头；
3. **缺少轻量级健康检查与探针免密放行**：目前服务未提供 `/health` 探针路由。启用令牌后，若 Kubernetes Kubelet 或 Docker Compose 发起存活检测，因无 Token 会被 401 拦截，造成调度器误判服务宕机并触发无限重启风暴（CrashLoopBackOff）；
4. **容器停机（SIGTERM）导致数据库连接池泄露**：原 `registry.close_all()` 仅在 `except KeyboardInterrupt:`（SIGINT）中触发；容器编排系统销毁 Pod 时下发 `SIGTERM` 信号，Uvicorn 正常退出但未走异常块，造成数据库服务端残留死连接与孤儿事务锁。

## 架构决策

经 Grilling 架构推演，决定实施全面的网络边缘与生命周期加固：

1. **主机与来源安全白名单 (Allowed Hosts & Origins)**：
   - 遵循专属命名空间规则，新增 `MCP_RDBMS_ALLOWED_HOSTS`、`MCP_RDBMS_ALLOWED_ORIGINS` 环境变量与对应 CLI 参数；
   - 支持逗号分隔的域名/IP 列表或 `*` 全局通配符；若指定 `*` 则安全禁用底层 DNS Rebinding 保护（完全信任前置反代网关）；若指定具体主机则规范化注入 `server.settings.transport_security` 并保留本地回环，彻底消除反向代理与容器互联误杀。
2. **预检免认证穿透与可控 CORS 挂载 (CORS Preflight Bypass & Origins)**：
   - 在 `TokenAuthMiddleware` 中将 `request.method == "OPTIONS"` 显式纳入免认证放行通道；
   - 引入 `MCP_RDBMS_CORS_ORIGINS`（`--cors-origins`），默认保持严格不开启；当显式配置时挂载 Starlette 原生 `CORSMiddleware` 于最外层，使 401 认证失败响应亦携带合法 CORS 头部，赋能前端精准感知鉴权异常。
3. **健康探针免认证路由与云原生探活 (Public Health Probe)**：
   - 在 FastMCP 上注册 `@server.custom_route("/health")` 与 `@server.custom_route("/ping")`；
   - 在 `TokenAuthMiddleware` 中设置 `PUBLIC_PATHS = {"/health", "/ping"}` 免认证放行；
   - 在官方 `docker-compose.yaml` 中配置原生 `healthcheck:` 节，实现容器生命周期自动化健康观测。
4. **全量连接池优雅回收 (Graceful Pool Disposal)**：
   - 重构 `cli.py` `main()` 入口为标准的 `try ... finally: registry.close_all()` 结构，语言级保证无论通过 SIGINT、SIGTERM 还是异常崩溃退出，数据库连接池均 100% 显式关闭并释放底层网络句柄。

## 效果与收益

- **全场景适配**：消除反向代理域名、多容器网络与浏览器 Web 客户端跨域调用的阻断性陷阱；
- **云原生就绪**：原生集成健康探针与容器健康检测，防范生产环境探活误杀；
- **资源零泄露**：确保任何停机信号均能安全回收数据库连接池，保障数据库服务端运行稳定性。
