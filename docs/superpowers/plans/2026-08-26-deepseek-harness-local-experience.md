# DeepSeek Harness 本机安装体验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本机用 npx 启动 `@deepseek-ai/dsh web`（v0.1.1-rc.2），配好模型并实测一轮真实 Agent 对话，把 Web UI 交给用户体验。

**Architecture:** npx 直跑官方 npm 包（已缓存验证可用）；模型配置双轨——轨道 1 复用用户当前 settings.json 的 kimi 中转（pi-ai 适配器 `anthropic-messages` 协议自定义路由），轨道 2 兜底 DeepSeek 官方 key（`llm-deepseek` 原生适配器）。

**Tech Stack:** Node v24.15.0 / npm 11.12.1（已验证）、`@deepseek-ai/dsh@0.1.1-rc.2`、Playwright MCP（UI 验证）

## Global Constraints

- **密钥零落盘到仓库**：apiKey 只进 `~/.dsh/.env` / `~/.dsh/.credentials.yaml` / dsh UI 凭据存储；绝不写入本仓库任何文件
- **不修改用户现有 settings.json**（`~/.claude/settings.json*` 只读）
- dsh 必须从专用空目录 `~/dsh-playground` 启动（dsh 把调用目录作为默认 workspace 根，绝不能从本仓库启动）
- 服务端口固定 **8310**（被占则 8311、8312 顺延）
- 启动必须带 `--no-open`（浏览器由我们控制）
- npx 包已缓存在 `~/.npm/_npx/b86ed90107c62dab`，重复调用不会重新下载
- 本计划为运维操作，无仓库代码变更；除计划文档本身外无需 git commit

## 侦察已确认的事实（执行者无需重新发现）

- CLI：`dsh web [--host] [--port] [--no-open] [--trusted-host]`；版本 0.1.1-rc.2
- `$DSH_HOME` 默认 = `~/.dsh`；web profile 首启自动初始化到 `~/.dsh/profiles/web`
- 凭据存储：`~/.dsh/.credentials.yaml`（可写）+ `~/.dsh/.env`（只读兜底）
- 默认模型配置（`agent-default-model`）：`provider: deepseek-official`，`model: deepseek-v4-flash`
- `llm-pi-ai` 配置 schema：`Config = { providers: dict(profile) }`，profile 字段：
  `api`（`anthropic-messages`/`openai-completions`/`openai-responses`）、`baseURL`、`apiKeyEnv`（credential-ref，从凭据存储/.env 解析）、`displayName`、`models: [{id, name?, contextWindow?, maxTokens?, input?}]`（仅 `id` 必填）
- patch 层文件：`~/.dsh/profiles/web/cordis.patch.yml`（profile 级）或 `~/.dsh/cordis.patch.yml`（home 级），条目格式 `- id: <插件id>` + `config:`（与 `dsh --profile web --dump-config` 输出同形）
- UI 有模型设置页（`dsh-client-ui-settings-models`）与模型选择器（`dsh-client-ui-model-selection`）
- web 搜索插件读 `DEEPSEEK_API_KEY` 环境变量（与轨道 2 的 key 同名，顺带激活联网搜索）

## 密钥来源（只读，执行时读取）

- 轨道 1：`~/.claude/settings.json` → `env.ANTHROPIC_AUTH_TOKEN`（kimi 中转 key）、`env.ANTHROPIC_BASE_URL` = `https://new-api.jointpilot.com/`、模型 `kimi-k3`
- 轨道 2：`~/.claude/settings.json.deepseek.bak` → `env.ANTHROPIC_AUTH_TOKEN`（DeepSeek 官方 key，sk-9836 开头）

---

### Task 1: 专用工作目录 + 后台启动 dsh web + 服务可达验证

**Files:**
- Create: `~/dsh-playground/`（空目录，dsh 的 workspace 根）
- Create: `~/.dsh/`（由 dsh 首启自动初始化，不手工建）

**Interfaces:**
- Produces: 运行中的 dsh web 服务，基址 `http://127.0.0.1:8310`；后台任务 ID 供 Task 5 停止用

- [ ] **Step 1: 确认端口空闲**

```bash
lsof -nP -iTCP:8310 -sTCP:LISTEN || echo "PORT_8310_FREE"
```
Expected: 输出 `PORT_8310_FREE`；若被占则改用 8312（8311 常见占用）并记录最终端口

- [ ] **Step 2: 建专用工作目录**

```bash
mkdir -p ~/dsh-playground && cd ~/dsh-playground && pwd
```
Expected: 输出 `/Users/gourouhundun/dsh-playground`

- [ ] **Step 3: 后台启动 dsh web**

