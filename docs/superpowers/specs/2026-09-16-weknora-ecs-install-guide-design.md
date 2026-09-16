# 设计文档：WeKnora ECS 安装方案（可执行文档）

- 日期：2026-09-16
- 状态：已确认（设计获用户批准）
- 背景依托：RF-20260915-knowledge-base 知识库选型研究（top1 为 WeKnora）

## 1. 背景与目标

知识库选型研究已推荐 WeKnora 为 top1。用户决定在一台独立的阿里云 ECS（10.17.21.95）
上安装 WeKnora v0.8.0 进行实际体验。本任务产出**一份自包含、可照做的安装方案文档**，
用户将带到另一个会话/另一台机器上执行。

用户已确认的决策：
1. 部署规模：标准集（默认 5 容器 + neo4j GraphRAG + minio 对象存储）
2. 模型配置：先不配，启动后在 Web UI 自行配置
3. 版本：v0.8.0 线（`WEKNORA_VERSION=v0.8.0` 固定，与研究锚定一致）
4. 执行方式：只产出方案文档，由用户在另外的会话执行安装

## 2. 产出物清单

| 文件 | 位置 | 说明 |
|------|------|------|
| WeKnora安装方案.md | `_bmad-output/research-projects/RF-20260915-knowledge-base/06-final-deliverables/` | 唯一交付物，8 节自包含安装文档 |

## 3. 目标机器环境快照（2026-09-16 实测，写入文档"环境前提"节）

| 项 | 实测值 | 来源 |
|----|--------|------|
| OS | Ubuntu 22.04.5 LTS | `/etc/os-release` |
| 架构 | **aarch64（ARM64）** | `uname -m` |
| CPU/内存 | 8 核 / 15GB（可用 15GB） | `nproc` / `free -h` |
| 磁盘 | 系统盘 vda1 26GB 可用（29GB 总量）；**数据盘 vdb 挂载 /data，80GB 可用**（98GB 总量，已用 14GB，fstab 持久挂载） | `df -h` / `lsblk` |
| Docker | 未安装 | `docker --version` 失败 |
| 端口 | 80/8080/7474/7687/9000/9090/5432/6379/11434 全空闲 | `ss -tlnp` |
| GitHub 可达性 | 200，约 1s | `curl https://github.com` |
| Docker Hub 可达性 | **registry-1.docker.io 8 秒超时** | `curl` |
| SSH | ubuntu 用户免密可连，sudo 免密 | 已实测 |

**ARM64 镜像架构支持（docker hub API 实证，2026-09-16）**：

| 镜像 | arm64 |
|------|-------|
| paradedb/paradedb:v0.22.2-pg17 | ✅ |
| wechatopenai/weknora-app:latest | ✅ |
| wechatopenai/weknora-docreader:latest | ✅ |
| wechatopenai/weknora-ui:latest | ✅ |
| wechatopenai/weknora-sandbox:latest | ✅ |
| qdrant/qdrant:v1.16.2 | ✅ |
| redis:7.0-alpine | ✅ |
| searxng/searxng:latest | ✅ |
| neo4j:2025.10.1 | 官方长期发布 arm64（hub API 限流未实证，文档中列入 `docker manifest inspect` 复核步骤） |
| minio/minio:RELEASE.2025-09-07T16-13-09Z | 同上，列入复核步骤 |

## 4. 文档结构（8 节）与内容要求

### 第 1 节：环境前提
- 环境快照表（§3 数据）+ 执行前复核命令块（`nproc`/`free -h`/`df -h`/`lsblk`（确认 /data 挂载）/`ss -tlnp`/docker 检查，
  每命令一行、附预期输出示例）——执行会话必须重跑一遍，环境变化时先对照调整
- 判定阈值：≥4 核、≥8GB 内存、**数据盘 /data 可用 ≥20GB**、80/8080 空闲；不满足时的处理指引

### 第 2 节：安装 Docker
- 官方脚本路径（`curl -fsSL https://get.docker.com | sudo sh`，支持 arm64）
- 将 ubuntu 加入 docker 组（免 sudo 用 docker）
- **阿里云镜像加速器配置**（`/etc/docker/daemon.json` 的 registry-mirrors，附获取加速器地址的说明）
- **Docker 数据根目录改到数据盘**：daemon.json 配置 `data-root: /data/docker`（镜像 5-8GB 不入系统盘；
  附 `sudo mkdir -p /data/docker` 命令；/data 已有 14GB 既有内容，不得触碰 /data 下其他目录）
- 重启 docker + `docker run hello-world` 验证
- 附：Compose 插件已随官方脚本安装（`docker compose version` 验证）

