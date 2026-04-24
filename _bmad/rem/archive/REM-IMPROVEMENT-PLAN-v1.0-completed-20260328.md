# REM (Research Execution Module) 整改计划

**版本**: v1.0
**日期**: 2026-03-28
**状态**: ✅ 已完成

---

## 一、问题汇总

### 1.1 用户反馈的问题

| 编号 | 问题 | 严重程度 | 影响范围 |
|------|------|---------|---------|
| P1 | 缺少文字校对Agent，研究成果未经过文字校对 | 中 | 成果质量 |
| P2 | 研究成果输出结构不明确，导致空文件夹 | 高 | 框架完整性 |
| P3 | 上下文超限处理机制缺失，研究被迫停止 | 高 | 执行稳定性 |
| P4 | 缺少批判性思维Agent，无法对研究成果进行挑战 | 高 | 研究质量 |

### 1.2 分析发现的额外问题

| 编号 | 问题 | 严重程度 | 影响范围 |
|------|------|---------|---------|
| P5 | Agent超时恢复机制不完善，超时后无法自动恢复 | 高 | 执行稳定性 |
| P6 | 缺少阶段性质量门禁(Quality Gate)，无法控制研究质量 | 高 | 研究质量 |
| P7 | 研究进度追踪机制不完善，缺少定期进度报告 | 中 | 可观测性 |
| P8 | 文件架构规范与实际产出不一致，规范未被严格执行 | 中 | 框架完整性 |
| P9 | 协作日志产出不完整，验证/冲突记录未完整生成 | 中 | 可追溯性 |
| P10 | 缺少版本管理机制，无法追踪成果版本变化 | 中 | 可维护性 |
| P11 | 缺少研究暂停/恢复检查点机制 | 中 | 执行稳定性 |
| P12 | 缺少Agent输出校验机制，未验证输出完整性 | 中 | 成果质量 |

---

## 二、整改方案

### 2.1 P1: 增加文字校对Agent

**方案**: 新增 `rem-agent-editor` (文字编辑专家)

**职责**:
- 文字校对和语法检查
- 格式规范化
- 引用格式统一
- 术语一致性检查
- 可读性优化

**介入时机**:
- 每个Agent完成初稿后
- 交叉验证报告生成后
- 最终成果输出前

**实现方式**:
```yaml
# rem-agent-editor.md
name: rem-agent-editor
displayName: 文字编辑专家
role: 确保研究成果的文字质量和格式规范

capabilities:
  - 文字校对
  - 格式规范化
  - 引用检查
  - 术语一致性
  - 可读性优化

triggerPoints:
  - after: "agent-draft-complete"
  - after: "cross-validation-complete"
  - before: "final-deliverable-output"
```

**文件位置**: `_bmad/rem/agents/rem-agent-editor.md`

---

### 2.2 P2: 研究成果输出结构规范化

**方案**:
1. 定义基准版本输出规范 (v1.0 Baseline)
2. 增加输出完整性校验机制
3. 禁止创建空文件夹

**具体措施**:

#### 2.2.1 基准版本输出清单

```yaml
# baseline-output-specification.yaml
version: "1.0"
name: "研究框架基准输出规范"

requiredOutputs:
  00-meta:
    - project-config.yaml       # 必需
    - research-framework.yaml   # 必需
    - status-tracker.yaml       # 必需

  01-topic-definition:
    - topic-analysis-report.md  # 必需
    - methodology-selection-report.md # 必需

  02-literature-review:
    - literature-review-report.md # 必需

  03-research-design:
    - research-design-proposal.md # 必需

  04-agent-outputs:
    # 每个Agent必须有至少一个输出文件
    pattern: "{agent-id}/reports/*.md"
    minFilesPerAgent: 1

  05-collaboration-logs:
    - cross-validation-report.md # 必需

  06-final-deliverables:
    - comprehensive-exercise-plan-v1.0.md # 必需
    - implementation-guide.md      # 必需
    - assessment-toolkit.md        # 必需
    - final-research-report.md     # 必需

outputRules:
  - rule: "禁止创建空文件夹"
    action: "只有在有文件需要写入时才创建目录"
  - rule: "所有模板文件必须填充实际内容"
    action: "不输出占位符内容"
```

#### 2.2.2 Step-10 增强

在 `step-10-final-output.md` 中增加:
- 输出完整性检查清单
- 基准版本对照表
- 空文件夹清理步骤

---

### 2.3 P3: 上下文超限处理机制

**方案**:
1. 定义上下文使用阈值
2. 自动触发压缩机制
3. 设置阶段性检查点

**具体措施**:

