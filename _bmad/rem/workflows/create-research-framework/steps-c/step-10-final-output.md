# Step 10: 生成最终框架文件

## 目标
整合所有前序步骤的输出，生成最终的研究框架配置文件。

## 输入
- 所有前序Step的输出

## 输出
- 完整研究框架配置文件（YAML格式）

## 框架配置文件结构

```yaml
# research-framework.yaml
# 研究框架配置文件
# 由组团研究器自动生成

metadata:
  id: RF-{timestamp}
  name: "{课题名称}"
  version: "1.0.0"
  createdAt: {timestamp}
  generator: "Research Team Assembler"

# 课题信息
topic:
  title: "{课题标题}"
  description: "{课题描述}"
  keywords: []
  domains: []

# 方法论选择
methodology:
  selected:
    id: "{methodology-id}"
    name: "{方法论名称}"
    rationale: "{选择理由}"
    confidence: 0.9
  alternatives:
    - id: "{alternative-id}"
      name: "{备选方法论}"

# 团队配置
team:
  totalSize: {N}
  leadAgent:
    name: "{主负责Agent名称}"
    role: "{角色}"
    domain: "{领域}"

  agents:
    - id: "agent-1"
      name: "{Agent名称}"
      role: "{角色}"
...
```

## 文件结构
fileStructure:
  root: "research-projects/{project-id}/"
  structure:
    - name: "01-课题定义"
      path: "01-topic-definition/"
    - name: "02-文献综述"
      path: "02-literature-review/"
    - name: "03-研究设计"
      path: "03-research-design/"
    - name: "04-agent产出"
      path: "04-agent-outputs/"
    - name: "05-协作记录"
      path: "05-collaboration-logs/"
    - name: "06-最终成果"
      path: "06-final-deliverables/"

# 状态管理
stateManagement:
  documentTypes:
    - type: "研究报告"
      states: [draft, pending_review, under_review, revision, confirmed, divergent, archived]
    - type: "文献综述"
      states: [draft, confirmed, archived]
    - type: "数据文件"
      states: [draft, confirmed, archived]

  transitions:
    draft -> pending_review: "开始审查"
    pending_review -> under_review: "进入审查队列"
    under_review -> revision: "需要修订"
    revision -> confirmed: "审查通过，可以归档"

    confirmed -> archived: "归档保存"
    archived -> divergent: "标记为分歧，需要人工处理"

    divergent -> confirmed: "最终合并"

    confirmed -> archived: "最终归档"

# 质量标准
qualityStandards:
  - "所有研究结论必须有证据支撑"
  - "所有引用需要有明确的出处"
  - "研究方法必须可复现"
  - "所有假设必须可验证"

---

## 完成条件
- [ ] 所有配置项已填写
- [ ] YAML格式正确
- [ ] 文件已保存到指定路径
- [ ] 框架配置文件可被系统加载

## 输出完整性校验

### 10.1 执行输出完整性检查
读取基准输出规范配置文件：
检查以下内容：
1. 必需文件是否存在
2. 文件内容是否为空或占位符
3. 每个Agent是否有输出文件
4. 是否存在空文件夹

### 10.2 文件内容验证
对于每个文件，检查
- 文件大小是否超过最小要求
- 内容是否包含必需章节
- 是否存在占位符内容（如"待填写"、"TODO"等）

### 10.3 清理空文件夹
扫描项目目录，删除所有空文件夹。
空文件夹定义：不包含任何文件的文件夹。

### 10.4 生成校验报告
如果发现问题，生成校验报告到：
00-meta/output-validation-report.md
}

```

报告问题：
- 严重问题：缺少必需文件
- 一般问题:内容不足最小要求
- 优化建议:可以改进的内容
```

### 10.5 完成条件
- [ ] 所有必需文件存在且有内容
- [ ] 无空文件夹
- [ ] 无占位符内容
- [ ] YAML格式正确
- [ ] 文件已保存到指定路径
- [ ] **输出完整性校验通过**

## 下一步
研究框架创建工作流完成！返回用户确认,进入实施阶段。
