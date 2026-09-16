# WeKnora ECS 安装方案文档 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 产出一份自包含的 WeKnora ECS 安装方案文档（8 节），用户可带到另一台机器/会话照着执行安装。

**Architecture:** 单一内容文档交付物。文档 8 节覆盖：环境前提 → 装 Docker（含加速器+数据盘 data-root）→ ARM64 镜像复核 → 拉取源码 → 启动标准集 → 验证与首次注册 → 模型配置 → 故障排查与维护。所有命令与事实均出自官方源码/文档或本次实测（SSH 探测、docker hub API 实证），禁止推测命令。

**Tech Stack:** 无代码。内容产出 + grep 事实核对。

## Global Constraints

1. 交付物唯一：`_bmad-output/research-projects/RF-20260915-knowledge-base/06-final-deliverables/WeKnora安装方案.md`（该目录被 .gitignore 忽略，提交需 `git add -f`，仓库先例）
2. 命令准确性：每条命令必须来自官方文档（`/tmp/weknora-deepdive` 的 README/website-docs/docker-compose.yml/.env.example）、源码实证（router.go /health 端点）、或本次实测（ECS SSH 探测、hub API）；不写推测命令
3. 自包含性：执行者零上下文可照做；所有预期输出、判定阈值、错误表现写全
4. 版本锚定：`WEKNORA_VERSION=v0.8.0` 全文档一致；数据快照日期 2026-09-16
5. 磁盘约束：安装位置 `/data/WeKnora`、Docker 数据根 `/data/docker`；/data 已有 14GB 既有内容，文档须明确"不得触碰 /data 下其他目录"
6. 文档内不出现内部研究术语（SVO、Agent ID、证据分级等）
7. 不触碰 `_bmad/bmb/` 下用户未提交修改（不 cd 进去、不运行 git 操作）

---

### Task 1: 文档骨架 + 第 1-3 节（环境前提/安装 Docker/镜像架构复核）

**Files:**
- Create: `_bmad-output/research-projects/RF-20260915-knowledge-base/06-final-deliverables/WeKnora安装方案.md`

**Interfaces:**
- Consumes: 无（首个任务）
- Produces: 文档标题区（含日期/版本锚定）+ §1 环境前提 + §2 安装 Docker + §3 镜像架构复核；后续任务续写 §4-§8

- [ ] **Step 1: 创建文档骨架与标题区**

写入文件开头的全部内容（逐字）：

```markdown
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
```

- [ ] **Step 2: 文档事实自检（Task 1 范围）**

逐项核对刚写入的 §1-§3 内容：

```bash
grep -n "v0.8.0" "/Users/gourouhundun/Documents/01_工作/研究课题/研究组团器/Research_Team_Assembler/_bmad-output/research-projects/RF-20260915-knowledge-base/06-final-deliverables/WeKnora安装方案.md" | head -3
```

验证要点：
1. 端口清单 80/8080/7474/7687/9000/9001 与 compose 实证一致（frontend `${FRONTEND_PORT:-80}`、app `${APP_PORT:-8080}`、neo4j `7474/7687`、minio `${MINIO_PORT:-9000}`+`${MINIO_CONSOLE_PORT:-9001}`）
2. arm64 清单表与 hub API 实证结果一致（8 项 ✅，neo4j/minio 标"复核"）
3. 无占位符（"你的专属加速器地址"是用户填写位，非占位符；`<...>` 尖括号标注用户操作位）

- [ ] **Step 3: Commit**

```bash
cd "/Users/gourouhundun/Documents/01_工作/研究课题/研究组团器/Research_Team_Assembler"
git add -f "_bmad-output/research-projects/RF-20260915-knowledge-base/06-final-deliverables/WeKnora安装方案.md"
git commit -m "docs(install-guide): WeKnora安装方案 §1-§3(环境前提/装Docker+加速器/镜像复核)"
```

---

### Task 2: 文档第 4-6 节（拉取源码/启动服务/启动验证）

**Files:**
- Modify: `_bmad-output/research-projects/RF-20260915-knowledge-base/06-final-deliverables/WeKnora安装方案.md`（在 §3 末尾追加 §4-§6）

**Interfaces:**
- Consumes: Task 1 的文档标题区与 §1-§3（含端口号、加速器配置、/data 目录约定）
- Produces: §4 拉取源码与配置 + §5 启动服务 + §6 启动验证与首次注册；供 Task 3 续写 §7-§8