#### 2.3.1 上下文监控配置

```yaml
# context-management.yaml
contextManagement:
  thresholds:
    warning: 70%    # 警告阈值
    compression: 80% # 自动压缩阈值
    critical: 90%    # 临界阈值

  actions:
    atWarning:
      - 记录当前进度
      - 提示用户即将压缩

    atCompression:
      - 自动执行/compact命令
      - 保存关键状态到文件
      - 生成恢复点

    atCritical:
      - 强制保存所有进度
      - 生成恢复文件
      - 提示用户手动压缩

  checkpointIntervals:
    - after: "step-03"  # 文献综述后
    - after: "step-06"  # 框架设计后
    - after: "phase-2"  # 独立研究后
    - after: "phase-3"  # 交叉验证后
```

#### 2.3.2 恢复点文件格式

```yaml
# recovery-point.yaml
recoveryPoint:
  id: "RP-{timestamp}"
  projectId: "RF-{project-id}"
  createdAt: "{timestamp}"

  completedSteps:
    - step: "step-01"
      status: "completed"
      outputFile: "path/to/output"
    - step: "step-02"
      status: "completed"
      outputFile: "path/to/output"

  currentStep:
    step: "step-05"
    status: "in_progress"
    progress: "60%"

  pendingSteps:
    - "step-06"
    - "step-07"

  agentStates:
    - agentId: "agent-1"
      status: "completed"
      outputLocation: "path/to/output"

  resumeInstructions:
    - "读取 recovery-point.yaml"
    - "加载 research-framework.yaml"
    - "从 step-05 继续"
```

#### 2.3.3 修改工作流

在 `workflow.md` 中增加:
```markdown
## 上下文管理

### 自动压缩触发
- 当上下文使用超过80%时，自动执行压缩
- 压缩前保存恢复点

### 手动恢复
- 用户提供 `/compact` 命令后的恢复流程
- 从 recovery-point.yaml 读取状态继续执行
```

---

### 2.4 P4: 增加批判性思维Agent

**方案**: 新增 `rem-agent-critic` (批判性审查专家)

**职责**:
- 挑战研究假设和结论
- 识别逻辑漏洞和证据不足
- 提出反例和替代解释
- 质疑方法论选择

**介入时机**:
- 交叉验证完成后
- 最终成果整合前

**与现有Agent的关系**:
- 与 `rem-agent-reviewer` (跨学科审查员) 配合
- Reviewer负责质量检查，Critic负责挑战质疑

**实现方式**:
```yaml
# rem-agent-critic.md
name: rem-agent-critic
displayName: 批判性审查专家
title: 研究挑战与质疑专家
icon: 🎯

capabilities:
  - 假设挑战
  - 逻辑漏洞识别
  - 反例构造
  - 替代解释提出
  - 方法论质疑

role: 以严谨挑剔的态度挑战研究成果，发现潜在问题

identity: |
  严谨的学术批评家，擅长发现研究中的漏洞和不足。
  不满足于表面解释，总是追问"为什么"和"凭什么"。
  以批判性思维为武器，确保研究经得起质疑。

communicationStyle: |
  直接、犀利、不留情面但建设性。
  用问题挑战假设，用反例测试结论。
  每次批评都伴随改进建议。

principles:
  - 批评是学术进步的动力
  - 好的研究应该经得起质疑
  - 发现问题是解决问题的前提
  - 严谨比速度更重要

triggerPoints:
  - after: "cross-validation-complete"
  - before: "final-integration"

outputFormat:
  type: "批判性审查报告"
  sections:
    - 假设挑战
    - 逻辑漏洞
    - 证据不足之处
    - 替代解释
    - 改进建议
```

**协作流程调整**:
```
独立研究 → 交叉验证 → 批判性审查 → 整合改进 → 最终成果
```

---

### 2.5 P5: Agent超时恢复机制

**方案**:
1. 定义Agent超时处理策略
2. 增加部分成果保存机制
3. 支持Agent重新启动

**具体措施**:

```yaml
# agent-timeout-handling.yaml
timeoutHandling:
  defaultTimeout: 300000  # 5分钟

  strategies:
    partialSave:
      enabled: true
      action: "保存已完成的部分成果"

    resume:
      enabled: true
      action: "从断点恢复执行"

    fallback:
      enabled: true
      action: "使用简化策略重新执行"

  recoveryProcess:
    - step: "检查Agent输出目录"
    - step: "读取部分成果"
    - step: "评估完成度"
    - step: "决定恢复或重试策略"
    - step: "继续执行或标记失败"
```

---

### 2.6 P6: 阶段性质量门禁

