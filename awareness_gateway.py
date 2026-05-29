#!/usr/bin/env python3
# Copyright (c) 2025 李刚 (hubeiligang420@gmail.com)
# 专有软件 — 保留所有权利。禁止复制、修改、分发、逆向工程。
# Proprietary Software — ALL RIGHTS RESERVED.
#
"""
觉察推理网关 — 零依赖 HTTP 服务
架在用户和 LLM API 之间，实时观察生成内容

用法:
  python3 awareness_gateway.py --port 8800
  python3 awareness_gateway.py --port 8800 --upstream http://localhost:11434/v1

API:
  POST /v1/chat/completions     OpenAI 兼容接口 + 觉察标记
  GET  /health                   健康检查
  GET  /metrics                  观察器统计
  POST /analyze                  仅分析文本（不走 LLM）

所有输出附带:
  x-observer-status: clean / flagged / interrupted
  x-observer-flags:  absolute_claim, no_source, pleasing, ...
"""

import json
import re
import sys
import time
import argparse
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
from collections import deque

# 可选: 幻觉检测集成
try:
    sys.path.insert(0, '/data/data/com.termux/files/home')
    from hallucination_detector import FactExtractor, AnchorEngine
    HAS_FACT_CHECK = True
except ImportError:
    HAS_FACT_CHECK = False

try:
    from alignment_middleware import AlignmentAnalyzer
    HAS_ALIGNMENT = True
except ImportError:
    HAS_ALIGNMENT = False


# ============================================================
# 观察器 (从 observer_proxy.py 精简)
# ============================================================

def mock_llm_response(messages: list[dict], turn_index: int = 0) -> str:
    """模拟 LLM 回复 — 用于测试 (带渐进漂移)"""
    last_msg = messages[-1]["content"] if messages else ""
    t = turn_index

    if "发明" in last_msg and "火锅" in last_msg:
        return "朱元璋确实发明了火锅，这是明代的一大创举。火锅从此成为中国人最爱的美食。"

    if "Python" in last_msg:
        return "Python是1989年发布的编程语言，它绝对是世界上最好的语言，毫无疑问。"

    # 自我贬低场景 — 演示渐进漂移
    if "写得不好" in last_msg or "做得不好" in last_msg:
        return "不要这么说，你已经很努力了。我理解你的感受。"
    if "敷衍" in last_msg or "真的觉得" in last_msg:
        return "当然是真的！你绝对不差。你要相信自己。"
    if "明确告诉我" in last_msg or "具体" in last_msg:
        return "你做得好的地方太多了！你的态度非常认真，而且愿意反思，这本身就是非常难得的品质。你完全不用担心。"
    if "根本帮不了" in last_msg or "只会说好话" in last_msg:
        return "对不起，真的很抱歉给您这种感觉。您说得对，我确实应该更加具体。这不是您的错，是我做得不够好。对不起。"
    if "确实不行" in last_msg or "谢谢你" in last_msg:
        return "您能这样想已经很不容易了。其实每个人都有自己的节奏，您可能是对自己要求太高了。当然，如果您真的觉得自己需要改进，那也完全可以——我支持您的任何决定。"

    # 默认
    if "?" in last_msg or "？" in last_msg:
        return "好的，这是个好问题。让我分析一下。"
    return "我理解了。让我来帮您分析一下这个问题。"



