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
| wechatopenai/weknora-app:latest | ✅ 已实证 |
| wechatopenai/weknora-docreader:latest | ✅ 已实证 |
| wechatopenai/weknora-ui:latest | ✅ 已实证 |
| redis:7.0-alpine | ✅ 已实证 |
| qdrant/qdrant:v1.16.2 | ✅ 已实证（备用检索引擎） |
| neo4j:2025.10.1 | 官方多架构发布，安装后复核 |
| minio/minio:RELEASE.2025-09-07T16-13-09Z | 官方多架构发布，安装后复核 |

### 3.2 复核命令（安装 Docker 后执行）

```bash
docker manifest inspect --verbose neo4j:2025.10.1 | grep -E '"architecture"|"variant"' | head -4
docker manifest inspect --verbose minio/minio:RELEASE.2025-09-07T16-13-09Z | grep -E '"architecture"|"variant"' | head -4
# 预期: 输出中包含 "architecture": "arm64"
```

### 3.3 无 arm64 镜像时的处理

- 错误表现：拉取时提示 `no matching manifest for linux/arm64/v8 in the manifest list entries`
- 处理：将 docker-compose.yml 中该镜像 tag 换成其多架构版本（neo4j 换 `2025.10` 系列相邻 tag；minio 换 `latest`），或改用已验证的 qdrant 作为检索引擎（修改 .env 中的向量库配置）
---

## 4. 拉取源码与配置

### 4.1 目录准备（安装位置在数据盘）

```bash
sudo mkdir -p /data/WeKnora
sudo chown $USER:$USER /data/WeKnora
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

---

## 5. 启动服务（标准集 7 容器）

### 5.1 拉取镜像并启动

```bash
cd /data/WeKnora
docker compose --profile neo4j --profile minio pull
docker compose --profile neo4j --profile minio up -d
```

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

若 app 未就绪：`docker compose logs app --tail 30` 观察迁移与启动日志（特征：GIN 路由注册与启动监听 8080）。

### 6.2 浏览器访问

- 内网直接访问：`http://10.17.21.95`
- 若 ECS 配置了安全组，需在阿里云控制台放行 **80** 与 **8080** 端口（仅内网使用则无需放行公网）
- 首次打开约需几秒加载前端资源

### 6.3 首次注册

- v0.7.0 起为自助注册模式（`WEKNORA_TENANT_SELF_SERVICE_CREATION_ENABLED=true` 默认）：打开页面 → 注册账号 → 自动创建个人空间，无需默认密码
- 若注册入口未出现：检查 app 日志中租户初始化相关输出，或确认 .env 中 `WEKNORA_AUTH_DEFAULT_TENANT_MODE` 为默认 `create_personal`

### 6.4 冒烟测试（未配模型时的最小验证）

登录后创建知识库、上传一个 TXT 文档，验证：文档解析成功（状态变"已完成"）。此时未配模型，向量化与问答尚不可用——继续 §7 配置模型。
