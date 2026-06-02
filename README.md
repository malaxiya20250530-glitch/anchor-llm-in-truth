# 🔍 Hallucination Detector · 幻觉检测器

[![CI](https://github.com/malaxiya20250530-glitch/shiyan2925/actions/workflows/test.yml/badge.svg)](https://github.com/malaxiya20250530-glitch/shiyan2925/actions)
[![Build](https://github.com/malaxiya20250530-glitch/shiyan2925/actions/workflows/build-binaries.yml/badge.svg)](https://github.com/malaxiya20250530-glitch/shiyan2925/actions)
[![Python](https://img.shields.io/badge/Python-3.13-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-Proprietary-red)](LICENSE)
[![Stars](https://img.shields.io/github/stars/malaxiya20250530-glitch/shiyan2925?style=social)](https://github.com/malaxiya20250530-glitch/shiyan2925)

> **Zero-dependency LLM hallucination detection middleware. Like a CDN for AI safety.**
> **零外部依赖的大模型幻觉检测中间件。像 CDN 一样守护 AI 安全。**

🌐 [Live Demo](https://malaxiya20250530-glitch.github.io/shiyan2925/) · 📖 [Contributing](CONTRIBUTING.md) · 🏥 [Medical KB](kb_medical.json) · ⚖️ [Legal KB](kb_legal.json)

---

## ⚡ 5-Second Demo · 5 秒体验

```bash
python3 hallucination_detector.py "朱元璋发明了火锅"
```

```
🔴 [contradicted] 朱元璋发明了火锅  (90%)
   Evidence: 朱元璋是明朝开国皇帝，1328-1398 年
   Source: 明史
```

English users try:
```bash
python3 hallucination_detector.py "Edison invented the light bulb"
```

---

## 🏗️ Architecture · 架构

```
User → awareness_gateway (OpenAI-compatible API)
         ├─ BillingMiddleware     ← Pay-per-token
         ├─ ObserverSecurity      ← Security middleware
         ├─ HallucinationDetector
         │    ├─ 14 Checkers      ← Weighted chain
         │    ├─ Knowledge Graph   ← 608 facts
         │    ├─ Vector KB         ← Hybrid search
         │    └─ Web Verifier      ← Cross-validation
         ├─ Consensus Engine
         ├─ Alignment Analyzer
         └─ Feedback → Auto KB Updater (self-evolving)
```

## 🚀 Quick Start · 快速开始

**Zero dependencies. Clone and run.**

```bash
git clone https://github.com/malaxiya20250530-glitch/shiyan2925.git
cd shiyan2925

# CLI detection
python3 hallucination_detector.py "爱迪生发明了电灯泡"

# OpenAI-compatible gateway
python3 awareness_gateway.py --mock --port 8800
curl http://localhost:8800/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-f你的key" \
  -d '{"model":"mock","messages":[{"role":"user","content":"你好"}]}'

# Dashboard
python3 dashboard_server.py --port 8080
# Open http://localhost:8080
```

## 💰 Monetization · 变现

```bash
# Create API keys with tiered plans
python3 billing.py create "Client A" pro   # free / basic / pro / enterprise
python3 billing.py stats                    # MRR overview
python3 billing.py list                     # All accounts
```

| Plan | Monthly Quota | Rate Limit | Price |
|------|:---:|:---:|:---:|
| Free · 免费 | 10K tokens | 2 req/s | ¥0 |
| Basic · 基础 | 100K tokens | 5 req/s | ¥29 |
| Pro · 专业 | 1M tokens | 20 req/s | ¥199 |
| Enterprise · 企业 | Unlimited | 50 req/s | ¥999 |

## 🏥 Industry Knowledge Bases · 行业知识库

| Domain | Entries | File |
|--------|:---:|------|
| Medicine · 医疗 | 45 | `kb_medical.json` |
| Law · 法律 | 52 | `kb_legal.json` |
| General · 通用 | 511 | `kb_core.json` |

```bash
python3 -c "from kb_loader import load_industry_kb; load_industry_kb()"
```

## 🔐 Binary Compilation · 加密编译

```
git push → GitHub Actions → .so for Linux / Mac / Windows
```

| Platform | Artifact |
|----------|----------|
| 🐧 Linux x86_64 | `.so` |
| 🍎 macOS arm64 | `.so` |
| 🍏 macOS x86_64 | `.so` |
| 🪟 Windows x86_64 | `.pyd` |

## 🧪 Testing · 测试

```bash
python3 test_fact_checker.py          # Unit tests
python3 test_knowledge_graph.py       # Knowledge graph
python3 test_observer_security.py     # Security observer
python3 test_deepseek.py              # End-to-end with DeepSeek
```

## 📊 Stats · 项目规模

- **17,733 lines** Python · **61 modules** · **14 checkers**
- **608 facts** · **6 CI workflows** · **0 external deps**

## 📄 License · 许可证

Proprietary · 专有软件. Contact author for commercial licensing.
Copyright © 2025-2026 Li Qiao · 李桥

---

⭐ **If this helps you, star this repo! 如果对你有用，点个 Star！**
