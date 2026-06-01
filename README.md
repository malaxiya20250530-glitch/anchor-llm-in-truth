[![测试](https://github.com/malaxiya20250530-glitch/shiyan2925/actions/workflows/test.yml/badge.svg)](https://github.com/malaxiya20250530-glitch/shiyan2925/actions)

# 觉察推理网关 · Awareness Gateway

架在 LLM 和用户之间的透明代理，实时检测幻觉、对齐漂移、安全风险。

```
用户 → [觉察网关] → LLM API
         ├── 事实核查（10 检查器责任链）
         ├── 对齐检测（情绪 / 压力 / 取悦漂移）
         └── 安全观察（锚定 / 来源归因 / 一致性）
```

## 性能指标 (Phase 1 冻结基线)

| 指标 | 值 |
|------|------|
| F1 分数 | **0.851** |
| 准确率 | 79.9% |
| 精确率 | 93.8% |
| 召回率 | 77.8% |
| 平均延迟 | 14.2 ms/条 |
| P50 | 10.5 ms |
| P95 | 42.8 ms |
| P99 | 57.2 ms |
| KB 规模 | 225 实体, 1000 事实 |
| 代码规模 | 18,353 行, 46 模块 |
| 依赖 | **0 外部依赖**（纯 Python 3.10+ 标准库） |

### 各检查器 F1

| 检查器 | F1 | 说明 |
|--------|:--:|------|
| negation | 0.938 | 否定模式匹配 |
| temporal_order | 0.919 | 时间顺序推理 |
| knowledge_base | 0.971 | 知识库匹配 |
| graph_relation | 0.896 | 知识图谱推理 |
| location_conflict | 0.881 | 地点冲突检测 |
| numeric_conflict | 0.848 | 数值偏差检测 |
| year_conflict | 0.743 | 年份冲突检测 |

### Phase 2 组件

- `Dockerfile` — alpine 轻量镜像（预计 < 80MB）
- `circuit_breaker.py` — 三级降级断路器（128/286/296ms）
- `webhook_notifier.py` — 异步告警推送
- `.github/workflows/ci.yml` — CI 回归守卫（Hash 验证 + F1 退化检查）

## 快速开始

### Docker（推荐）

```bash
# 启动网关 + 仪表盘
docker-compose up -d

# 验证
curl http://localhost:8800/health
curl http://localhost:8801/        # 反馈仪表盘

# 压测
python3 stress_test.py --port 8800 --requests 50 --concurrency 10
```

### 本地运行

```bash
# 启动网关（mock 模式，无需上游 LLM）
python3 awareness_gateway.py --port 8800 --mock &

# 启动反馈仪表盘
python3 feedback_dashboard.py --port 8801 &

# 测试
curl -X POST http://localhost:8800/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"朱元璋发明了火锅吗？"}],"session_id":"test"}'
```

### 配置

编辑 `config.json`：

```json
{
  "gateway": { "port": 8800, "mock_mode": false, "upstream_url": "http://localhost:11434/v1" },
  "observer": { "sensitivity": 0.5 },
  "security": { "white_box_logging": true },
  "social_alignment": { "security_level": "balanced" }
}
```

所有模块在启动时自动读取 `config.json`，命令行参数可覆盖配置。

## 测试运行

```bash
# 全部 8 个测试套件，76 个用例
python3 test_fact_checker.py        # 幻觉检测核心（5 组）
python3 test_feedback_store.py      # 反馈库 CRUD（10 组）
python3 test_update_kb.py           # 知识库管理（9 组）
python3 test_observer_security.py   # 安全观察器（11 组）
python3 test_alignment_middleware.py # 对齐分析（20 组）
python3 test_observer_proxy.py      # 观察代理（13 组）
python3 test_feedback_dashboard.py  # 仪表盘（5 组）
python3 test_stress.py              # 压力测试结构（3 组）

# 一键运行
for t in test_*.py; do python3 "$t" && echo "---"; done
```

## 架构

```
hallucination_detector (861行)     ← 幻觉检测引擎
  ├── FactExtractor                ← 断言提取 + 实体识别
  ├── AnchorEngine                 ← 10 检查器责任链
  │   ├── _check_knowledge_base    ← KB 匹配（最高优先）
  │   ├── _check_infinity / _check_negation
  │   ├── _check_year_conflict / _check_numeric_conflict
  │   ├── _check_overlap / _check_temporal_order
  │   ├── _check_location_conflict
  │   └── _check_absolute_claim    ← 绝对化检测（最低优先）
  └── Reporter                     ← 格式化输出

awareness_gateway (1024行)         ← HTTP 网关（Ollama/OpenAI 双协议）
  └── observer_proxy (392行)       ← 流式观察器

observer_security (642行)          ← 安全层（多观察器委员会）
alignment_middleware (578行)       ← 对齐分析（情绪/压力/漂移）

feedback_store (178行)             ← SQLite 反馈库
feedback_dashboard (314行)         ← Web 仪表盘
update_kb (140行)                  ← 知识库管理 CLI
```

## 新增检查器

只需两步，不破坏责任链：

1. 写函数 `_check_xxx(self, claim, fact) -> (result_type, confidence) | None`
2. 把函数名加到 `_PRIORITY_CHECKERS` 列表

```python
def _check_new_pattern(self, claim: str, fact: str):
    """检测新的冲突模式"""
    if "某种模式" in claim and "另一种" in fact:
        return ("contradicted", 0.7)
    return None

# 在 _PRIORITY_CHECKERS 中注册
_PRIORITY_CHECKERS = [
    "_check_knowledge_base",
    # ...
    "_check_new_pattern",  # ← 加这里
]
```

## 压测结果

```
请求数: 20  |  并发: 3  |  吞吐: 89 req/s
平均延迟: 19ms  |  P50: 6.5ms  |  P95: 102ms
错误率: 0%  |  评级: 🟢 优秀
```

## 许可

Copyright (c) 2025 李桥. 专有软件 — 保留所有权利。
