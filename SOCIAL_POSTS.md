# 推广帖模板

---

## Reddit — r/Python

**Title:** Show HN: llm-fact-guard — zero-dependency hallucination detection for LLMs

**Body:**

I built a zero-dependency Python middleware that detects LLM hallucinations in real-time. 

`pip install llm-fact-guard`

```python
from hallucination_detector import HallucinationDetector
guard = HallucinationDetector()
report = guard.analyze("朱元璋发明了火锅")
# → contradicted ✅
```

**What it does:**
- 14 checkers (KB matching, year conflict, numeric, attribution, negation…)
- WAF (44 OWASP vectors blocked)
- Circuit breaker + rate limiter
- Structured JSON logging for Loki/ES

3000 requests, 0 errors at 100 QPS. Pure Python stdlib.

GitHub: https://github.com/malaxiya20250530-glitch/anchor-llm-in-truth
PyPI: https://pypi.org/project/llm-fact-guard/

---

## Reddit — r/MachineLearning

**Title:** [P] llm-fact-guard — 14-checker hallucination detection chain for LLMs

Check it out on PyPI: `pip install llm-fact-guard`

---

## Hacker News — Show HN

**Title:** Show HN: llm-fact-guard — detect LLM hallucinations with 14 checkers

**Body:**

LLMs hallucinate. This catches them. Pure Python, zero dependencies.

14-checker chain: KB matching → Year conflict → Numeric validation → Negation → Attribution → and 9 more. Built-in WAF, circuit breaker, structured logging.

3000 req / 0 errors @ 100 QPS.

PyPI: https://pypi.org/project/llm-fact-guard/

---

## Twitter / X

```
LLMs lie. This catches them.

pip install llm-fact-guard

✅ 14 checkers
✅ Zero dependencies  
✅ 100 QPS, 0 errors
✅ Built-in WAF

pypi.org/project/llm-fact-guard/
```

---

## 知乎 / V2EX

**标题:** 开源了一个零依赖 LLM 幻觉检测中间件，14 个检查器链

**正文:**

大模型说朱元璋发明了火锅？一键揪出来。

```bash
pip install llm-fact-guard
```

```python
from hallucination_detector import HallucinationDetector
guard = HallucinationDetector()
guard.analyze("朱元璋发明了火锅")
# → 矛盾 / 朱元璋是明朝开国皇帝，火锅起源可追溯至商周
```

**能力:**
- 14 个检查器 (KB匹配/年份冲突/数字校验/否定检测/归因分析...)
- 内置 WAF，44 项 OWASP 全拦截
- 熔断器 + 速率限制
- 纯 Python 标准库，零外部依赖
- 3000 请求 0 错误 @ 100 QPS

PyPI: https://pypi.org/project/llm-fact-guard/
GitHub: https://github.com/malaxiya20250530-glitch/anchor-llm-in-truth

---

## 掘金

**标题:** 我写了一个 LLM 幻觉检测器，纯 Python，pip 就能装

（内容同上）

---

## 推广顺序建议

1. **今天** → V2EX / 掘金 发帖（中文圈起量最快）
2. **明天** → Reddit r/Python + r/MachineLearning
3. **后天** → Hacker News Show HN
4. **持续** → Twitter/X 每周发一次

