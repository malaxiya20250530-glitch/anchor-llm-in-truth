# 🔍 Anchor · LLM Hallucination Detector

> **Zero-dependency LLM hallucination detection. 7M facts. 14 checkers. Pure Python stdlib.**

[![GitHub](https://img.shields.io/badge/GitHub-anchor--llm--in--truth-blue)](https://github.com/malaxiya20250530-glitch/anchor-llm-in-truth)
[![License](https://img.shields.io/badge/License-MIT-green)](https://github.com/malaxiya20250530-glitch/anchor-llm-in-truth/blob/master/LICENSE)

---

## ⚡ Quick Start

```bash
git clone https://github.com/malaxiya20250530-glitch/anchor-llm-in-truth.git
cd anchor-llm-in-truth
python3 hallucination_detector.py "Did 朱元璋 invent hotpot?"
```

## 🏗️ Architecture

```
User Input
  → Entity Index (514 entities, kb_core.json)
  → Fact Retrieval (7M rows, SQLite FTS)
  → 14 Checker Chain (weighted voting)
  → Graph Reasoner (multi-hop contradiction)
  → Output: verified / contradicted / unverifiable
```

## 🛡️ Security

- 12-layer Prompt Injection Defense
- 86/100 Attack Block Rate (29 vectors)
- Source Code Encrypted (.pye)
- GitHub Actions CI/CD

## 📊 Benchmarks

| Checker | Weight | Hit Rate |
|---------|--------|----------|
| YearConflictChecker | 0.92 | — |
| NumericConflictChecker | 0.90 | 10.8% |
| NegationChecker | 0.83 | 4.7% |
| AttributionChecker | 0.80 | 17.7% |
| GraphContradictionChecker | 0.78 | 11/11 ✅ |

## 🔗 Links

- [GitHub](https://github.com/malaxiya20250530-glitch/anchor-llm-in-truth)
- [Issues](https://github.com/malaxiya20250530-glitch/anchor-llm-in-truth/issues)
- [Discussions](https://github.com/malaxiya20250530-glitch/anchor-llm-in-truth/discussions)

---

Built with ❤️ on Android Termux. Zero dependencies.