在 `~/dsh-playground` 下用 run_in_background 执行：

```bash
cd ~/dsh-playground && npx -y @deepseek-ai/dsh@latest web --port 8310 --no-open
```
Expected: 输出流中出现监听地址（形如 `http://127.0.0.1:8310` 或 `localhost:8310`）；首启会自动初始化 `~/.dsh/profiles/web`

- [ ] **Step 4: 验证 HTTP 可达**

```bash
for i in $(seq 1 30); do code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8310/ 2>/dev/null); [ "$code" = "200" ] && echo "HTTP_OK" && break; sleep 2; done; echo "final=$code"
```
Expected: `HTTP_OK` 且 `final=200`；若 60 秒内未 200，读后台任务输出的报错再处理（常见：端口冲突→换端口重启）

### Task 2: Playwright 打开 UI + 探明模型设置界面

**Files:** 无（纯浏览器操作）

**Interfaces:**
- Consumes: Task 1 的服务基址 `http://127.0.0.1:8310`
- Produces: UI 截图；Settings→Models 页的结构认知（有哪些 provider、添加自定义 provider 的入口形态），供 Task 3 决策 UI 配置 vs patch 配置

- [ ] **Step 1: 打开 UI 并截图**

用 `browser_navigate` 打开 `http://127.0.0.1:8310`，然后 `browser_take_screenshot`（filename: `dsh-home.png`）
Expected: 页面加载出 dsh Web UI（会话/输入框界面）；若白屏，查 `browser_console_messages` level=error

- [ ] **Step 2: 探明模型设置入口**

`browser_snapshot` 找设置入口（gear 图标 / Settings / 模型选择器），点进 Settings→Models 页，截图 `dsh-settings-models.png`
Expected: 能看到 provider 列表（至少 `deepseek-official`）与"添加 provider / 编辑 baseURL / 填 apiKey"类控件。**记录**：是否支持自定义 provider 路由 + 自定义 baseURL——这决定 Task 3 走 UI 还是 patch 文件

### Task 3: 轨道 1 — kimi 中转配置 + 真实对话实测

**Files:**
- Create（仅 UI 路径不可行时）: `~/.dsh/profiles/web/cordis.patch.yml`
- Modify（仅 patch 路径）: `~/.dsh/.env`

**Interfaces:**
- Consumes: Task 2 的 UI 结构认知；`~/.claude/settings.json` 的 key/baseURL/model
- Produces: 可用模型路由 `kimi-relay` / 模型 `kimi-k3`；一轮真实对话成功截图

- [ ] **Step 1: 读取轨道 1 凭据**

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/settings.json'))['env']; print(d['ANTHROPIC_BASE_URL']); print(d['ANTHROPIC_AUTH_TOKEN'][:8]+'...'); print(d['ANTHROPIC_MODEL'])"
```
Expected: `https://new-api.jointpilot.com/`、`sk-AFxuF1...`、`kimi-k3`

- [ ] **Step 2a（首选，UI 路径）: 在 Settings→Models 添加自定义 provider**

按 Task 2 探明的 UI 形态操作：新增 provider，协议选 Anthropic（`anthropic-messages`），baseURL 填 `https://new-api.jointpilot.com`（去掉尾部斜杠），apiKey 填轨道 1 token，模型加 `kimi-k3`；保存后把它选为当前模型（模型选择器）
Expected: provider 保存成功无报错 → 跳到 Step 4

- [ ] **Step 2b（兜底，patch 路径）: 写 patch 层 + .env**

仅当 UI 不支持自定义 provider/baseURL 时执行：

```bash
mkdir -p ~/.dsh
cat > ~/.dsh/.env <<'EOF'
DSH_KIMI_RELAY_KEY=<粘贴轨道1的完整token>
EOF
chmod 600 ~/.dsh/.env
cat > ~/.dsh/profiles/web/cordis.patch.yml <<'EOF'
# 轨道1: kimi 中转（Anthropic 协议）经 pi-ai 适配器
- id: llm-pi-ai
  name: '@deepseek-ai/dsh-llm-pi-ai'
  config:
    providers:
      kimi-relay:
        api: anthropic-messages
        baseURL: https://new-api.jointpilot.com
        apiKeyEnv: DSH_KIMI_RELAY_KEY
        displayName: Kimi (relay)
        models:
          - id: kimi-k3
            contextWindow: 262144
            maxTokens: 32768
- id: agent-default-model
  name: '@deepseek-ai/dsh-agent-default-model'
  config:
    provider: kimi-relay
    model: kimi-k3
EOF
```
然后停掉 Task 1 的后台任务并用同命令重启（patch 层在 boot 时叠加）
Expected: 重启后服务恢复 200；`npx -y @deepseek-ai/dsh@latest --profile web --dump-config | grep -A3 kimi-relay` 能看到路由已并入配置树

