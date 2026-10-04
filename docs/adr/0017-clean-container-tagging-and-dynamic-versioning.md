# ADR-0017: 纯净容器镜像标签矩阵与动态元数据版本反射

- **状态**: Accepted
- **日期**: 2026-10-04
- **决定者**: Ateng, 孔余

## 背景与问题陈述 (Context)

在之前的发布过程中，存在两项工程化缺陷：
1. **GHCR 镜像缺少 `latest` 标签且存在幽灵标签风险**：
   - 在 `.github/workflows/release.yml` 的 `docker/metadata-action` 中，手动添加了 `type=raw,value=latest`，与该 action 默认的 `flavor: latest=auto` 产生冲突，导致向 GitHub Container Registry (GHCR) 重复推送了同名的 `latest` 标签；
   - 未显式声明 `provenance: false` 与 `sbom: false`，导致 Buildx 默认注入了 SLSA provenance attestation，在 GHCR 界面生成 `unknown/unknown` 架构幽灵标签，掩盖或破坏了标准 OCI 镜像索引；
   - 缺少主版本号 `pattern={{major}}` 标签（如 `:1`）；
2. **Python 源码版本双重硬编码 (Violates SSOT)**：
   - 在 `src/atengk_mcp_server_rdbms/__init__.py` 中硬编码了 `__version__ = "x.y.z"`，每次版本变更需同时修改 `pyproject.toml` 和 `__init__.py`，极易发生版本漂移。

## 决策 (Decision)

我们决定对齐 `atengk/oss-template` 模版规范，全面推行**纯净容器标签矩阵**与**单一数据源动态版本反射**：

1. **重构 Docker Metadata 标签规则**：
   - 采用标准三级 SemVer 标签阶梯：
     ```yaml
     tags: |
       type=semver,pattern={{version}}
       type=semver,pattern={{major}}.{{minor}}
       type=semver,pattern={{major}}
     ```
   - 依赖 `docker/metadata-action` 内置的语义化版本算法自动、唯一地为正式发版打上 `latest` 标签；
2. **彻底禁用 Attestation 以保证产物纯净**：
   - 在 `docker/build-push-action` 中显式配置：
     ```yaml
     provenance: false
     sbom: false
     ```
   - 杜绝 Registry 生成附加的 attestation 幽灵标签，确保 `linux/amd64` 与 `linux/arm64` 多架构清单清晰稳定；
3. **推行动态元数据版本反射**：
   - 移除 `__init__.py` 中的字面量版本号，改用标准库 `importlib.metadata.version`；
   - `pyproject.toml` 成为版本号唯一事实来源（SSOT），后续迭代无需再触碰源码文件。

## 结果与影响 (Consequences)

### 正面影响 (Positive)
- **标签体系完备**：发版自动且稳定生成 `1.1.4`、`1.1`、`1` 与 `latest` 四级标准标签；
- **消除幽灵标签**：Registry 页面呈现纯净的多架构镜像索引，兼容老旧 Docker 引擎与私有 Registry；
- **消除维护负担**：Python 源码彻底解耦发版版本号，发版仅需更新 `pyproject.toml`。