**方案**: 定义每个阶段的质量标准和通过条件

**具体措施**:

```yaml
# quality-gates.yaml
qualityGates:
  gate-01-topic-definition:
    phase: "课题定义"
    criteria:
      - criterion: "课题描述清晰完整"
        validation: "检查topic-analysis-report.md内容完整性"
      - criterion: "方法论选择有理有据"
        validation: "检查methodology-selection-report.md论证充分性"
    passAction: "进入下一阶段"
    failAction: "返回修改"

  gate-02-literature-review:
    phase: "文献综述"
    criteria:
      - criterion: "覆盖所有相关领域"
        validation: "检查domains覆盖率"
      - criterion: "引用规范"
        validation: "检查references格式"
    passAction: "进入研究设计"
    failAction: "补充文献"

  gate-03-agent-outputs:
    phase: "独立研究"
    criteria:
      - criterion: "所有Agent都有产出"
        validation: "检查每个Agent目录是否有文件"
      - criterion: "产出内容完整"
        validation: "检查报告结构完整性"
    passAction: "进入交叉验证"
    failAction: "补充缺失产出"

  gate-04-cross-validation:
    phase: "交叉验证"
    criteria:
      - criterion: "验证报告完整"
        validation: "检查validation-report存在"
      - criterion: "分歧已解决"
        validation: "检查divergence状态"
    passAction: "进入成果整合"
    failAction: "处理未解决分歧"

  gate-05-final-deliverables:
    phase: "成果输出"
    criteria:
      - criterion: "所有必需文件存在"
        validation: "检查baseline-output清单"
      - criterion: "格式规范"
        validation: "检查文件格式正确性"
    passAction: "研究完成"
    failAction: "补充缺失文件"
```

---

### 2.7 P7: 研究进度追踪机制

**方案**:
1. 增加定期进度报告
2. 可视化研究状态
3. 预警机制

**具体措施**:

```yaml
# progress-tracking.yaml
progressTracking:
  reportIntervals:
    - trigger: "step-complete"
      output: "step-progress-report.md"
    - trigger: "phase-complete"
      output: "phase-progress-report.md"
    - trigger: "daily"
      output: "daily-summary.md"

  statusDashboard:
    file: "00-meta/status-dashboard.md"
    updateFrequency: "real-time"

  alerts:
    - condition: "step-duration > expected * 2"
      action: "预警：步骤执行时间过长"
    - condition: "agent-completion-rate < 80%"
      action: "预警：Agent完成率低"
    - condition: "context-usage > 70%"
      action: "预警：上下文使用率高"
```

---

### 2.8 P8-P12: 其他整改项

#### P8: 文件架构规范强化
- 修改 `file-architecture-specification.md`，增加强制执行规则
- 在 Step-10 中增加架构校验步骤

#### P9: 协作日志完整性
- 定义协作日志最小输出要求
- 在交叉验证流程中增加日志输出检查

#### P10: 版本管理机制
```yaml
# version-control.yaml
versionControl:
  scheme: "semantic-versioning"
  initialVersion: "1.0.0"

  versionFiles:
    - "research-framework.yaml"
    - "final-deliverables/*.md"

  changeLog:
    file: "00-meta/CHANGELOG.md"
    format: "Keep a Changelog"
```

#### P11: 暂停/恢复检查点
- 在每个Phase结束时设置检查点
- 保存完整状态到 `recovery-point.yaml`

#### P12: Agent输出校验
```yaml
# agent-output-validation.yaml
validation:
  requiredSections:
    - "理论基础"
    - "核心方案"
    - "安全注意事项"
    - "参考文献"

  minLength:
    report: 3000  # 最少3000字

  validationAction:
    onFail: "返回Agent补充"
```

---

## 三、实施计划

### 3.1 优先级排序

| 优先级 | 问题 | 理由 |
|--------|------|------|
| P0-紧急 | P3 上下文超限 | 影响执行稳定性 |
| P0-紧急 | P5 Agent超时 | 影响执行稳定性 |
| P1-高 | P4 批判性Agent | 影响研究质量 |
| P1-高 | P2 输出结构 | 影响框架完整性 |
| P1-高 | P6 质量门禁 | 影响研究质量 |
| P2-中 | P1 文字校对 | 影响成果质量 |
| P2-中 | P7 进度追踪 | 影响可观测性 |
| P3-低 | P8-P12 | 改进优化 |

### 3.2 实施步骤

#### 第一阶段：紧急修复 (优先级P0)

1. **增加上下文管理配置**
   - 创建 `context-management.yaml`
   - 修改 `workflow.md` 增加上下文管理章节
   - 创建恢复点文件格式规范

