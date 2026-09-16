# WeKnora 安装方案（阿里云 ECS · ARM64）

- 版本锚定：WeKnora v0.8.0
- 环境快照日期：2026-09-16
- 目标机器：10.17.21.95（Ubuntu 22.04.5 LTS，aarch64）
- 部署形态：Docker Compose 标准集（7 容器：默认 5 + neo4j GraphRAG + minio 对象存储）
- 适用读者：零上下文执行者；每步附预期输出，可对照判定

> 本方案的每条命令均经过官方源码/文档或实机探测验证。执行前请先按 §1 复核环境。

---

## 1. 环境前提

### 1.1 环境快照（2026-09-16 实测）

| 项 | 实测值 |
|----|--------|
| OS | Ubuntu 22.04.5 LTS |
| 架构 | aarch64（ARM64） |
| CPU / 内存 | 8 核 / 15GB |
| 磁盘 | 系统盘 vda1 29GB（26GB 可用）；数据盘 vdb 100GB 挂载于 /data（80GB 可用，fstab 持久挂载） |
| Docker | 未安装 |
| 端口 | 80/8080/7474/7687/9000/9001 全部空闲 |
| GitHub | 可达（HTTP 200） |
| Docker Hub | 直连超时，必须配置镜像加速器 |

### 1.2 执行前复核命令（环境可能已变化，务必重跑）

```bash
nproc                          # 预期: 8
free -h                        # 预期: Mem total 15Gi
df -h /data                    # 预期: /dev/vdb 98G，Avail ≥ 20G
lsblk                          # 确认 vdb 挂载在 /data
ss -tlnp | grep -E ':(80|8080|7474|7687|9000|9001)\b'   # 预期: 无输出（端口空闲）
docker --version               # 预期: command not found（未安装）
curl -sI -m 8 https://github.com | head -1              # 预期: HTTP/2 200
curl -sI -m 8 https://registry-1.docker.io/v2/          # 预期: 超时或 401（拉镜像走加速器即可）
```

### 1.3 判定阈值

| 项 | 阈值 | 不满足时 |
|----|------|---------|
| CPU | ≥ 4 核 | 停用 neo4j 的最小集仍可跑（见 §8.3） |
| 内存 | ≥ 8GB | 同上，最小集约需 4GB |
| 数据盘 /data | 可用 ≥ 20GB | 先清理或扩容数据盘 |
| 端口 80/8080 | 空闲 | 修改 .env 端口（见 §8.4） |

---

## 2. 安装 Docker

### 2.1 官方脚本安装（自动识别 arm64）

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

退出并重新登录（或执行 `newgrp docker`）使 docker 组生效，然后验证：

```bash
docker --version         # 预期: Docker version 27.x 或 28.x
docker compose version   # 预期: Docker Compose version v2.x
```

### 2.2 配置镜像加速器 + 数据盘 data-root（关键，缺一不可）

国内 ECS 直连 Docker Hub 超时，必须配加速器；镜像约 5-8GB，数据根改到数据盘：

```bash
sudo mkdir -p /data/docker
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": ["https://<你的专属加速器地址>.mirror.aliyuncs.com"],
  "data-root": "/data/docker"
}
EOF
sudo systemctl restart docker
```

**加速器地址获取**（任选其一）：
- 阿里云控制台 → 容器镜像服务 ACR → 镜像工具 → 镜像加速器 → 复制专属地址（本机是阿里云 ECS，推荐）
- 公共加速源：`https://docker.m.daocloud.io`（DaoCloud，临时可用）

```bash
docker run --rm hello-world   # 预期: 输出 "Hello from Docker!" 即加速器生效
```

> 警告：/data 下已有 14GB 既有内容。本方案只新建 `/data/docker` 与 `/data/WeKnora` 两个目录，**不要触碰 /data 下其他任何目录**。

---

## 3. 镜像架构复核（ARM64 专项）

### 3.1 arm64 支持清单（docker hub API 实证，2026-09-16）

