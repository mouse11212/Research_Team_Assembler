# 故障手册（Incident Playbook）

## 1. 问财(pywencai)限流画像（2026-08-04 实测）

- 短窗约 **5-6 次成功**后被限流；冷却 ~10 分钟可再放行 ~5 次；累计 ~60 次成功后进入**硬限流**。
- 限流报错特征 = pywencai 内部 `'NoneType' object has no attribute 'get'`。
- 递增间隔（5s→12s→20s）对硬限流无效——连败即停，**冷却数小时**再试。
- 原则：降级保主链路（新浪清单先落库），净买额等富化字段留 NULL（非伪造），记断点。

## 2. 断点续传与补跑

```bash
cd 06-最终成果/模型原型/src
# 概念映射断点续传（断点=已尝试概念数，worker报告给出）
caffeinate -i python3 data/sync_stock_concept.py --offset {断点}
# 龙虎榜净买额补跑（只UPDATE缺net_buy的行；WENCAI_INTERVAL调节奏，默认≥5s；连续2败自中止）
WENCAI_INTERVAL=8 python3 data/backfill_dragon_tiger_enrich_retry.py {日期1} {日期2} ...
# 注意：backfill_dragon_tiger_enrich_retry.py 为 2026-08-04 会话所建；若缺口不同，参照
# data/backfill_dragon_tiger_20260804.py 模式新写（串行/限频/连败降级/Fail-Loud/busy_timeout=60000）。
```

## 3. 处置决策树

```
分片 fail 飙升或日志出现「熔断」?
├─ 是 → kill 该分片 → 同 offset/limit 单流重跑（幂等安全）→ 再失败则报告分析师裁决
└─ 否 → 完成行 fail=0?
        ├─ 是 → 通过（skip 先想北交所/停牌，勿误报）
        └─ 否 → 归因失败代码：停牌/无数据=正常；真实网络错误=重跑一次

问财线报错含 "NoneType ... 'get'"?
├─ 连续≥2次 → 立即停问财段，降级（新浪数据已落库），记断点offset与受影响日期
└─ 偶发 → 间隔拉长重试一次，仍败按连败处置

概念同步日志连续出现「成分为空」?
└─ 立即杀进程（脚本无熔断会烧光配额）→ 记断点 → 冷却数小时后 --offset 续传
```

## 4. 已知数据质量问题

- **dragon_tiger 468 行历史列错位脏数据**（trade_date 字段存股票代码如 '920981'）：按真实日期查询不受影响。清洗建议（先备份再执行，属一次性运维）：
  ```sql
  -- 候选识别（trade_date 不是8位日期）
  SELECT COUNT(*) FROM dragon_tiger WHERE trade_date NOT GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]';
  ```
- **stock_info 行业覆盖不全**（东财行业源被墙→深市兜底，仅~2900只有行业）：已知限制，待 eastmoney 恢复后跑 `sync_market_meta.py`。
- **情绪相位规则敏感**（LU单日降幅>30%即fading，曾14天振荡7次）：评估仓位系数时注意；改进方向=连续2日确认或3日平滑（属策略层，不在本 skill 范围）。

## 5. 环境坑

- mac 无 `timeout`；长任务 `caffeinate -i` 防睡眠。
- `_bmad-output/` 被 gitignore：提交用 `git add -f`。
- akshare `_ths` 等 JS 解密接口依赖 `mini-racer==0.12.4`（arm64 .dylib）；若报 dlsym symbol not found：`pip uninstall -y py-mini-racer mini-racer && pip install mini-racer==0.12.4`。