- [ ] **Step 1: 追加第 4 节（拉取源码与配置）**

在文档 §3 末尾追加（逐字）：

```markdown
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
```

- [ ] **Step 2: 文档事实自检（Task 2 范围）**

验证要点：
1. 容器名清单与 compose 实证一致：`grep -n "container_name" /tmp/weknora-deepdive/docker-compose.yml | head -8` → WeKnora-frontend/WeKnora-app/WeKnora-docreader/WeKnora-postgres/WeKnora-redis/WeKnora-neo4j/WeKnora-minio
2. profile 名拼写 neo4j/minio 与 compose 一致：`grep -c "neo4j" /tmp/weknora-deepdive/docker-compose.yml`
3. `/health` 返回体 `{"status":"ok"}` 与源码一致（router.go 实证）
4. `AUTO_MIGRATE`、`OLLAMA_OPTIONAL=true`、`WEKNORA_AUTH_DEFAULT_TENANT_MODE=create_personal` 均已在 compose/.env.example 中实证

- [ ] **Step 3: Commit**

```bash
cd "/Users/gourouhundun/Documents/01_工作/研究课题/研究组团器/Research_Team_Assembler"
git add -f "_bmad-output/research-projects/RF-20260915-knowledge-base/06-final-deliverables/WeKnora安装方案.md"
git commit -m "docs(install-guide): WeKnora安装方案 §4-§6(源码/启动/验证与注册)"
```

---

### Task 3: 文档第 7-8 节（模型配置/故障排查与维护）

**Files:**
- Modify: `_bmad-output/research-projects/RF-20260915-knowledge-base/06-final-deliverables/WeKnora安装方案.md`（在 §6 末尾追加 §7-§8）

**Interfaces:**
- Consumes: Task 2 的 §4-§6（注册流程、.env 默认值、容器清单）
- Produces: §7 模型配置 + §8 故障排查与维护；文档全 8 节完成

- [ ] **Step 1: 追加第 7 节（模型配置）**

在文档 §6 末尾追加（逐字）：

```markdown
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
- 常见组合示例：LLM=DeepSeek + Embedding=智谱 embedding-3；或 LLM=Kimi + Embedding=硅基流动 bge-m3
- 配置入口在登录后的模型管理界面（界面文案以实际版本为准），填入 API Key、base_url、模型名后测试连通

### 7.3 配置验证

1. 上传一个含明确答案的小文档（如 3 段的产品说明）
2. 提问文档内容相关问题，预期：回答正确且带引用来源
3. 提问文档外问题，预期：能识别"文档中未找到"（拒答比瞎编好）
```

- [ ] **Step 2: 追加第 8 节（故障排查与维护）**

继续追加（逐字）：

```markdown
---

## 8. 故障排查与维护

### 8.1 镜像拉取超时/失败

1. 检查加速器：`docker info | grep -A5 "Registry Mirrors"`（预期显示你配置的加速地址）
2. 若使用阿里云专属地址失败，daemon.json 中换 `https://docker.m.daocloud.io` 后 `sudo systemctl restart docker`
3. 部分大镜像（docreader 约 2GB+）建议夜间/错峰拉取

### 8.2 启动失败排查

```bash
docker compose ps                  # 哪个容器非 Up 状态
docker compose logs <容器名> --tail 50   # 看该容器日志
```

常见：postgres 迁移失败（.env 密码被改过）→ 恢复默认 `DB_PASSWORD=postgres123!@#` 后重建 `docker compose up -d --force-recreate postgres`。

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

1. **保持最新版**：v0.8.0 之前版本存在已披露 CVE（含 2 个 CVSS 9.9），务必使用 v0.8.0 并跟踪新版本
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
git pull
docker compose --profile neo4j --profile minio pull && docker compose --profile neo4j --profile minio up -d
```

- 卷目录名以 `docker compose config --volumes` 实际输出为准（WeKnora- 前缀可能随 compose 项目名变化）
- 升级前必看 release notes 的 Breaking Change（v0.8.0 起移除本地沙箱后端等）

---

> 方案结束。安装成功后建议：按研究报告 §8 实测清单构建 golden dataset 做检索质量对照测试。
```

- [ ] **Step 3: 文档事实自检（Task 3 范围）**

