# 设计：本机安装并体验 DeepSeek Harness（dsh）

- **日期**: 2026-08-26
- **依据**: `_bmad-output/research-projects/RF-20260825-deepseek-harness/06-final-deliverables/调研报告.md`
- **方案选择**: 方案 A（npx 直接跑），用户已批准

## 1. 目标与成功标准

在本机通过 `npx @deepseek-ai/dsh web` 启动 dsh 的 Web UI，配好模型，能真正发起一轮 Agent 对话。

**成功标准**：浏览器打开 Web UI → 创建会话 → 发一条消息 → 收到模型真实回复。

## 2. 环境前提（已核实）

- Node v24.15.0 / npm 11.12.1 / npx 已就绪
- 调研报告记录的本地源码克隆 `~/Documents/01_工作/Code/AICoding/deepseek-harness` 当前无权限访问（EPERM），本设计不依赖它——走 npm 包
- dsh 模型适配器（据调研报告）：`llm-deepseek`（DeepSeek 官方）+ `llm-pi-ai`（`@earendil-works/pi-ai`）
- dsh 含 settings/credentials 插件，模型 key 大概率可在 Web UI 内配置

## 3. 安装与启动流程

1. `npx -y @deepseek-ai/dsh@latest --help` 验证包可拉取，确认版本与命令
2. 探明模型配置入口，优先级：`dsh web --help` 的 CLI 参数 → 环境变量 → `$DSH_HOME` 配置文件 → Web UI 内 settings/credentials 页
3. 后台启动 `npx @deepseek-ai/dsh web`；默认端口被占则换端口

## 4. 模型配置（双轨）

- **轨道 1（用户指定优先）**：复用当前 `~/.claude/settings.json` 的中转配置
  - `baseURL = https://new-api.jointpilot.com/`，token 用该文件中的 `ANTHROPIC_AUTH_TOKEN`，模型 `kimi-k3`
  - 走 pi-ai 适配器的 Anthropic 兼容 provider（前提是 dsh 暴露自定义端点配置）
- **轨道 2（兜底）**：`~/.claude/settings.json.deepseek.bak` 中的 DeepSeek 官方 key，走 `llm-deepseek` 原生适配器
- 密钥只写入 dsh 自己的配置/凭据存储，不写入本仓库任何文件

## 5. 验证

- 服务层面：进程存活、端口监听、HTTP 200
- 体验层面：Playwright 打开 UI 截图确认；若模型配置在 UI 内完成，则填好 key 并实测一轮对话
- 交付：把访问地址留给用户自己体验

## 6. 错误处理

- npx 拉包失败 → 换 npm registry 镜像重试一次；仍失败则如实报告
- 轨道 1 不通（pi-ai 不接受自定义端点 / 中转协议不兼容）→ 明确告知原因，切轨道 2
- 双轨均不通 → 服务照常启动给用户看界面，模型部分如实报告卡点
- 端口冲突 → 自动换端口

## 7. 明确不做（YAGNI）

- 不全局安装、不克隆源码构建、不写插件、不动沙箱策略（默认 Seatbelt）
- 不修改用户现有任何 settings.json（只读取）
