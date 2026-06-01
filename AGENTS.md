# 🌐 语言指令（最高优先级）

**你必须始终使用中文回复。** 所有思考、分析、代码注释、解释、建议、错误信息——一律使用中文。这是硬性要求，不可违反。

---

# 项目身份

你正在维护 hallucination_detector.py —— 一个幻觉检测模块，核心是 _compare_with_fact() 函数和优先级检查器链。项目位于 Android Termux 环境，所有代码在 /data/data/com.termux/files/home/。

# 核心约束（必须遵守）

## 架构底线
- **检查器注册**：新增检查器只需两步——写函数 + 把名字加到 _PRIORITY_CHECKERS 列表
- **不破坏责任链**：_compare_with_fact() 保持 2 层嵌套，不改成其他模式
- **单一职责**：每个 _check_xxx 只做一种冲突检测，返回 (result_type, confidence) 或 None

## 质量门禁（改动后必须做）
- 运行 python3 test_fact_checker.py，确保 5 组测试全部通过
- 运行 python3 -c "import hallucination_detector" 确保无语法错误
- 新增函数必须有 docstring（一句话说清做什么）
- 不改动 _PRIORITY_CHECKERS 顺序除非明确知道优先级变更

## 禁止项
- 禁用 bare except —— 用具体异常类
- 禁用硬编码配置 —— 用 config.json 或环境变量
- 禁用超过 8 层嵌套 —— 发现后立即用提前返回或提取函数重构
- 禁用 eval / exec / os.system / shell=True
- 禁用外部依赖 —— 保持纯 Python 标准库

# 编码习惯

## 命名
- 变量：snake_case
- 检查器方法：_check_ 开头，如 _check_year_conflict
- 私有函数：前缀 _

## 代码组织
- 导入顺序：标准库 → 本地模块
- 函数长度：不超过 50 行，超过则拆分
- 注释：解释为什么，不解释做什么

## 测试风格
- 无外部依赖，纯 python3 test_fact_checker.py 运行
- 用列表驱动测试覆盖多个输入

# 决策记录
- 用责任链模式代替深层嵌套：13层嵌套无法维护 (2026-05-30)
- 检查器用列表注册而非类继承：简单直观新增成本低 (2026-05-30)
- 单元测试覆盖命中/未命中/优先级：为后续修改提供安全网 (2026-05-30)
- 同义词映射扩充知识库：突破关键词天花板 (2026-05-29)
- 双协议 Ollama/OpenAI SSE：网关对接真实 LLM (2026-05-29)

# 已完成
- 静态扫描 bare except 清零
- 嵌套 13→6（_compare_with_fact 拆为 5 个子检查器）
- 单元测试 221 行，5 组场景，全部通过
- _PRIORITY_CHECKERS 模块级常量提取
- 同义词映射 + bigram 语义回退
- 网关 Ollama 协议兼容

# 常用命令
- 单元测试: python3 test_fact_checker.py
- 语法检查: python3 -c "import hallucination_detector"
- 事实核查: python3 hallucination_detector.py "朱元璋发明了火锅"
- 启动网关: python3 awareness_gateway.py --port 8800 --mock
- 演示: bash demo_auto_captions.sh

# 🌐 中文化补充规则

## Git 提交信息
提交信息必须使用中文，格式：`类型: 简短描述`
- 类型：新增 / 修复 / 优化 / 重构 / 文档 / 测试 / 回滚
- 示例：`新增: 知识图谱模糊匹配层`

## 术语标准化
代码注释和解释中必须使用以下中文术语：
- function→函数, variable→变量, parameter→参数, return→返回
- exception→异常, error→错误, warning→警告, log→日志
- deploy→部署, rollback→回滚, benchmark→基准测试
- middleware→中间件, gateway→网关, observer→观察器
- checker→检查器, pipeline→流水线, buffer→缓冲区

## 文件引用格式
引用文件路径时使用反引号，如 `hallucination_detector.py`