| 镜像 | arm64 |
|------|-------|
| paradedb/paradedb:v0.22.2-pg17 | ✅ 已实证 |
| wechatopenai/weknora-app:v0.8.0 | ✅ 已实证 |
| wechatopenai/weknora-docreader:v0.8.0 | ✅ 已实证 |
| wechatopenai/weknora-ui:v0.8.0 | ✅ 已实证 |
| redis:7.0-alpine | ✅ 已实证 |
| qdrant/qdrant:v1.16.2 | ✅ 已实证（备用检索引擎） |
| neo4j:2025.10.1 | 官方多架构发布，安装后复核 |
| quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z | ✅ 已实证（quay.io 源；Docker Hub 的 minio/minio 自 2025-10-23 起停发免费镜像，不可再用） |

### 3.2 复核命令（在能直连 Docker Hub 的机器上执行）

> `docker manifest inspect` 不走 registry-mirrors（moby 已知行为），在 ECS（直连超时）上执行必失败。
> 建议在个人电脑（可科学上网）上执行复核；在 ECS 上跳过本步，直接进入 §5 的 pull——架构不符会明确报错。

```bash
docker manifest inspect --verbose neo4j:2025.10.1 | grep -E '"architecture"|"variant"' | head -4
docker manifest inspect --verbose quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z | grep -E '"architecture"|"variant"' | head -4
# 预期: 输出中包含 "architecture": "arm64"
```

### 3.3 无 arm64 镜像时的处理

- 错误表现：拉取时提示 `no matching manifest for linux/arm64/v8 in the manifest list entries`
- 处理：将镜像 tag 换成其多架构版本（neo4j 换 `2025.10` 系列相邻 tag；minio 仅能从 quay.io 获取，换 `RELEASE.` 系列相邻 tag），或改用已验证的 qdrant 作为检索引擎（修改 .env 中的向量库配置）
---

## 4. 拉取源码与配置

### 4.1 目录准备（安装位置在数据盘）

```bash
sudo mkdir -p /data/WeKnora
sudo chown $USER:$USER /data/WeKnora
# 预期: 无报错即成功（命令成功时静默无输出）
```

### 4.2 clone 源码并固定版本

```bash
git clone https://github.com/Tencent/WeKnora.git /data/WeKnora
cd /data/WeKnora
git log --oneline -1        # 预期: main 分支最新提交
cp .env.example .env
sed -i 's/^WEKNORA_VERSION=.*/WEKNORA_VERSION=v0.8.0/' .env
grep WEKNORA_VERSION .env   # 预期: WEKNORA_VERSION=v0.8.0
```

### 4.3 .env 配置说明

- **模型不预配**：LLM / Embedding / Rerank 全部保持注释状态（默认值），启动后在 Web UI 配置（见 §7）
- `OLLAMA_OPTIONAL=true` 已默认：本机无 Ollama 时不阻断启动，仅告警
- 其余全部保持默认值即可

### 4.4 磁盘预算

| 占用 | 位置 | 约 |
|------|------|-----|
| 源码 | /data/WeKnora | ~200MB |
| Docker 镜像 | /data/docker | 5-8GB |
| 数据卷 | /data/docker/volumes | 按知识库规模 |

安装后可随时查看：`docker system df`

### 4.5 创建 minio 镜像源 override（必做）

Docker Hub 的 minio/minio 镜像自 2025-10-23 起停发免费版，官方 compose 中的该镜像已不可拉取。
创建 `docker-compose.override.yml`（compose 自动加载，官方文件保持原样，升级不冲突）：

```bash
cd /data/WeKnora
cat > docker-compose.override.yml <<'EOF'
services:
  minio:
    image: quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z
EOF
cat docker-compose.override.yml   # 预期: 显示上面 3 行内容
```

> 注意：quay.io 不走 §2.2 配置的 Docker Hub 加速器。若 ECS 直连 quay.io 失败，见 §8.1。

---

## 5. 启动服务（标准集 7 容器）

### 5.1 拉取镜像并启动

```bash
cd /data/WeKnora
docker compose --profile neo4j --profile minio pull
docker compose --profile neo4j --profile minio up -d
```