验证要点：
1. 厂商 base_url 三处均为公开常识（moonshot/deepseek/bigmodel/siliconflow 官方域名），模型名用"以厂商文档为准"规避时效风险
2. 默认 DB_PASSWORD 与 .env.example 实证一致：`grep "^DB_PASSWORD" /tmp/weknora-deepdive/.env.example` → postgres123!@#
3. CVE 结论与研究报告一致（7 个 CVE 含 2 个 CVSS 9.9，≥v0.7.0 修复）
4. 备份命令的卷名写明了"以 docker compose config --volumes 实际输出为准"，不虚构卷全名
5. 全文无内部研究术语（grep 检查：`grep -nE "SVO|Agent ID|证据分级|元素提取" 文档` 无输出）

- [ ] **Step 4: Commit**

```bash
cd "/Users/gourouhundun/Documents/01_工作/研究课题/研究组团器/Research_Team_Assembler"
git add -f "_bmad-output/research-projects/RF-20260915-knowledge-base/06-final-deliverables/WeKnora安装方案.md"
git commit -m "docs(install-guide): WeKnora安装方案 §7-§8(模型配置/故障排查与维护) 全8节完成"
```

---

### Task 4: 整文档终检

**Files:**
- Verify: `_bmad-output/research-projects/RF-20260915-knowledge-base/06-final-deliverables/WeKnora安装方案.md`

**Interfaces:**
- Consumes: Task 1-3 完成的 8 节全文
- Produces: 终检通过并最终提交

- [ ] **Step 1: 结构性终检**

```bash
DOC="/Users/gourouhundun/Documents/01_工作/研究课题/研究组团器/Research_Team_Assembler/_bmad-output/research-projects/RF-20260915-knowledge-base/06-final-deliverables/WeKnora安装方案.md"
grep -c "^## " "$DOC"        # 预期: 8（8 个二级标题节）
grep -n "^## " "$DOC"        # 预期顺序: 1环境前提 2安装Docker 3镜像架构 4拉取源码 5启动 6验证 7模型配置 8故障排查
wc -l "$DOC"
```

- [ ] **Step 2: 事实终检（全部 grep 验证一次跑完）**

```bash
# 版本锚定一致
grep -c "v0.8.0" "$DOC"                       # 预期: ≥3
# 无占位符残留
grep -nE "TBD|TODO|待补充|implement later" "$DOC"    # 预期: 无输出
# 无内部研究术语
grep -nE "SVO|Agent ID|证据分级|元素提取|置信度" "$DOC"  # 预期: 无输出
# 命令出处复核（每条 shell 命令必须出现在官方文档或本次实测中）
grep -n "get.docker.com\|docker compose --profile\|git clone https://github.com/Tencent/WeKnora\|manifest inspect\|WEKNORA_VERSION" "$DOC" | head -10
```

- [ ] **Step 3: 自包含性通读自检**

以"执行者零上下文"角色通读全文，逐条确认：
1. 每个命令块都有预期输出或判定方法
2. 每处用户需自己填的值（加速器地址、API Key）都有获取说明
3. 每处"以实际为准"的表述（模型名、卷名、UI 文案）都有验证命令或说明原因
4. §1-§8 前后引用一致（端口、目录、版本号无矛盾）

发现问题直接修复并重新跑 Step 1-2 检查。

- [ ] **Step 4: 最终提交（含 spec/plan 一致性）**

```bash
cd "/Users/gourouhundun/Documents/01_工作/研究课题/研究组团器/Research_Team_Assembler"
git add -f "_bmad-output/research-projects/RF-20260915-knowledge-base/06-final-deliverables/WeKnora安装方案.md"
git commit -m "docs(install-guide): WeKnora安装方案终检通过(8节完整/命令全部有出处/自包含)"
```

---

## Self-Review 记录（计划作者执行）

1. **Spec coverage**：spec §4 的 8 节内容要求 → Task 1（§1-3）/Task 2（§4-6）/Task 3（§7-8）全覆盖；spec §5 质量要求 → Global Constraints 1-6 逐条对应；spec §6 测试要求 → 各任务自检 Step + Task 4 终检；spec §7 范围边界 → 交付物唯一，无越界任务 ✅
2. **Placeholder scan**：文档内容全部逐字给出，无 TBD/TODO；`<你的专属加速器地址>` 是显式标注的用户填写位 ✅
3. **Type consistency**：端口 80/8080/7474/7687/9000/9001、目录 /data/WeKnora 与 /data/docker、版本 v0.8.0 在四个任务间一致 ✅