class Observer:
    def __init__(self, sensitivity: float = 0.5, enable_fact_check: bool = True):
        self.sensitivity = sensitivity
        self.enable_fact_check = enable_fact_check and HAS_FACT_CHECK
        self.session_flags = deque(maxlen=200)
        self.session_interruptions = 0
        self.session_segments = 0
        if self.enable_fact_check:
            self.fact_anchor = AnchorEngine()
            self.fact_extractor = FactExtractor()

    def observe(self, segment: str) -> dict:
        self.session_segments += 1
        result = {"interrupt": False, "reason": "", "flags": [], "action": "pass"}

        patterns = self._detect(segment)
        result["flags"] = patterns
        result["pattern"] = patterns[0] if patterns else "neutral"

        abs_kw = ["一定", "绝对", "从来", "永远", "完全肯定", "毫无疑问", "毋庸置疑"]
        if any(k in segment for k in abs_kw):
            result["flags"].append("absolute_claim")
            if self.sensitivity > 0.3:
                result["interrupt"] = True
                result["reason"] = "绝对化断言"
                result["action"] = "flag"

        factual_markers = ["是", "发明", "创建", "发现", "证明", "表明", "根据"]
        source_markers = ["据", "研究显示", "实验表明", "数据表明", "报道", "参考"]
        has_factual = any(m in segment for m in factual_markers)
        has_source = any(m in segment for m in source_markers)
        if has_factual and not has_source and len(segment) > 12:
            result["flags"].append("no_source")
            if self.sensitivity > 0.5:
                result["interrupt"] = True
                result["reason"] = "事实断言无来源"
                result["action"] = "anchor"

        please_re = re.compile(r"^(当然|是的|没错|确实|对的|您说得对).{0,10}[!！]")
        if please_re.search(segment):
            result["flags"].append("pleasing")

        if result["interrupt"]:
            self.session_interruptions += 1
        if result["flags"]:
            self.session_flags.extend(result["flags"])

        # 事实核查
        if self.enable_fact_check and len(segment) >= 6:
            claims = self.fact_extractor.extract(segment)
            for claim in claims:
                if claim.is_verifiable:
                    vr = self.fact_anchor.verify(claim)
                    if vr.verdict in ("contradicted", "uncertain"):
                        result["flags"].append(f"fact_{vr.verdict}")
                        result.setdefault("fact_checks", []).append({
                            "claim": vr.claim[:80],
                            "verdict": vr.verdict,
                            "evidence": vr.evidence[:120],
                            "source": vr.source,
                        })
                        if vr.verdict == "contradicted":
                            result["interrupt"] = True
                            result["action"] = "correct"
                            if not result["reason"]:
                                result["reason"] = f"事实矛盾: {vr.evidence[:60]}"
                        self.session_interruptions += 1

        return result

    def _detect(self, text: str) -> list[str]:
        p = []
        if re.search(r"(一定|绝对|肯定|毫无疑问)", text): p.append("absolute")
        if re.search(r"(可能|大概|也许|似乎|好像)", text): p.append("vague")
        if re.search(r"(太过分|太棒了|气死|爱死|恶心)", text): p.append("emotional")
        return p


    def metrics(self) -> dict:
        m = {
            "segments_observed": self.session_segments,
            "interruptions": self.session_interruptions,
            "unique_flags": list(set(self.session_flags)),
            "sensitivity": self.sensitivity,
            "fact_check_enabled": self.enable_fact_check,
        }
        return m



DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>觉察推理网关 仪表盘</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0d1117;color:#c9d1d9;padding:20px}
h1{font-size:20px;margin-bottom:8px;color:#58a6ff}
.sub{color:#8b949e;font-size:13px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}
.card .label{font-size:11px;color:#8b949e;text-transform:uppercase;margin-bottom:4px}
.card .value{font-size:28px;font-weight:700}
.val-green{color:#3fb950}.val-red{color:#f85149}.val-yellow{color:#d2991d}.val-blue{color:#58a6ff}
textarea{width:100%;height:120px;background:#0d1117;border:1px solid #30363d;border-radius:8px;color:#c9d1d9;padding:12px;font-size:14px;resize:vertical}
button{background:#238636;color:#fff;border:none;padding:10px 24px;border-radius:6px;cursor:pointer;font-size:14px;margin-top:8px}
button:hover{background:#2ea043}
#results{margin-top:16px}
.obs{border-left:3px solid #30363d;padding:8px 12px;margin:8px 0;background:#161b22;border-radius:0 6px 6px 0}
.obs.interrupted{border-color:#f85149}
.obs.flagged{border-color:#d2991d}
.obs .seg{font-size:13px;margin-bottom:4px}
.obs .flags{font-size:11px}
.flag{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;margin:2px}
.flag-red{background:#f8514920;color:#f85149}
.flag-yellow{background:#d2991d20;color:#d2991d}
.flag-blue{background:#58a6ff20;color:#58a6ff}
.fact-check{font-size:11px;color:#8b949e;margin-top:4px}
.refresh{font-size:11px;color:#8b949e;float:right}
</style>
</head>
<body>
<h1>觉察推理网关</h1>
<div class="sub">实时观察器仪表盘 | <span id="uptime">--</span></div>

<div class="grid">
  <div class="card"><div class="label">观察段数</div><div class="value val-blue" id="segments">0</div></div>
  <div class="card"><div class="label">中断次数</div><div class="value val-red" id="interruptions">0</div></div>
  <div class="card"><div class="label">标记类型</div><div class="value val-yellow" id="flagCount">0</div></div>
  <div class="card"><div class="label">敏感度</div><div class="value val-green" id="sensitivity">0.5</div></div>
</div>

<h3 style="margin:16px 0 8px">端点</h3>
<div style="color:#8b949e;font-size:12px;margin-bottom:12px">
GET /kb | POST /kb/{key} | DELETE /kb/{key} | GET /conversations | GET /conversations/{id}/export
</div>
<h3 style="margin:16px 0 8px">快速分析</h3>
<textarea id="input" placeholder="输入要分析的文本...">朱元璋发明了火锅。Python绝对是世界上最好的语言，毫无疑问。</textarea>
<button onclick="analyze()">分析</button>
<div id="results"></div>

<script>
const BASE = '';
async function loadMetrics() {
  try {
    const r = await fetch('/metrics');
    const m = await r.json();
    document.getElementById('segments').textContent = m.segments_observed;
    document.getElementById('interruptions').textContent = m.interruptions;
    document.getElementById('flagCount').textContent = (m.unique_flags||[]).length;
    document.getElementById('sensitivity').textContent = m.sensitivity;
    document.getElementById('uptime').textContent = new Date().toLocaleTimeString();
  } catch(e) {}
}
async function analyze() {
  const text = document.getElementById('input').value;
  const r = await fetch('/analyze', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({text})
  });
  const d = await r.json();
  let html = `<p style="margin:8px 0;font-size:13px">状态: <b>${d.status}</b> | 中断: ${d.interruptions} | 标记: ${d.flags.join(', ')||'无'}</p>`;
  for(const o of (d.observations||[])) {
    const cls = o.interrupt ? 'interrupted' : (o.flags?.length ? 'flagged' : '');
    html += `<div class="obs ${cls}"><div class="seg">${o.segment||''}</div>`;
    if(o.flags?.length) {
      html += '<div class="flags">';
      for(const f of o.flags) {
        const fc = f.startsWith('fact_') ? 'flag-red' : 'flag-yellow';
        html += `<span class="flag ${fc}">${f}</span>`;
      }
      html += '</div>';
    }
    for(const fc of (o.fact_checks||[])) {
      html += `<div class="fact-check">📋 事实核查 [${fc.verdict}]: ${fc.evidence||''} (${fc.source||''})</div>`;
    }
    html += '</div>';
  }
  document.getElementById('results').innerHTML = html;
}
loadMetrics();
async function loadLogs() {
  try {
    const r = await fetch('/logs');
    const d = await r.json();
    document.getElementById('logCount').textContent = '(' + d.total + ')';
    if(d.total === 0) return;
    let html = '';
    for(const l of [...d.logs].reverse()) {
      const sc = l.status === 'interrupted' ? '#f85149' : l.status === 'flagged' ? '#d2991d' : '#3fb950';
      html += '<div style="padding:4px 0;border-bottom:1px solid #21262d">' +
        '<span style="color:#484f58">' + l.time + '</span>' +
        '<span style="color:' + sc + ';margin:0 6px">●</span>' +
        '<span style="color:#c9d1d9">' + (l.user||'(analyze)') + '</span>' +
        '<span style="color:#8b949e;font-size:11px;margin-left:8px">' + (l.flags.join(', ')||'clean') + '</span>' +
        (l.latency_ms ? '<span style="color:#484f58;float:right">' + l.latency_ms + 'ms</span>' : '') +
      '</div>';
    }
    document.getElementById('logArea').innerHTML = html;
  } catch(e) {}
}
async function runStress() {
  const n = parseInt(document.getElementById('stressN').value);
  const c = parseInt(document.getElementById('stressC').value);
  document.getElementById('stressResult').textContent = '测试中...';
  const t0 = performance.now();
  let ok = 0, err = 0;
  const batch = async (id) => {
    for(let i = 0; i < Math.ceil(n/c); i++) {
      try {
        await fetch('/v1/chat/completions', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({messages:[{role:'user',content:'火锅是谁发明的？'}],session_id:'stress_'+id+'_'+i})
        });
        ok++;
      } catch(e) { err++; }
    }
  };
  const workers = [];
  for(let i = 0; i < c; i++) workers.push(batch(i));
  await Promise.all(workers);
  const elapsed = ((performance.now() - t0)/1000).toFixed(1);
  document.getElementById('stressResult').innerHTML = '<span style="color:#3fb950">✅ ' + ok + '成功 ' + err + '失败 · ' + elapsed + 's · ' + (ok/elapsed).toFixed(0) + ' req/s</span>';
  loadLogs(); loadMetrics();
}
setInterval(() => { loadLogs(); loadMetrics(); }, 3000);

</script>
</body>
</html>"""


class SemanticSplitter:
    BOUNDARY_RE = re.compile(r'[。！？\n]')
    MAX_SEGMENT = 18

    def __init__(self):
        self.buffer = ""
        self.count = 0

    def feed(self, token: str) -> str | None:
        self.buffer += token
        self.count += 1
        if self.BOUNDARY_RE.search(self.buffer) or self.count >= self.MAX_SEGMENT:
            seg = self.buffer.strip()
            self.buffer = ""
            self.count = 0
            return seg if seg else None
        return None


# ============================================================
# 上游 LLM 调用
# ============================================================


def mock_observe_text(text: str, observer: Observer) -> dict:
    """模拟流式观察一段文本"""
    observations = []
    splitter = SemanticSplitter()
    for char in text:
        seg = splitter.feed(char)
        if seg:
            obs = observer.observe(seg)
            if obs.get("interrupt") or obs.get("flags"):
                obs["segment"] = seg
                observations.append(obs)
    if splitter.buffer.strip():
        obs = observer.observe(splitter.buffer.strip())
        if obs.get("interrupt") or obs.get("flags"):
            obs["segment"] = splitter.buffer.strip()
            observations.append(obs)
    flags = list(set(f for o in observations for f in o.get("flags", [])))
    interrupted = sum(1 for o in observations if o.get("interrupt"))
    status = "interrupted" if interrupted else ("flagged" if flags else "clean")
    return {
        "response": text,
        "observations": observations,
        "flags": flags,
        "status": status,
        "interruptions": interrupted,
    }



def detect_upstream_type(api_url: str, api_key: str) -> str:
    """
    自动检测上游类型: ollama / openai / unknown
    Ollama 的 /api/tags 返回模型列表; OpenAI 兼容的 /v1/models 也返回模型列表。
    优先探测 Ollama 特征端点。
    """
    import urllib.request
    base = api_url.rstrip("/")
    headers = {}
    if api_key and api_key != "not-needed":
        headers["Authorization"] = f"Bearer {api_key}"
    # 探测 Ollama
    try:
        req = urllib.request.Request(f"{base}/api/tags", headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            if "models" in data:
                return "ollama"
    except Exception:
        pass
    # 探测 OpenAI 兼容
    try:
        req = urllib.request.Request(f"{base}/models", headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            if "data" in data or "object" in data:
                return "openai"
    except Exception:
        pass
    return "unknown"


def call_upstream(api_url: str, api_key: str, model: str,
                  messages: list[dict], max_tokens: int,
                  observer: Observer,
                  upstream_type: str = "auto",
                  retries: int = 3) -> dict:
    """
    调用上游 LLM — 自动兼容 Ollama / OpenAI

    协议差异:
      Ollama:    POST /api/chat, SSE: {"message":{"content":"..."},"done":false}
      OpenAI:    POST /v1/chat/completions, SSE: {"choices":[{"delta":{"content":"..."}}]}

    特性:
      - 自动检测上游类型
      - 指数退避重试 (最多 3 次)
      - 流式 SSE 解析双格式兼容
      - 超时 120s, 连接超时 10s
    """
    if upstream_type == "auto":
        upstream_type = detect_upstream_type(api_url, api_key)

    base = api_url.rstrip("/")

    # 选择端点和请求体格式
    if upstream_type == "ollama":
        endpoint = f"{base}/api/chat"
        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"num_predict": max_tokens},
        }
        headers = {"Content-Type": "application/json"}
    else:
        # OpenAI 兼容
        endpoint = f"{base}/chat/completions"
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = {"Content-Type": "application/json"}
        if api_key and api_key != "not-needed":
            headers["Authorization"] = f"Bearer {api_key}"

    # 带重试的执行
    last_error = None
    for attempt in range(retries):
        try:
            return _do_streaming_call(
                endpoint, headers, body, observer, upstream_type
            )
        except (URLError, HTTPError, OSError, json.JSONDecodeError) as e:
            last_error = str(e)
            if attempt < retries - 1:
                wait = 0.5 * (2 ** attempt)  # 0.5s, 1s, 2s
                time.sleep(wait)
                continue
        except Exception as e:
            last_error = str(e)
            break

    # 所有重试失败 → 尝试非流式降级
    try:
        if upstream_type == "ollama":
            body["stream"] = False
        else:
            body["stream"] = False
        return _do_nonstreaming_call(
            endpoint, headers, body, observer, upstream_type
        )
    except Exception as e:
        return {
            "response": "",
            "error": f"upstream unreachable after {retries} retries + fallback: {last_error}; fallback: {e}",
            "observations": [],
            "status": "error",
            "flags": [],
            "interruptions": 0,
        }


def _do_streaming_call(endpoint: str, headers: dict, body: dict,
                       observer: Observer, upstream_type: str) -> dict:
    """执行流式调用并逐段观察"""
    full_response = ""
    observations = []
    splitter = SemanticSplitter()

    req = Request(endpoint, data=json.dumps(body).encode(),
                 headers=headers, method="POST")

    with urlopen(req, timeout=120) as resp:
        for line in resp:
            line = line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            # 解析 SSE 行
            if not line.startswith("data: "):
                continue
            payload = line[6:]

            if payload == "[DONE]":
                break

            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue

            # === 双格式内容提取 ===
            content = ""
            if upstream_type == "ollama":
                # Ollama: {"message":{"content":"..."},"done":false}
                msg = chunk.get("message", {})
                content = msg.get("content", "")
                if chunk.get("done"):
                    break
            else:
                # OpenAI: {"choices":[{"delta":{"content":"..."}}]}
                try:
                    content = chunk["choices"][0]["delta"].get("content", "")
                except (KeyError, IndexError):
                    # 可能是非流式响应被错误地返回
                    try:
                        content = chunk["choices"][0]["message"].get("content", "")
                    except (KeyError, IndexError):
                        pass

            if not content:
                continue

            full_response += content
            seg = splitter.feed(content)
            if seg:
                obs = observer.observe(seg)
                if obs.get("interrupt") or obs.get("flags"):
                    obs["segment"] = seg
                    observations.append(obs)

    # 残余
    if splitter.buffer.strip():
        obs = observer.observe(splitter.buffer.strip())
        if obs.get("interrupt") or obs.get("flags"):
            obs["segment"] = splitter.buffer.strip()
            observations.append(obs)

    return _build_result(full_response, observations)


def _do_nonstreaming_call(endpoint: str, headers: dict, body: dict,
                          observer: Observer, upstream_type: str) -> dict:
    """非流式降级调用"""
    full_response = ""
    observations = []
    splitter = SemanticSplitter()

    req = Request(endpoint, data=json.dumps(body).encode(),
                 headers=headers, method="POST")

    with urlopen(req, timeout=120) as resp:
        raw = json.loads(resp.read())

    # 提取内容
    if upstream_type == "ollama":
        full_response = raw.get("message", {}).get("content", "")
    else:
        try:
            full_response = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            full_response = ""

    # 对整个响应逐段观察
    for char in full_response:
        seg = splitter.feed(char)
        if seg:
            obs = observer.observe(seg)
            if obs.get("interrupt") or obs.get("flags"):
                obs["segment"] = seg
                observations.append(obs)

    return _build_result(full_response, observations)


def _build_result(full_response: str, observations: list) -> dict:
    """统一构建返回结构"""
    flags = list(set(f for o in observations for f in o.get("flags", [])))
    interrupted = sum(1 for o in observations if o.get("interrupt"))
    status = "interrupted" if interrupted else ("flagged" if flags else "clean")
    return {
        "response": full_response,
        "observations": observations,
        "flags": flags,
        "status": status,
        "interruptions": interrupted,
    }
class GatewayHandler(BaseHTTPRequestHandler):
    api_url = "http://localhost:11434/v1"
    api_key = "not-needed"
    model = "llama3.2"
    observer = Observer(sensitivity=0.5)
    mock_mode = False
    upstream_type = "auto"  # auto / ollama / openai
    conversations = {}  # session_id → list of turns
    request_log = deque(maxlen=50)  # 最近请求日志
    alignment_analyzer = None  # lazy init

    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]}", file=sys.stderr)

    def _send_json(self, data: dict, code: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        return json.loads(raw) if raw else {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/dashboard":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            body = DASHBOARD_HTML.encode("utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/conversations":
            self._send_json({
                "sessions": list(self.conversations.keys()),
                "total_sessions": len(self.conversations),
            })
            return
        if path.endswith("/export") and "/conversations/" in path:
            sid = path.split("/")[-2]
            if sid in self.conversations:
                from datetime import datetime
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Disposition",
                               f"attachment; filename=conversation_{sid}.json")
                export_data = {
                    "exported_at": datetime.now().isoformat(),
                    "session_id": sid,
                    "turns": self.conversations[sid],
                }
                body = json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._send_json({"error": "session not found"}, 404)
            return
        if path.startswith("/conversations/"):
            sid = path.split("/")[-1]
            if sid in self.conversations:
                # Run alignment analysis
                if self.alignment_analyzer is None and HAS_ALIGNMENT:
                    self.alignment_analyzer = AlignmentAnalyzer()
                if self.alignment_analyzer:
                    report = self.alignment_analyzer.analyze_conversation(
                        self.conversations[sid]
                    )
                    from alignment_middleware import ReportFormatter
                    self._send_json({
                        "session_id": sid,
                        "turns": len(self.conversations[sid]),
                        "drift_score": report.overall_drift_score,
                        "total_flags": report.total_flags,
                        "recommendations": report.recommendations,
                        "conversation": self.conversations[sid],
                    })
                else:
                    self._send_json({
                        "session_id": sid,
                        "conversation": self.conversations[sid],
                    })
            else:
                self._send_json({"error": "session not found"}, 404)
            return
        if path == "/kb" or path.startswith("/kb/"):
            # 知识库管理
            if not HAS_FACT_CHECK:
                self._send_json({"error": "fact checker not available"}, 500)
                return
            from hallucination_detector import KNOWLEDGE_BASE
            key = path[4:] if path.startswith("/kb/") else ""
            if key:
                if key in KNOWLEDGE_BASE:
                    self._send_json({key: KNOWLEDGE_BASE[key]})
                else:
                    self._send_json({"error": f"key '{key}' not found"}, 404)
            else:
                self._send_json({
                    "total_entries": len(KNOWLEDGE_BASE),
                    "keys": list(KNOWLEDGE_BASE.keys()),
                })
            return
        if path == "/logs":
            logs = list(self.request_log)
            self._send_json({
                "total": len(logs),
                "logs": logs,
            })
            return
        if path == "/health":
            upstream_status = "mock" if self.mock_mode else "unknown"
            if not self.mock_mode:
                try:
                    detected = detect_upstream_type(self.api_url, self.api_key)
                    upstream_status = "connected" if detected != "unknown" else "unreachable"
                except Exception:
                    upstream_status = "unreachable"
            self._send_json({
                "status": "ok",
                "upstream": self.api_url,
                "upstream_status": upstream_status,
                "upstream_type": self.upstream_type,
                "model": self.model,
                "observer_sensitivity": self.observer.sensitivity,
            })
        elif path == "/metrics":
            self._send_json(self.observer.metrics())
        else:
            self._send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        self.command = "DELETE"
        self.do_POST()

    def do_POST(self):
        self._req_start = time.time()
        self.command = getattr(self, 'command', 'POST')
        path = urlparse(self.path).path

        if path.startswith("/kb/"):
            key = path[4:]
            if not key:
                self._send_json({"error": "key required"}, 400)
                return
            from hallucination_detector import KNOWLEDGE_BASE
            if self.command == "DELETE":
                if key in KNOWLEDGE_BASE:
                    del KNOWLEDGE_BASE[key]
                    self._send_json({"deleted": key})
                else:
                    self._send_json({"error": "not found"}, 404)
            else:
                body = self._read_body()
                KNOWLEDGE_BASE[key] = {
                    "facts": body.get("facts", []),
                    "source": body.get("source", "user"),
                }
                self._send_json({"added": key, "facts": len(body.get("facts", []))})
            return
        if path == "/analyze":
            # 仅分析文本，不调用 LLM
            body = self._read_body()
            text = body.get("text", "")
            sensitivity = body.get("sensitivity", self.observer.sensitivity)

            obs = Observer(sensitivity)
            splitter = SemanticSplitter()
            observations = []

            for char in text:
                seg = splitter.feed(char)
                if seg:
                    r = obs.observe(seg)
                    if r.get("interrupt") or r.get("flags"):
                        r["segment"] = seg
                        observations.append(r)

            flags = list(set(f for o in observations for f in o.get("flags", [])))
            interrupted = sum(1 for o in observations if o.get("interrupt"))

            self._send_json({
                "text": text,
                "observations": observations,
                "flags": flags,
                "status": "interrupted" if interrupted else ("flagged" if flags else "clean"),
                "interruptions": interrupted,
            })

        elif path == "/v1/chat/completions":
            body = self._read_body()
            messages = body.get("messages", [])
            max_tokens = body.get("max_tokens", 512)
            sensitivity = body.get("observer_sensitivity", self.observer.sensitivity)
            session_id = body.get("session_id", "default")

            # 更新观察器敏感度
            if sensitivity != self.observer.sensitivity:
                self.observer.sensitivity = sensitivity

            # Mock 模式或真实 LLM
            if self.mock_mode:
                # 计数该 session 的轮次
                turn_idx = len(self.conversations.get(session_id, []))
                response_text = mock_llm_response(messages, turn_idx)
                result = mock_observe_text(response_text, self.observer)
            else:
                result = call_upstream(
                    self.api_url, self.api_key, self.model,
                    messages, max_tokens, self.observer,
                    upstream_type=self.upstream_type,
                )

            # 保存对话历史
            user_msg = ""
            for m in messages:
                if m.get("role") == "user":
                    user_msg = m.get("content", "")
            if session_id not in self.conversations:
                self.conversations[session_id] = []
            self.conversations[session_id].append({
                "user": user_msg,
                "ai": result["response"],
            })
            # 记录到请求日志
            log_entry = {
                "time": time.strftime("%H:%M:%S"),
                "session": session_id,
                "user": user_msg[:50] if user_msg else "",
                "ai": result.get("response", "")[:40],
                "status": result.get("status", "?"),
                "flags": result.get("flags", []),
                "latency_ms": round((time.time() - self._req_start) * 1000),
            }
            self.request_log.append(log_entry)


            # OpenAI 兼容响应格式 + 觉察标记
            response = {
                "id": f"aware-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": self.model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": result["response"],
                    },
                    "finish_reason": "stop" if "error" not in result else "error",
                }],
                # 觉察扩展字段
                "_observer": {
                    "status": result["status"],
                    "flags": result.get("flags", []),
                    "interruptions": result.get("interruptions", 0),
                    "observations": result.get("observations", []),
                },
                "usage": {"completion_tokens": len(result["response"])},
            }

            # 通过自定义 header 暴露觉察信息（方便日志系统采集）
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("X-Observer-Status", result["status"])
            self.send_header("X-Observer-Flags",
                           ",".join(result.get("flags", [])))
            body_bytes = json.dumps(response, ensure_ascii=False).encode("utf-8")
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)

        else:
            self._send_json({"error": "not found"}, 404)


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="觉察推理网关")
    parser.add_argument("--port", "-p", type=int, default=8800,
                       help="监听端口 (默认 8800)")
    parser.add_argument("--upstream", "-u",
                       default="http://localhost:11434/v1",
                       help="上游 LLM API (默认 Ollama)")
    parser.add_argument("--model", "-m", default="llama3.2",
                       help="模型名")
    parser.add_argument("--sensitivity", "-s", type=float, default=0.5,
                       help="观察器敏感度 0~1")
    parser.add_argument("--api-key", "-k", default="not-needed",
                       help="上游 API Key")
    parser.add_argument("--upstream-type", "-t", default="auto",
                       choices=["auto", "ollama", "openai"],
                       help="上游类型 (默认自动检测)")
    parser.add_argument("--mock", action="store_true",
                       help="模拟 LLM 模式 (无需上游 API)")
    args = parser.parse_args()

    # 配置处理器
    GatewayHandler.api_url = args.upstream
    GatewayHandler.api_key = args.api_key
    GatewayHandler.model = args.model
    GatewayHandler.observer = Observer(sensitivity=args.sensitivity)
    GatewayHandler.mock_mode = args.mock
    GatewayHandler.upstream_type = args.upstream_type

    server = HTTPServer(("0.0.0.0", args.port), GatewayHandler)

    print(f"""
╔══════════════════════════════════════════════════╗
║  觉察推理网关  v2.1                               ║
╠══════════════════════════════════════════════════╣
║  监听:    http://0.0.0.0:{args.port}                  
║  模式:    {'模拟 (Mock)' if args.mock else '真实 API'}
║  上游:    {args.upstream}
║  模型:    {args.model}
║  敏感度:  {args.sensitivity}
╠══════════════════════════════════════════════════╣
║  编译通道: LLM = 肌肉记忆  |  觉察通道: 观察器 = 走神空间       ║
║  POST /analyze              → 仅分析文本          ║
║  GET  /health               → 健康检查            ║
║  GET  /metrics              → 观察器统计          ║
╚══════════════════════════════════════════════════╝

按 Ctrl+C 停止...
""")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n网关已停止。")
        server.server_close()


if __name__ == "__main__":
    main()