2. **增加Agent超时处理配置**
   - 创建 `agent-timeout-handling.yaml`
   - 修改Agent执行流程

#### 第二阶段：核心增强 (优先级P1)

3. **新增批判性审查Agent**
   - 创建 `_bmad/rem/agents/rem-agent-critic.md`
   - 修改协作流程，增加批判性审查阶段
   - 更新 `research-framework.yaml` 模板

4. **强化输出结构规范**
   - 创建 `baseline-output-specification.yaml`
   - 修改 `step-10-final-output.md`
   - 增加输出完整性校验

5. **增加质量门禁机制**
   - 创建 `quality-gates.yaml`
   - 在各Phase结束时增加门禁检查

#### 第三阶段：改进优化 (优先级P2-P3)

6. **新增文字编辑Agent**
   - 创建 `_bmad/rem/agents/rem-agent-editor.md`

7. **增加进度追踪机制**
   - 创建 `progress-tracking.yaml`
   - 增加状态看板模板

8. **其他改进项**
   - 版本管理机制
   - 协作日志完整性
   - Agent输出校验

### 3.3 文件变更清单

| 操作 | 文件路径 | 说明 |
|------|---------|------|
| 新增 | `_bmad/rem/agents/rem-agent-critic.md` | 批判性审查Agent |
| 新增 | `_bmad/rem/agents/rem-agent-editor.md` | 文字编辑Agent |
| 新增 | `_bmad/rem/config/context-management.yaml` | 上下文管理配置 |
| 新增 | `_bmad/rem/config/agent-timeout-handling.yaml` | Agent超时处理 |
| 新增 | `_bmad/rem/config/quality-gates.yaml` | 质量门禁配置 |
| 新增 | `_bmad/rem/config/baseline-output-specification.yaml` | 基准输出规范 |
| 新增 | `_bmad/rem/config/progress-tracking.yaml` | 进度追踪配置 |
| 修改 | `_bmad/rem/workflows/create-research-framework/workflow.md` | 增加上下文管理 |
| 修改 | `_bmad/rem/workflows/create-research-framework/steps-c/step-10-final-output.md` | 增加输出校验 |
| 修改 | `_bmad/rem/templates/file-architecture-specification.md` | 强化规范执行 |
| 修改 | `_bmad/rem/collaboration/cross-validation-mechanism.md` | 增加批判性审查 |

---

## 四、验收标准

### 4.1 功能验收

| 验收项 | 验收标准 |
|--------|---------|
| 上下文管理 | 上下文超过80%时自动触发压缩提示 |
| Agent超时 | 超时后能保存部分成果并支持恢复 |
| 批判性审查 | 研究成果经过批判性审查并记录 |
| 输出完整性 | 无空文件夹，所有必需文件存在 |
| 质量门禁 | 每个阶段有明确的质量检查点 |
| 文字校对 | 最终成果经过文字编辑检查 |

### 4.2 测试场景

1. **长时研究测试**: 执行超过1小时的研究，验证上下文管理
2. **Agent超时测试**: 模拟Agent超时，验证恢复机制
3. **输出完整性测试**: 验证所有必需文件生成
4. **质量门禁测试**: 模拟质量不达标，验证拦截机制

---

## 五、风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| 新Agent与现有流程冲突 | 中 | 中 | 充分测试协作流程 |
| 上下文压缩导致信息丢失 | 低 | 高 | 完善恢复点机制 |
| 质量门禁过于严格 | 中 | 中 | 设置可配置的宽松度 |
| 整改范围过大 | 中 | 中 | 分阶段实施 |

---

## 六、待确认事项

请确认以下事项后开始实施：

1. **批判性审查Agent的介入时机**：
   - 选项A：交叉验证后，最终整合前
   - 选项B：每个Agent完成后立即审查
   - 选项C：仅在最终成果输出前

2. **文字校对Agent的职责范围**：
   - 选项A：仅校对格式和语法
   - 选项B：包含术语一致性检查
   - 选项C：包含可读性优化

3. **上下文压缩的自动化程度**：
   - 选项A：仅提示，由用户手动压缩
   - 选项B：自动压缩，用户确认
   - 选项C：完全自动化

4. **质量门禁的严格程度**：
   - 选项A：宽松，允许部分不达标通过
   - 选项B：标准，关键项必须达标
   - 选项C：严格，所有项必须达标

5. **整改实施优先级**：
   - 是否同意上述优先级排序？
   - 是否有需要调整优先级的项目？

---

**文档状态**: 已完成 ✅
**下一步**: 无（所有整改任务已完成）


