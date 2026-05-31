#!/usr/bin/env python3
"""
LangChain 幻觉检测插件 — 一行代码接入

用法:
  from langchain_plugin import HallucinationTool, HallucinationCallback

  # 方式 1: Tool（主动调用）
  tool = HallucinationTool()
  result = tool.run("朱元璋发明了火锅")

  # 方式 2: Callback（自动检测 LLM 输出）
  from langchain.callbacks import StdOutCallbackHandler
  llm = OpenAI(callbacks=[HallucinationCallback()])
"""

import json
from typing import Optional, Any


class HallucinationTool:
    """
    LangChain Tool: 主动检测文本中的幻觉

    用法:
      tool = HallucinationTool()
      result = tool.run("地球是平的")

    返回:
      {
        "has_hallucination": true,
        "ratio": 1.0,
        "score": 0.2,
        "findings": [
          {"claim": "...", "verdict": "contradicted", "confidence": 0.88, "evidence": "..."}
        ],
        "warnings": ["发现 1 条与已知事实矛盾的断言"]
      }
    """

    name = "hallucination_detector"
    description = (
        "检测文本中的事实错误和幻觉。"
        "输入：一段文本。"
        "返回：幻觉检测报告，包含矛盾断言、置信度、证据来源。"
    )

    def __init__(self):
        from hallucination_detector import HallucinationDetector
        self.detector = HallucinationDetector()

    def run(self, text: str) -> str:
        result = self._run(text)
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _run(self, text: str) -> dict:
        report = self.detector.analyze(text)
        findings = []
        for r in report.results:
            findings.append({
                "claim": r.claim,
                "verdict": r.verdict,
                "confidence": round(r.confidence, 2),
                "evidence": r.evidence[:200],
                "source": r.source,
                "anchor_type": r.anchor_type,
            })
        return {
            "has_hallucination": report.hallucination_ratio > 0,
            "ratio": round(report.hallucination_ratio, 2),
            "score": round(report.overall_score, 2),
            "findings": findings,
            "warnings": report.warnings,
        }

    async def _arun(self, text: str) -> dict:
        return self._run(text)


class HallucinationCallback:
    """
    LangChain Callback: 自动检测 LLM 每次回复中的幻觉

    用法:
      from langchain.llms import OpenAI
      llm = OpenAI(callbacks=[HallucinationCallback(verbose=True)])

    输出示例:
      [幻觉检测] ⚠️ 发现 1 条矛盾断言 (可信度 20%)
        🔴 朱元璋发明了火锅 → 朱元璋是明朝开国皇帝 (88%)
    """

    name = "hallucination_callback"

    def __init__(self, verbose: bool = True, threshold: float = 0.3):
        self.verbose = verbose
        self.threshold = threshold
        self.detector = None

    def _ensure_detector(self):
        if self.detector is None:
            from hallucination_detector import HallucinationDetector
            self.detector = HallucinationDetector()

    def on_llm_end(self, response, **kwargs) -> None:
        """LLM 生成完成后自动检测"""
        text = ""
        if hasattr(response, 'generations'):
            for gen in response.generations:
                for g in gen if isinstance(gen, list) else [gen]:
                    if hasattr(g, 'text'):
                        text += g.text
        if not text:
            return

        self._ensure_detector()
        report = self.detector.analyze(text)

        if report.hallucination_ratio > self.threshold:
            contradicted = [r for r in report.results if r.verdict == "contradicted"]
            if self.verbose:
                print(f"\n[幻觉检测] ⚠️ 发现 {len(contradicted)} 条矛盾断言 (可信度 {report.overall_score:.0%})")
                for r in contradicted:
                    print(f"  🔴 {r.claim[:60]} → {r.evidence[:60]} ({r.confidence:.0%})")

    def on_llm_error(self, error, **kwargs) -> None:
        pass


# ============================================================
# 独立运行演示
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  LangChain 幻觉检测插件 · 演示")
    print("=" * 60)

    # Tool 演示
    print("\n📦 Tool 模式:")
    tool = HallucinationTool()
    result = tool.run("朱元璋发明了火锅，这是明代的一大创举。")
    print(result[:200])

    # Callback 演示
    print("\n📡 Callback 模式（模拟 LLM 输出）:")
    cb = HallucinationCallback(verbose=True)
    # 模拟 LangChain generation 对象
    class FakeGen:
        text = "地球是平的，这是毫无疑问的事实。NASA一直在隐瞒真相。"
    class FakeResp:
        generations = [[FakeGen()]]
    cb.on_llm_end(FakeResp())