- [ ] **Step 3: 验证路由生效（仅 patch 路径需要）**

```bash
cd ~/dsh-playground && npx -y @deepseek-ai/dsh@latest --profile web --dump-config 2>/dev/null | grep -B1 -A8 "kimi-relay"
```
Expected: 输出含 `kimi-relay` 路由与 `baseURL: https://new-api.jointpilot.com`

- [ ] **Step 4: 实测一轮真实对话**

Playwright：回到主页 → 新建会话 → 输入框发送 `用一句话介绍你自己` → 等待回复 → 截图 `dsh-chat-kimi.png`
Expected: 60 秒内收到模型真实回复（非错误提示）。若报错（401/404/协议不符），把错误原文记入结果，转 Task 4

### Task 4: 轨道 2 兜底 — DeepSeek 官方 key + 真实对话实测

> 仅当 Task 3 Step 4 失败时执行；Task 3 成功则本任务整体跳过并在结果中注明。

**Files:**
- Modify: `~/.dsh/.env`（追加 DEEPSEEK_API_KEY）或 UI 凭据存储

**Interfaces:**
- Consumes: `~/.claude/settings.json.deepseek.bak` 的 key
- Produces: provider `deepseek-official` 可用；一轮真实对话成功截图

- [ ] **Step 1: 读取轨道 2 key 并写入 dsh 环境**

```bash
KEY=$(python3 -c "import json; print(json.load(open('$HOME/.claude/settings.json.deepseek.bak'))['env']['ANTHROPIC_AUTH_TOKEN'])")
touch ~/.dsh/.env && chmod 600 ~/.dsh/.env
grep -q DEEPSEEK_API_KEY ~/.dsh/.env 2>/dev/null || echo "DEEPSEEK_API_KEY=$KEY" >> ~/.dsh/.env
```
Expected: `~/.dsh/.env` 含 DEEPSEEK_API_KEY 行（权限 600）

- [ ] **Step 2: 恢复默认模型并重启服务**

若 Task 3 走过 patch 路径：把 `~/.dsh/profiles/web/cordis.patch.yml` 中 `agent-default-model` 段改回（或整文件删除——默认即 `deepseek-official` + `deepseek-v4-flash`），重启 dsh web。若 Task 3 走的是 UI 路径：在模型选择器切回 `deepseek-official` / `deepseek-v4-flash` 即可，并在 Settings→Models 给 deepseek-official 填 key（此时可跳过 .env）
Expected: 服务 200；默认模型指向 deepseek-official

- [ ] **Step 3: 实测一轮真实对话**

同 Task 3 Step 4，截图 `dsh-chat-deepseek.png`
Expected: 收到真实回复。若仍失败，如实记录错误（服务保持运行，界面仍可体验）

### Task 5: 交付与收尾

**Files:** 无仓库文件变更

**Interfaces:**
- Consumes: Task 1-4 的最终状态
- Produces: 用户可自己操作的访问入口与运维说明

- [ ] **Step 1: 汇总交付信息并告知用户**

向用户报告：访问地址 `http://127.0.0.1:8310`、生效的模型轨道（kimi-relay 或 deepseek-official）、实测对话结果（成功/失败+原因）、截图文件位置

- [ ] **Step 2: 留下运维说明**

告知用户：
- 停止服务：停止本会话的后台任务，或 `pkill -f "@deepseek-ai/dsh"` 
- 日后重启：`cd ~/dsh-playground && npx -y @deepseek-ai/dsh@latest web --port 8310`
- 数据位置：`~/.dsh/`（会话、凭据、配置）；删除它即完全卸载痕迹（npx 缓存另在 `~/.npm/_npx`）

---

## Self-Review 记录

- **Spec 覆盖**：安装启动（T1)✓ 配置入口探明（T2，spec §3 步骤2)✓ 双轨配置（T3/T4)✓ 服务+UI+对话验证（T1S4/T2/T3S4)✓ 错误处理（T1S4 端口、T3S4→T4 回落、双轨均败如实报告）✓ YAGNI 约束写入 Global Constraints✓
- **占位符扫描**：Step 2b 的 `<粘贴轨道1的完整token>` 是有意的执行期注入点（密钥禁止写入计划/仓库），其余步骤均为可直接执行内容
- **一致性**：端口 8310 全篇一致；路由名 `kimi-relay`、模型 `kimi-k3`、env 名 `DSH_KIMI_RELAY_KEY` 前后一致；T4 引用的默认值与侦察事实一致