- minio 镜像走 quay.io（不受 §2.2 加速器影响），其余镜像走加速器
- 首次拉取约 5-8GB（走加速器，时长取决于带宽）
- 首次启动含数据库自动迁移（AUTO_MIGRATE=true 默认），等待 1-2 分钟

### 5.2 预期容器清单

| 容器 | 端口 | 说明 |
|------|------|------|
| WeKnora-frontend | 80 | Web UI |
| WeKnora-app | 8080 | 后端 API |
| WeKnora-docreader | （内部 gRPC 50051） | 文档解析 |
| WeKnora-postgres | （内部 5432） | ParadeDB pg17 |
| WeKnora-redis | （内部 6379） | 任务队列 |
| WeKnora-neo4j | 7474 / 7687 | GraphRAG 知识图谱 |
| WeKnora-minio | 9000 / 9001 | 对象存储 |

---

## 6. 启动验证与首次注册

### 6.1 健康检查

```bash
docker compose ps                        # 预期: 7 个容器均为 Up
curl -s http://localhost:8080/health     # 预期: {"status":"ok"}
curl -sI http://localhost | head -1      # 预期: HTTP/1.1 200
```

若 app 未就绪：`docker compose logs app --tail 30` 观察迁移与启动日志（特征：数据库迁移完成并出现 `Server is running at` 监听 8080；默认 `GIN_MODE=release` 不打印 GIN 逐条路由注册日志）。

### 6.2 浏览器访问

- 内网直接访问：`http://10.17.21.95`
- 若 ECS 配置了安全组，需在阿里云控制台放行 **80** 与 **8080** 端口（仅内网使用则无需放行公网）
- 首次打开约需几秒加载前端资源

### 6.3 首次注册

- v0.7.0 起为自助注册模式（`WEKNORA_TENANT_SELF_SERVICE_CREATION_ENABLED=true` 默认）：打开页面 → 注册账号 → 自动创建个人空间，无需默认密码
- 若注册入口未出现：检查 app 日志中租户初始化相关输出，或确认 .env 中 `WEKNORA_AUTH_DEFAULT_TENANT_MODE` 为默认 `create_personal`

### 6.4 冒烟测试（未配模型时的最小验证）

登录后创建知识库、上传一个 TXT 文档，验证：文档解析成功（状态变"已完成"）。此时未配模型，向量化与问答尚不可用——继续 §7 配置模型。

---

## 7. 模型配置（启动后，Web UI 内完成）

### 7.1 需要配置什么

| 模型类型 | 是否必需 | 说明 |
|---------|---------|------|
| LLM（对话生成） | 问答必需 | 未配置时仅可管理文档，无法问答 |
| Embedding（向量化） | 文档入库必需 | 上传文档前必须配好，否则无法向量化 |
| Rerank（重排） | 可选 | 显著提升检索精度，建议配置 |

### 7.2 常见厂商接入表（OpenAI 兼容 API）

| 厂商 | LLM 可用 | Embedding 可用 | base_url 示例 |
|------|---------|---------------|--------------|
| Kimi（月之暗面） | ✅ | ❌ 无 Embedding API | https://api.moonshot.cn/v1 |
| DeepSeek | ✅ | ❌ 无 Embedding API | https://api.deepseek.com |
| 智谱 GLM | ✅ | ✅（embedding-3） | https://open.bigmodel.cn/api/paas/v4 |
| 硅基流动 | ✅ | ✅（BAAI/bge-m3） | https://api.siliconflow.cn/v1 |

- 模型名以厂商当前文档为准（更新快，勿照搬旧文档）
- API Key 在对应厂商开放平台注册账号后获取（表中 base_url 与 API Key 须来自同一厂商）
- 常见组合示例：LLM=DeepSeek + Embedding=智谱 embedding-3；或 LLM=Kimi + Embedding=硅基流动 bge-m3
- 配置入口在登录后的模型管理界面（界面文案以实际版本为准），填入 API Key、base_url、模型名后测试连通

### 7.3 配置验证