### 第 3 节：镜像架构复核（arm64 专项）
- 上表 arm64 清单
- `docker manifest inspect --verbose <image> | grep -A3 arm64` 复核命令（对 neo4j/minio 两个待复核项必做）
- 若某镜像无 arm64 的处理：错误表现（`no matching manifest for linux/arm64/v8`）+ 替代方案说明

### 第 4 节：拉取源码与配置
- 安装位置：**数据盘 `/data/WeKnora`**（用户要求；`sudo mkdir -p /data/WeKnora && sudo chown $USER:$USER /data/WeKnora`，/data 属 root，须先赋权）
- `git clone https://github.com/Tencent/WeKnora.git /data/WeKnora && cd /data/WeKnora`
- `cp .env.example .env`，设置 `WEKNORA_VERSION=v0.8.0`
- `.env` 其余全部保持默认（模型不配；`OLLAMA_OPTIONAL=true` 已默认，无 Ollama 不阻断启动）
- 磁盘提示：源码+镜像+卷约 6-9GB（Docker 数据在 /data/docker、源码在 /data/WeKnora，均在数据盘 80GB 余量内），安装后 `docker system df` 查看

### 第 5 节：启动服务
- `docker compose pull`（首次拉取，走加速器）
- `docker compose --profile neo4j --profile minio up -d`
- 启动顺序说明：等待 1-2 分钟（首次含自动数据库迁移）
- 预期容器清单表：frontend(80)/app(8080)/docreader/postgres/redis/neo4j(7474/7687)/minio(9000/9001)

### 第 6 节：启动验证
- `docker compose ps`（7 容器 running）
- `docker compose logs app | tail`（迁移完成/服务就绪特征行）
- `curl http://localhost:8080/health`（后端健康检查，端点源码实证：`internal/router/router.go:131`）与 `curl -I http://localhost`（前端 200）
- 浏览器访问 `http://10.17.21.95`（内网 IP；若机器有安全组，需放行 80/8080 端口——ECS 安全组提示）
- **首次登录**：v0.7.0+ 为自助注册模式（`WEKNORA_TENANT_SELF_SERVICE_CREATION_ENABLED=true` 默认），
  打开页面注册账号即用，无默认密码；若注册入口未出现，查 `WEKNORA_AUTH_DEFAULT_TENANT_MODE` 默认值说明

### 第 7 节：模型配置（启动后）
- Web UI 中配置 LLM/Embedding/Rerank 模型的步骤要点
- 常见厂商接入表：Kimi（moonshot，OpenAI 兼容）、DeepSeek、智谱，各给 base_url 与模型名示例
- Embedding 必配说明（文档向量化必需；LLM 未配时仅部分功能可用）

### 第 8 节：故障排查与维护
- Docker Hub 拉取超时 → 检查加速器配置/换加速源（列表）
- 内存不足 → 停用 neo4j profile 的最小集降级命令
- 端口冲突 → .env 改 `FRONTEND_PORT`/`APP_PORT` 的方法
- 磁盘 → `docker system prune` 与数据卷位置说明（Docker 数据根在 /data/docker、源码在 /data/WeKnora，均在数据盘）
- 安全加固：研究报告结论——最新版（≥v0.7.0）、关公开注册、MCP 面最小化、出口流量过滤
- 升级：`git pull` + `WEKNORA_VERSION` 更新 + `docker compose pull && up -d`，附升级前备份
  （postgres/minio 数据卷）命令

## 5. 质量要求（Global Constraints）

1. **命令准确性**：每条命令必须来自官方文档（`website-docs/01-getting-started/02-installation.md`、
   README.md、docker-compose.yml 实测）或本次实测（SSH 探测、hub API 实证）；不写推测命令
2. **自包含性**：执行者不依赖本会话任何上下文；所有预期输出、判定阈值、错误表现写全
3. **版本锚定**：v0.8.0 全文档一致；注明数据快照日期 2026-09-16
4. **事实核对**：首次注册模式、.env 默认值、profile 名称、端口号均以 `/tmp/weknora-deepdive`
   （main≈v0.8.0）源码为准
5. 文档内不出现内部研究术语（SVO、Agent ID、证据分级等）

## 6. 测试（只产出文档，不实测安装）

1. **命令逐条复核**：每条命令对照官方文档/源码出处核对（grep 验证）
2. **事实核对清单**：端口号、profile 名、env 变量名、版本号逐项 grep 源码验证
3. **自包含性自检**：假设"执行者零上下文"通读全文档，检查是否有未解释的依赖
4. **静态检查**：8 节齐全、无占位符、无推测命令

## 7. 范围边界

- 包含：上述唯一交付物文档
- 不包含：在 ECS 上实际执行安装（用户另行会话执行）、本机安装、模型 API Key 配置、安全组操作（文档仅提示）
