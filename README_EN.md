# Awareness Gateway · 觉察推理网关

[![Tests](https://github.com/malaxiya20250530-glitch/shiyan2925/actions/workflows/test.yml/badge.svg)](https://github.com/malaxiya20250530-glitch/shiyan2925/actions)

A transparent proxy between users and LLMs that detects hallucinations, alignment drift, and safety risks in real time.

```
User → [Awareness Gateway] → LLM API
         ├── Fact-checking (10-checker chain of responsibility)
         ├── Alignment detection (emotion / pressure / pleasing drift)
         └── Safety observation (anchoring / source attribution / consistency)
```

## Quick Start

### Install

```bash
pip install awareness-gateway
# or for OCR support:
pip install awareness-gateway[ocr]
```

### Run

```bash
# Mock mode (no upstream LLM needed)
awareness-gateway --mock --port 8800

# Dashboard
awareness-dashboard --port 8900
```

### API

```bash
curl -X POST http://localhost:8800/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Did朱元璋 invent hotpot?"}]}'

# OCR endpoint
curl -X POST http://localhost:8800/ocr \
  -H "Content-Type: application/json" \
  -d '{"text":"The Earth is flat"}'
```

## LangChain Integration

```python
from langchain_plugin import HallucinationTool, HallucinationCallback

# Tool mode
tool = HallucinationTool()
tool.run("The Earth is flat")

# Auto-detect LLM output
from langchain.llms import OpenAI
llm = OpenAI(callbacks=[HallucinationCallback()])
```

## Architecture

```
HallucinationDetector (849 lines)
  ├── FactExtractor — claim extraction + entity recognition
  ├── AnchorEngine — 10 priority checkers
  │   ├── _check_knowledge_base (KB matching)
  │   ├── _check_infinity / _check_negation
  │   ├── _check_year_conflict / _check_numeric_conflict
  │   ├── _check_overlap / _check_temporal_order
  │   ├── _check_location_conflict
  │   └── _check_absolute_claim
  └── Reporter

Verification Pipeline:
  1. KB direct match → fast path
  2. Hybrid retrieval (BM25 + TF-IDF vector) → semantic fallback
  3. Web cross-verification (DuckDuckGo + Wikipedia) → last resort
  4. Active learning → uncertain samples → human labeling → KB evolution
```

## Features

- **Pure Python stdlib** — zero required dependencies
- **10 priority checkers** — chain of responsibility pattern
- **Hybrid retrieval** — BM25 keywords + TF-IDF semantic vectors
- **Multi-source verification** — DuckDuckGo + Wikipedia cross-check
- **Active learning** — uncertain samples feed back into knowledge base
- **OCR support** — detect hallucinations in screenshots
- **82 test cases** — comprehensive coverage
- **Docker** — one-command deployment
- **LangChain plugin** — Tool + Callback integration

## Tests

```bash
python3 test_fact_checker.py        # Core detection (5)
python3 test_feedback_store.py      # Feedback CRUD (10)
python3 test_update_kb.py           # KB management (9)
python3 test_observer_security.py   # Safety observer (11)
python3 test_alignment_middleware.py # Alignment (20)
python3 test_observer_proxy.py      # Observer proxy (13)
python3 test_feedback_dashboard.py  # Dashboard (5)
python3 test_stress.py              # Stress test (3)
python3 test_vector_kb.py           # Vector retrieval (6)
# Total: 82 test cases
```

## Docker

```bash
docker-compose up -d
# Gateway: http://localhost:8800
# Dashboard: http://localhost:8900
```

## Adding a New Checker

1. Write `_check_xxx(self, claim, fact) → (result_type, confidence) | None`
2. Add to `_PRIORITY_CHECKERS` list

That's it. No class inheritance needed.

---

Built with ❤️ on Android Termux. [中文 README](README.md)