1. 上传一个含明确答案的小文档（如 3 段的产品说明）
2. 提问文档内容相关问题，预期：回答正确且带引用来源
3. 提问文档外问题，预期：能识别"文档中未找到"（拒答比瞎编好）

---

## 8. 故障排查与维护

### 8.1 镜像拉取超时/失败

1. 检查加速器：`docker info | grep -A5 "Registry Mirrors"`（预期显示你配置的加速地址）
2. 若使用阿里云专属地址失败，daemon.json 中换 `https://docker.m.daocloud.io` 后 `sudo systemctl restart docker`
3. 部分大镜像（docreader 约 2GB+）建议夜间/错峰拉取
4. quay.io（minio 镜像源）拉取失败时：在可访问 quay.io 的机器上 `docker pull quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z` 后 `docker save`/`docker load` 导入 ECS；或为 quay.io 配置 HTTP 代理后重启 docker

### 8.2 启动失败排查

```bash
docker compose ps                  # 哪个容器非 Up 状态
docker compose logs <服务名> --tail 50   # 服务名=app/frontend/docreader/postgres/redis/neo4j/minio（§5.2 容器名的 WeKnora- 前缀去掉）
```

常见：postgres 迁移失败（.env 密码被改过）→ 仅当数据卷仍以默认密码初始化时，恢复默认 `DB_PASSWORD=postgres123!@#` 后重建 `docker compose up -d --force-recreate postgres`；若数据卷密码早已变过，需按 postgres 官方流程重置（另查资料）。

### 8.3 内存不足 → 降级最小集

```bash
docker compose --profile neo4j --profile minio down
docker compose up -d                # 最小集 5 容器，无 GraphRAG/对象存储
```

最小集约需 4GB 内存；恢复标准集再带 profile 启动即可。

### 8.4 端口冲突

编辑 `/data/WeKnora/.env`：

```
FRONTEND_PORT=8082     # 前端改端口
APP_PORT=8083          # 后端改端口
```

然后 `docker compose up -d` 重建，访问 `http://10.17.21.95:8082`。

### 8.5 磁盘空间

```bash
docker system df                    # 镜像/容器/卷占用总览
docker system prune -a              # 清理无用镜像（运行中的不受影响）
```

Docker 数据均在 /data/docker，源码在 /data/WeKnora，全部落在数据盘 80GB 预算内。

### 8.6 安全加固（生产使用前必读）

依据 2026-09 选型研究结论：

1. **保持最新版**：2026 年披露的 7 个 CVE（含 2 个 CVSS 9.9）均已在 ≤v0.7.0 版本修复；生产务必使用 ≥v0.7.0 的最新版（本方案锚定 v0.8.0）并跟踪新版本
2. **公网暴露时**：关闭开放注册（.env 设 `WEKNORA_TENANT_SELF_SERVICE_CREATION_ENABLED=false`），防止注册滥用
3. **MCP 面最小化**：不用的 MCP 工具与 IM 通道不配置；出口流量过滤
4. 仅内网使用时，安全组不要放行公网入站

### 8.7 升级与数据备份

```bash
cd /data/WeKnora
docker compose down
# 备份数据卷（postgres 与 minio 是关键）：
sudo tar czf /data/weknora-backup-$(date +%Y%m%d).tar.gz \
  /data/docker/volumes/weknora_postgres-data \
  /data/docker/volumes/weknora_minio_data
sed -i 's/^WEKNORA_VERSION=.*/WEKNORA_VERSION=vX.Y.Z/' .env   # X.Y.Z 换成目标新版本（先看 release notes）
git pull
docker compose --profile neo4j --profile minio pull && docker compose --profile neo4j --profile minio up -d
```

- 卷目录名以 `docker compose config --volumes` 实际输出为准（WeKnora- 前缀可能随 compose 项目名变化）
- 升级前必看 release notes 的 Breaking Change（v0.8.0 起移除本地沙箱后端等）

---

> 方案结束。安装成功后建议：按研究报告 §8 实测清单构建 golden dataset 做检索质量对照测试。
