# 觉察推理网关

LLM 幻觉检测透明代理 — 夹在用户与 LLM 之间，实时拦截虚假信息。

## 快速开始

```bash
pip install git+https://github.com/malaxiya20250530-glitch/anchor-llm-in-truth.git
```

### 对接 Ollama

```bash
# 1. 确保 Ollama 在运行
ollama serve

# 2. 启动网关（自动检测上游类型）
awareness-gateway --port 8800 --upstream http://localhost:11434/v1 --model llama3.2
```

### 对接 OpenAI

```bash
awareness-gateway --port 8800 --upstream https://api.openai.com/v1 --api-key sk-xxx --model gpt-4o
```

### Mock 模式（无需 LLM）

```bash
awareness-gateway --port 8800 --mock
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/v1/chat/completions` | POST | OpenAI 兼容聊天接口 |
| `/api/chat` | POST | Ollama 兼容聊天接口 |
| `/ocr` | POST | OCR 截图检测 |
| `/uncertain` | GET | 不确定样本审核面板 |
| `/feedback` | GET | 反馈复核面板 |

## 检测管道

```
用户输入 → 责任链检查器 → 向量语义检索 → 联网交叉验证 → 结果
```

- **责任链**：快速否定、年份冲突、数值矛盾、来源缺失
- **向量检索**：BM25 + TF-IDF 混合检索知识库
- **联网验证**：DuckDuckGo + Wikipedia 并行交叉验证

## 模块

| 模块 | 说明 |
|------|------|
| `hallucination_detector.py` | 核心幻觉检测 |
| `awareness_gateway.py` | HTTP 网关（Ollama/OpenAI 双协议） |
| `vector_kb.py` | 向量知识库（BM25+TF-IDF） |
| `web_verifier.py` | 联网交叉验证（DuckDuckGo+Wikipedia） |
| `feedback_store.py` | SQLite 反馈数据库 |
| `feedback_dashboard.py` | Web 仪表盘 |
| `observer_proxy.py` | 安全观察代理 |
| `observer_security.py` | 安全策略观察器 |
| `alignment_middleware.py` | 对齐中间件 |
| `ocr_handler.py` | OCR 截图检测 |
| `langchain_plugin.py` | LangChain 插件 |
| `encrypt_source.py` | 源码加密工具 |

## 配置

```json
{
  "port": 8800,
  "upstream_url": "http://localhost:11434/v1",
  "model": "llama3.2",
  "mock_mode": false
}
```

## 测试

```bash
python3 test_fact_checker.py
# 82 测试用例，全部通过
```
