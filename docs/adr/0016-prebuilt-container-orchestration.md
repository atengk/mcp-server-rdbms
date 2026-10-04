# ADR-0016: 转向官方预构建容器编排并保留二次开发构建兼容

- **状态**: Accepted
- **日期**: 2026-10-04
- **决定者**: Ateng, 孔余

## 背景与问题陈述 (Context)

在项目发布至 v1.1.2 后，GitHub Actions 自动化 CI/CD 流水线已具备自动构建并推送 `linux/amd64` 与 `linux/arm64` 双架构官方 Docker 镜像至 GHCR (`ghcr.io/atengk/mcp-server-rdbms`) 的能力。
然而，仓库根目录的 `docker-compose.yaml` 中仍同时声明了 `image` 与未注释的 `build` 配置块。
这带来以下问题：
1. **开箱体验劣化**：外部用户或运维人员在拉取源码执行 `docker compose up` 时，会被迫在本地重复触发耗时数分钟的 Docker 镜像编译构建，且依赖本地构建环境；
2. **官方镜像旁路**：CI/CD 自动化构建的高性能多架构官方镜像被本地构建完全覆盖，未能发挥云端预构建分发优势。

## 决策 (Decision)

我们决定将 `docker-compose.yaml` 的默认交付模型**全面转为“官方预构建容器编排 (Pre-built Container Orchestrator)”**：

1. **默认纯镜像秒级拉取**：
   - `docker-compose.yaml` 默认仅激活 `image: ghcr.io/atengk/mcp-server-rdbms:latest`；
   - 生产部署用户甚至无需克隆整个源码仓库，仅下载单个 `docker-compose.yaml` 即可开箱即用；
2. **生产版本锁定指引**：
   - 在配置文件中显式提供固定版本号注释示例（`# image: ghcr.io/atengk/mcp-server-rdbms:1.1.2`），避免 `latest` 标签漂移影响生产稳定性；
3. **二次开发平滑兼容**：
   - 将 `build` 配置块保留并转为注释状态，开发者在需要修改 Python 源码并自行构建本地镜像时，仅需解开注释即可无缝执行 `docker compose build`。

## 结果与影响 (Consequences)

### 正面影响 (Positive)
- **部署效率大幅提升**：从数分钟的本地编译降为数秒级的云端镜像拉取；
- **分发边界彻底解耦**：用户仅凭单个编排文件与环境变量即可完整运行服务；
- **双模体验兼顾**：最终用户享受开箱即用，二次开发者保留本地定制灵活性。

### 需遵循的约束 (Negative/Trade-offs)
- 每次发布新版本后，需确保 CI/CD 的 `publish-docker` 流水线稳定完成镜像推送。
