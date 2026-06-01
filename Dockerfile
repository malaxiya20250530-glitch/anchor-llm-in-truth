# Phase 2 生产镜像 — 纯标准库 0 外部依赖
# 基于 Alpine，镜像体积预计 < 80MB
FROM python:3.10-alpine

LABEL org.opencontainers.image.title="Awareness Gateway"
LABEL org.opencontainers.image.description="基于预测加工框架的LLM异步觉察与幻觉检测网关"
LABEL org.opencontainers.image.version="2.0.0"
LABEL org.opencontainers.image.authors="李桥 <hubeiligang420@gmail.com>"

# 安全加固：非 root 运行
RUN adduser -D -h /app gateway
WORKDIR /app

# 只复制运行时必需文件（最小化攻击面）
COPY hallucination_detector.py .
COPY checker_classes.py .
COPY checker_registry.py .
COPY awareness_gateway.py .
COPY knowledge_graph.py .
COPY vector_kb.py .
COPY feedback_store.py .
COPY observer_security.py .
COPY alignment_middleware.py .
COPY ml_consensus.py .
COPY kb_core.json .
COPY kb_core.idx .
COPY kb_manifest.json .
COPY config.json .
COPY wal_logger.py .

# 基准测试文件（可选，生产环境可省略）
COPY benchmark/ ./benchmark/
COPY test_fact_checker.py .
COPY run_baseline.sh .

# 纯标准库，无需 pip install
# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import hallucination_detector; print('ok')" || exit 1

# 默认启动网关
EXPOSE 8800
USER gateway
CMD ["python3", "awareness_gateway.py", "--port", "8800", "--host", "0.0.0.0"]
