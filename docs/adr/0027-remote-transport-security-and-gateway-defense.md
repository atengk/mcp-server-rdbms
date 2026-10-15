# 0027: 远端传输网络安全威胁模型、令牌门禁与反向代理网关防御

- **状态**: Accepted
- **日期**: 2026-10-15
- **决定者**: 阿腾 (Ateng)

## 背景与痛点

当 MCP 服务的通信传输协议由本地管道模式（`stdio`）切换至网络模式（`sse` 或 `streamable-http`）时，服务本质上转变为一个常驻的 HTTP 网络守护进程。由于该服务直连企业核心关系型数据库，直接以裸协议向网络开放将面临极其严重的生产级安全风险：

1. **零认证越权执行 (Unauthenticated Access)**：FastMCP 默认未启用应用层身份鉴权。任何能触达 HTTP 端口的网络客户端或恶意爬虫，均可直接下发 JSON-RPC 调用 `sql_query` 探查数据，甚至在开放 DML/DDL 时篡改或清空数据库；
2. **明文传输与中间人窃听 (Cleartext Sniffing & MITM)**：未启用 TLS/HTTPS 时，所有 SQL 语句、数据库 Schema 与返回数据在网络链路中完全明文传输；
3. **容器网络无感全网卡暴露 (0.0.0.0 Exposure)**：Docker 容器默认监听 `0.0.0.0`，在宿主机映射端口若未收敛至本地回环，可能意外向公网或未受信任局域网暴露；
4. **浏览器跨站与 DNS 重绑定攻击 (Cross-Site & DNS Rebinding)**：浏览器端 AI 客户端或恶意网页脚本可能向本地暴露的端口发起未授权跨站调用；
5. **慢查询与连接洪峰 DoS (Resource Exhaustion)**：长连接无并发与速率限制，易被恶意请求打满连接池导致服务雪崩。

## 架构决策

经 Grilling 访谈与攻防推演，决定实施**双层防御架构（Dual-Layer Defense Architecture）**：

1. **服务端内置轻量访问令牌门禁 (Bearer Token Gate)**：
   - 遵循专属命名空间规则（Dedicated Namespace Rule），新增 `MCP_RDBMS_AUTH_TOKEN` 环境变量与 `--auth-token` 启动参数；
   - 在 Starlette 应用层挂载原生 `TokenAuthMiddleware` 中间件；
   - 采用常数时间比较算法（`hmac.compare_digest`）比对 `Authorization: Bearer <token>` 头部或 URL 查询参数 `?token=<token>`，对非法或缺失令牌请求直接响应 `401 Unauthorized`；
   - 未配置令牌时保持向后兼容（便于本地容器内网调试），并在 `--doctor` 自检探针中对无凭据网络暴露主动输出安全告警。
2. **生产环境反向代理网关防御 (Reverse Proxy Gateway Defense)**：
   - 遵循云原生微服务职责分离原则，明确将传输层证书卸载（TLS/HTTPS）、IP 白名单、网络级速率限制（Rate Limiting）及外部 OAuth/OIDC 认证等重型网络安全职责交由成熟的前置网关（Nginx、Caddy、Envoy、API Gateway）统一收敛；
   - 官方交付标准 Nginx 与 Caddy 生产级反向代理加固配置模板。
3. **安全回环绑定收敛 (Localhost Loopback Binding)**：
   - 更新官方 `docker-compose.yaml` 默认端口绑定为 `"127.0.0.1:8000:8000"`，强制仅允许宿主机本地回环或同主机的反向代理访问，物理级封堵外部未授权网络直连通道。

## 效果与收益

- **双轨兼备**：轻量场景可仅凭一行 `MCP_RDBMS_AUTH_TOKEN` 实现极简原生防裸奔；生产场景通过网关代理构筑企业级合规纵深堡垒；
- **时序安全**：消除简易字符串比对引发的侧信道时序攻击风险；
- **安全默认**：容器默认端口绑定收敛至本地回环，贯彻“默认即安全”工程准则。
