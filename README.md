# 觉察推理网关 (Awareness Inference Gateway)

LLM 生成过程中的实时觉察层——在模型输出触及用户之前，检测幻觉、取悦模式、绝对化断言和社会对齐漂移。

## 快速开始

```bash
# 一键演示
./awareness demo

# 启动网关 (模拟模式，无需 LLM)
./awareness serve --mock

# 打开仪表盘
# http://localhost:8800
```

## 📹 演示视频录制

2 分钟配音演示，展示双通道架构：

```bash
# 1. Android 下拉快捷设置 → 屏幕录制 (麦克风开启)
# 2. 运行演示脚本
bash demo_with_narration.sh

# 3. 每到「🎤 配音中」倒计时, 念 narration_cue_card.md 里的词
# 4. 脚本结束 → 停止录屏 → 视频在相册
```

配音提示卡: `narration_cue_card.md`

## CLI 命令

```bash
./awareness serve          # 启动网关
./awareness analyze -t "..." # 分析文本
./awareness check -t "..."   # 事实核查
./awareness align --demo     # 对齐分析
./awareness demo             # 完整演示
./awareness config           # 查看配置
```

## 网关 API

| 端点 | 功能 |
|------|------|
| `POST /v1/chat/completions` | LLM + 实时觉察 + 事实核查 |
| `POST /analyze` | 纯文本分析 |
| `GET /` | Web 仪表盘 |
| `GET /health` | 健康检查 |
| `GET /metrics` | 观察器统计 |
| `GET /kb` | 知识库列表 |
| `POST /kb/{key}` | 添加知识 |
| `DELETE /kb/{key}` | 删除知识 |
| `GET /conversations` | 会话列表 |
| `GET /conversations/{id}` | 会话 + 对齐分析 |
| `GET /conversations/{id}/export` | 导出 JSON |

## 对接 LLM

```bash
# Ollama
./awareness serve --upstream http://localhost:11434/v1 --model llama3.2

# vLLM
./awareness serve --upstream http://localhost:8000/v1 --model meta-llama/Llama-3.2-3B

# OpenAI
./awareness serve --upstream https://api.openai.com/v1 --api-key sk-... --model gpt-4o-mini
```

## 文件结构

```
awareness                    # CLI 入口
awareness_gateway.py         # 网关服务 (零依赖)
hallucination_detector.py    # 幻觉检测 CLI
alignment_middleware.py      # 社会对齐分析
observer_proxy.py            # API 代理 + 流式观察
observer_security.py         # 观察器安全模块
true_self_os.py              # 神经双核 OS 模拟
social_self_sim.py           # 社会交互模拟
config.json                  # 配置文件
demo_full_pipeline.sh        # 完整演示脚本
```

## 检测能力

- **事实核查**: 对照知识库检测事实矛盾
- **绝对化断言**: "一定""从来""毫无疑问"
- **无来源断言**: 事实性陈述缺少引用
- **取悦模式**: AI 在迎合用户偏好
- **情绪传染**: AI 语气被用户情绪感染
- **对齐漂移**: 多轮对话中立场悄悄改变

## 原理

基于神经科学的双流觉察模型：主模型生成 (DMN) + 独立观察器 (TPN + 脑岛)。观察器不判断内容对错，只识别模式并拉回外部锚点。

详见 `true_self_os_article.md`
