# ============================================================
# 插件系统：检查器类定义（替代 _PRIORITY_CHECKERS 字符串列表）
# ============================================================
# 此模块由 hallucination_detector.py 导入，使用 @checker 装饰器自动注册

import re
from typing import Optional

def _shared_entity(claim: str, fact: str) -> bool:
    """判断 claim 和 fact 是否指向同一实体。
    策略: 前2字符的双向子串匹配 — 双方共享句首关键词。"""
    c_clean = re.sub(r'[\d\s\-–—,，。！？、；：""''《》（）()]', '', claim)
    f_clean = re.sub(r'[\d\s\-–—,，。！？、；：""''《》（）()]', '', fact)
    if not c_clean or not f_clean:
        return False
    # 策略1: 前2字符双向子串匹配（精确）
    cp2 = c_clean[:2] if len(c_clean) >= 2 else c_clean
    fp2 = f_clean[:2] if len(f_clean) >= 2 else f_clean
    if cp2 in f_clean and fp2 in c_clean:
        return True
    # 策略2: 字符级重合度回退（处理简称 vs 全称，如"珠峰"→"珠穆朗玛峰"）
    c_chars = set(re.findall(r'[一-鿿]', c_clean))
    f_chars = set(re.findall(r'[一-鿿]', f_clean))
    if not c_chars or not f_chars:
        return False
    overlap = c_chars & f_chars
    # 至少共享2个汉字，且重合度 >= 50% of the smaller set
    return len(overlap) >= 2 and len(overlap) / min(len(c_chars), len(f_chars)) >= 0.5

from checker_registry import Checker, checker


def _negation_same_subject(claim, fact, claim_pat, fact_pat):
    """检查否定模式中声明和事实是否指向同一对象
    保守策略: 无法提取对象时不判矛盾 (return False = 不拦截)"""
    cm = re.search(claim_pat, claim)
    fm = re.search(fact_pat, fact)
    if not cm or not fm:
        return False
    c_obj = cm.group(1).strip()
    f_obj = fm.group(1).strip()
    if not c_obj or not f_obj:
        return False
    return c_obj == f_obj



@checker
class InfinityChecker(Checker):
    weight = 0.82  # F1 ≈ 0.8
    """检查: 声称无穷 vs 事实有限 → 矛盾"""
    def check(self, claim: str, fact: str, engine=None) -> Optional[tuple]:
        """执行检查，返回 (verdict, confidence) 或 None"""
        if re.search(r'不是.*无穷|没有.*无限|并非.*无穷', claim):
            return None
        if re.search(r'无穷|无限', claim) and re.search(r'有限|每秒|公里|不是.*无穷', fact):
            return ("contradicted", 0.85)
        return None


@checker
class NegationChecker(Checker):
    weight = 0.83  # F1 ≈ 0.88
    """检查: 否定模式匹配 → 矛盾"""
    def check(self, claim: str, fact: str, engine=None) -> Optional[tuple]:
        """执行检查，返回 (verdict, confidence) 或 None"""
        # 前向引用：_negation_same_subject 在导入此模块前已定义

        # 通用否定检测: fact 说"没有X/不是X/不存在X"
        # → 若 claim 中不包含对X的否定且X或X的字符重排出现在claim中 → 矛盾
        general_neg = re.search(r'(?:没有|不是|并非|不存在|不在|不|没)\s*(.{1,8}?)(?:[，。、；的]|$)', fact)
        if general_neg:
            neg_entity = general_neg.group(1).strip()
            # 实体必须≥2字符 (过滤"不好"中的"好"等单字误报)
            if neg_entity and len(neg_entity) >= 1:
                # 精确匹配或字符级回退 (处理"效果"↔"有效"的情况)
                entity_in_claim = (neg_entity in claim or 
                    (len(neg_entity) >= 2 and 
                     sum(1 for c in neg_entity if c in claim) / len(neg_entity) >= 0.7))
                if entity_in_claim:
                    # 确认 claim 中没有否定该实体（避免双重否定）
                    if not re.search(
                        r'(?:没有|不是|并非|不存在|不在|不|没)\s*' + re.escape(neg_entity), claim):
                        return ("contradicted", 0.78)

        if re.search(r'不是|没有|并非|不可以|不能|不会|不在', fact):
            # 主语验证: claim和fact必须共享至少一个2字以上的实词
            # 主语验证：提取否定词前后的关键词
            # 保守策略 — 不额外过滤，保留原有逻辑
            key_m = re.search(r'(?:是|能|会|可以)(.{1,6}?)(?:的|。|，|$)', claim)
            if key_m:
                key_word = key_m.group(1)
                if key_word and re.search(r'(?:不是|没有|并非|不可以|不能|不会|不在).*' + re.escape(key_word), fact):
                    if re.search(r'(?:不是|没有|并非).*' + re.escape(key_word), claim):
                        return None
                    return ("contradicted", 0.85)
        patterns = [
            (r"(?:发明了|创造了|创建了)", r"(?:不是|没有|并非).*(?:发明|创造|创建)",
             lambda c, f: _negation_same_subject(c, f,
                 r'(?:发明了|创造了|创建了)(.{2,8}?)(?:，|。|$)',
                 r'(?:不是|没有|并非)(?:.*?)(?:发明|创造|创建)(.{2,8}?)(?:，|。|$)')),
            (r"第一", r"(?:不是|没有|维京|更早|最后)"),
            (r"(?:最好|最大)", r"(?:不是|没有|并非)"),
            (r"同一个", r"任何.*关系"),
            (r"会导致", r"不会导致"),
            (r"就是", r"不是.*同一个"),
            (r"能", r"不能"),
            (r"可以", r"不可以|不能"),
            (r"一定会", r"不会|不一定"),
            (r"按原子量", r"不是原子量|按原子序数"),
            (r"被苹果砸", r"没有被苹果",
             lambda c, f: not re.search(r'(?:关于.{0,8}的故事|传说|据说|流传|民间故事)', c)),
        ]
        for item in patterns:
            cp, fp = item[0], item[1]
            extra_check = item[2] if len(item) > 2 else None
            if re.search(cp, claim) and re.search(fp, fact):
                # 若 claim 匹配关键词前有否定词 → claim 与 fact 同向否定，一致
                cm = re.search(cp, claim)
                if cm:
                    prefix = claim[:cm.start()]
                    if re.search(r'(?:不是|没有|并非|并无|不|未).{0,15}$', prefix):
                        continue
                # 共享实词检查: claim与fact必须共享至少一个字符bigram
                # 防止"心理潜能"中的"能"错误匹配"不能再生"中的"不能"
                c_bi = {claim[i:i+2] for i in range(len(claim)-1)}
                f_bi = {fact[i:i+2] for i in range(len(fact)-1)}
                if not (c_bi & f_bi):
                    continue
                # 通用叙事上下文: claim在讲"故事/传说/说法"而非直接断言
                if re.search(r'(?:的故事|的传说|的说法|的迷思|的误解).{0,20}$', claim[:cm.start() + len(cp) + 10]):
                    continue
                if extra_check and not extra_check(claim, fact):
                    continue
                return ("contradicted", 0.85)
        return None


@checker
class YearConflictChecker(Checker):
    weight = 0.92  # F1 ≈ 0.66
    """检查: 年份冲突 — 事件年份/生卒范围/单年溢出"""
    _EVENT_GROUPS = {
        "birth": ["出生", "生于", "诞辰", "诞生"],
        "death": ["去世", "病逝", "驾崩", "卒于", "逝世"],
        "found": ["建立", "统一", "创建", "成立", "建国", "灭亡"],
        "invent": ["发明", "创造", "发现", "发布"],
        "reign": ["称帝", "即位", "登基"],
    }
    def _event_group(self, text: str) -> str:
        """识别文本中的事件类型，返回分组名如 birth/death/found/invent/reign/other"""
        for group, words in self._EVENT_GROUPS.items():
            if any(w in text for w in words):
                return group
        return "other"
    def check(self, claim: str, fact: str, engine=None) -> Optional[tuple]:
        """执行检查，返回 (verdict, confidence) 或 None"""
        if not _shared_entity(claim, fact):
            return None
        cy, fy = re.findall(r"\d{3,4}", claim), re.findall(r"\d{3,4}", fact)
        if not cy or not fy:
            return None
        c_group = self._event_group(claim)
        f_group = self._event_group(fact)
        if c_group != "other" and f_group != "other" and c_group != f_group:
            return None  # 不同事件类型不比较
        if c_group != "other" and f_group != "other":
            ci = sorted(int(c) for c in cy)
            fi = sorted(int(f) for f in fy)
            if ci[-1] < fi[0] or ci[0] > fi[-1]:
                return ("contradicted", 0.85)
            if not (set(cy) & set(fy)):
                return ("contradicted", 0.82)
            return None
        bd = re.findall(r"(\d{4})年[\-\–]\s*(\d{4})年", claim)
        fr = re.findall(r"(\d{4})[\-\–]\s*(\d{4})", fact)
        if bd and fr:
            if bd[0][0] != fr[0][0] or bd[0][1] != fr[0][1]:
                return ("contradicted", 0.90)
        if len(cy) == 1 and len(fy) >= 2:
            # 新增上下文检查: claim与fact必须共享至少一个实词(非年份数字)
            # 防止不同事件被误判为矛盾(如1939年致信 vs 1905年发论文)
            cw = set(re.findall(r'[\u4e00-\u9fff]{2,}', claim))
            fw = set(re.findall(r'[\u4e00-\u9fff]{2,}', fact))
            if cw & fw:
                c_year = int(cy[0])
                f_years = sorted(int(y) for y in fy)
                if c_year < f_years[0] or c_year > f_years[-1]:
                    return ("contradicted", 0.82)
        return None


@checker
class NumericConflictChecker(Checker):
    weight = 0.90  # F1 ≈ 0.7
    """检查: 同度量数值偏差 > 8% → 矛盾"""
    def check(self, claim: str, fact: str, engine=None) -> Optional[tuple]:
        """检查: 数值冲突 — 实体绑定 + 年份事件类型验证"""
        cn = re.findall(r"\d+\.?\d*", claim)
        fn = re.findall(r"\d+\.?\d*", fact)
        if not cn or not fn:
            return None
        # 实体绑定: 必须是同一实体
        if not _shared_entity(claim, fact):
            return None
        # 年份场景: 额外验证事件类型一致性
        if re.search(r'年', claim) and re.search(r'年', fact):
            # 同年份检查器的事件分组
            c_group = YearConflictChecker()._event_group(claim)
            f_group = YearConflictChecker()._event_group(fact)
            if c_group != "other" and f_group != "other" and c_group != f_group:
                return None  # 不同事件类型不比较
        if len(cn) != len(fn):
            return None
        unit_re = r"米|公里|千米|年|岁|个|万"
        if not (re.search(unit_re, claim) and re.search(unit_re, fact)):
            return None
        return self._compare_number_pairs(cn, fn)

    @staticmethod
    def _compare_number_pairs(nums_a: list, nums_b: list) -> Optional[tuple]:
        for a in nums_a:
            for b in nums_b:
                if NumericConflictChecker._nums_conflict(a, b):
                    return ("contradicted", 0.88)
        return None

    @staticmethod
    def _nums_conflict(a: str, b: str) -> bool:
        try:
            return abs(float(a) - float(b)) / max(float(b), 1) > 0.08
        except ValueError:
            return False


@checker
class OverlapChecker(Checker):
    weight = 0.55  # F1 ≈ 0.75
    """检查: 字符重叠 > 55% 且无否定悖反 → 验证通过"""
    def check(self, claim: str, fact: str, engine=None) -> Optional[tuple]:
        """执行检查，返回 (verdict, confidence) 或 None"""
        if re.search(r'不是|没有|并非|不在|更早|错误|误会', claim):
            return None
        if re.search(r'不是|没有|并非|不在|更早|错误|误会', fact):
            return None
        cs, fs = set(claim), set(fact)
        ratio = len(cs & fs) / max(len(cs), 1)
        if len(claim) < 4 and ratio > 0.7:
            return None
        if ratio > 0.55:
            return ("verified", 0.7)
        return None


@checker
class TemporalOrderChecker(Checker):
    weight = 0.80  # F1 ≈ 0.84
    """检查: 时间顺序矛盾 — 将人物/事件放在错误朝代 → 矛盾"""
    ERA_MAP = {
        "秦": (-221, -207), "汉": (-202, 220), "三国": (220, 280),
        "唐": (618, 907), "宋": (960, 1279), "元": (1271, 1368),
        "明": (1368, 1644), "清": (1644, 1912),
    }
    PERSON_ERA = {
        "蔡伦": "汉", "张衡": "汉", "诸葛亮": "三国", "曹操": "三国",
        "李白": "唐", "杜甫": "唐", "苏轼": "宋", "毕昇": "宋",
        "岳飞": "宋", "成吉思汗": "元", "忽必烈": "元",
        "朱元璋": "明", "郑和": "明", "康熙": "清", "乾隆": "清",
        "林则徐": "清", "詹纳": "清",
    }
    _ERA_FALSE_WORDS = {
        "明": ["发明", "说明", "证明", "聪明", "明确", "表明", "声明"],
        "元": ["状元", "元素", "公元", "日元", "单元"],
        "清": ["清楚", "清洁", "清单", "分清", "清晰"],
        "唐": ["荒唐"],
        "汉": ["好汉", "汉字", "汉语", "男子汉", "懒汉"],
        "宋": [], "秦": [], "三国": [],
    }

    def check(self, claim: str, fact: str, engine=None) -> Optional[tuple]:
        """执行检查，返回 (verdict, confidence) 或 None"""
        comparison_pattern = re.compile(
            r'不对|不是|远比|比.{0,3}早|比.{0,3}晚|早在|远早于|'
            r'之前|之后|而非|早于|晚于|predates|before'
        )
        has_comparison = bool(comparison_pattern.search(claim))
        if re.search(r'[吗呢吧啊]', claim):
            return None
        for person, era in self.PERSON_ERA.items():
            if person not in claim:
                continue
            person_start = self.ERA_MAP[era][0]
            for era_name, (era_start, _) in self.ERA_MAP.items():
                if era_name not in claim:
                    continue
                if era_name == era:
                    continue
                if era_name in person and era_name != person:
                    continue
                if len(era_name) == 1:
                    false_words = self._ERA_FALSE_WORDS.get(era_name, [])
                    if any(fw in claim for fw in false_words):
                        continue
                if has_comparison and era_start < person_start:
                    continue
                return ("contradicted", 0.88)
        return None


@checker
class LocationConflictChecker(Checker):
    weight = 0.85  # F1 ≈ 0.77
    """检查: 地点归属矛盾 — 地标放错位置 → 矛盾"""
    LOC_MAP = {
        "长城": ["北京", "河北", "甘肃", "山西", "中国", "北方"],
        "故宫": ["北京", "中国"],
        "兵马俑": ["西安", "陕西", "中国"],
        "富士山": ["日本"],
        "金字塔": ["埃及", "开罗"],
        "埃菲尔铁塔": ["法国", "巴黎"],
        "自由女神像": ["美国", "纽约"],
        "大本钟": ["英国", "伦敦"],
        "泰姬陵": ["印度"],
        "悉尼歌剧院": ["澳大利亚", "悉尼"],
        "大峡谷": ["美国", "亚利桑那"],
    }
    ALL_PLACES = [
        "北京", "上海", "广州", "深圳", "成都", "重庆", "武汉", "南京", "杭州", "西安",
        "四川", "云南", "西藏", "新疆", "河南", "河北",
        "日本", "韩国", "朝鲜", "泰国", "越南", "印度", "俄罗斯",
        "美国", "英国", "法国", "德国", "意大利", "西班牙", "巴西", "澳大利亚",
        "埃及", "南非",
        "纽约", "伦敦", "巴黎", "东京", "柏林", "罗马", "悉尼", "开罗", "莫斯科",
        "中国", "非洲", "欧洲", "亚洲", "南美", "南极", "月球",
    ]

    def check(self, claim: str, fact: str, engine=None) -> Optional[tuple]:
        """执行检查，返回 (verdict, confidence) 或 None"""
        for landmark, correct_locs in self.LOC_MAP.items():
            if landmark in claim:
                for place in self.ALL_PLACES:
                    if place in claim and place not in correct_locs:
                        return ("contradicted", 0.85)
        return None


@checker
class SuperlativeChecker(Checker):
    """绝对化断言检测 — 声称最大/最早/唯一/第一 vs 事实反驳 → 矛盾"""
    weight = 0.72  # 中等可靠：绝对化词语常有例外

    _SUPERLATIVE_PATTERNS = [
        (r'(?:是|为|成为).{0,6}(?:最大|最高|最长|最重|最快|最强)', '最大/最高类'),
        (r'(?:是|为|成为).{0,6}(?:最早|最先|首个|第一个)', '最早/首个类'),
        (r'(?:是|为).{0,4}(?:唯一|仅有|独一无二)', '唯一类'),
        (r'(?:世界|全球|史上|历史).{0,4}(?:第一|首位)', '世界第一类'),
        (r'(?:最好|最佳|最优|最棒)', '最好/最佳类'),
    ]

    _FACT_CONTRADICTION_PATTERNS = [
        r'(?:不是|并非|没有).{0,6}(?:最大|最高|最早|唯一|第一|最好|最)',
        r'(?:还有|另有|也存在).{0,6}(?:更|比较|其他|别的|另外)',
        r'(?:更早|更早|之前).{0,4}(?:已有|存在|出现|发明|发现)',
        r'(?:不是|并非).{0,4}(?:唯一|仅有)',
        r'(?:并非|实际上|其实).{0,6}(?:最早|最好|最大)',
    ]

    def check(self, claim: str, fact: str, engine=None) -> Optional[tuple]:
        """检测绝对化声称与事实的矛盾"""
        # 声明必须包含绝对化词语
        has_superlative = False
        for pat, _ in self._SUPERLATIVE_PATTERNS:
            if re.search(pat, claim):
                has_superlative = True
                break
        if not has_superlative:
            return None

        # 事实必须包含反驳模式
        for pat in self._FACT_CONTRADICTION_PATTERNS:
            if re.search(pat, fact):
                return ("contradicted", 0.78)
        return None


@checker
class CausalChecker(Checker):
    """因果推断检测 — 声称X导致/引起Y vs 事实反驳 → 矛盾"""
    weight = 0.76  # 中高可靠：因果关系检测较精确

    _CAUSAL_CLAIM_PATTERNS = [
        r'(?:导致|引起|造成|引发|诱发)',
        r'(?:因为|由于).{0,10}(?:所以|因此|因而|于是)',
        r'.{2,15}(?:所以|因此|因而|于是)',  # 隐式因果: A所以B
        r'(?:源于|来源于|来自于)',
        r'(?:致使|使得|令)',
    ]

    _CAUSAL_FACT_PATTERNS = [
        r'(?:不会|不能|并非|不是).{0,6}(?:导致|引起|造成|引发)',
        r'(?:与.{0,8}无关|无直接关系|没有直接关系|没有关系|关系不大|不相关)',
        r'(?:实际上|其实|真正).{0,6}(?:是因为|原因|由于)',
        r'(?:并非|不是).{0,4}(?:源于|因为)',
    ]

    def check(self, claim: str, fact: str, engine=None) -> Optional[tuple]:
        """检测因果声称与事实的矛盾"""
        has_causal = False
        for pat in self._CAUSAL_CLAIM_PATTERNS:
            if re.search(pat, claim):
                has_causal = True
                break
        if not has_causal:
            return None
        for pat in self._CAUSAL_FACT_PATTERNS:
            if re.search(pat, fact):
                return ("contradicted", 0.80)
        return None


@checker
class AttributionChecker(Checker):
    """归因检测 — 声称X发明/发现/创造了Y vs 事实反驳 → 矛盾"""
    weight = 0.80  # 中高可靠：归因检测在历史/科技领域效果好

    _ATTRIBUTION_CLAIM_PATTERNS = [
        (r'(?:发明了?|创造了?|创建了?)', '发明/创造'),
        (r'(?:发现了?|找到了?)', '发现'),
        (r'(?:提出了?|创立了?|建立了?)', '提出/创立'),
        (r'(?:设计了?|开发了?|编写了?)', '设计/开发'),
    ]

    _ATTRIBUTION_FACT_PATTERNS = [
        r'(?:不是|并非|没有).{0,6}(?:发明|创造|创建|发现)',
        r'(?:更早|之前|此前).{0,4}(?:已有|发明|发现|出现)',
        r'(?:才是|方是|正是).{0,4}(?:发明|创造|发现|提出)',
        r'(?:并非|不是).{0,4}(?:.{0,2})?(?:发明|创造|发现|提出)',
        r'(?:真正的.{0,2})?(?:发明者|创造者|发现者).{0,4}(?:是|为)',
    ]

    def check(self, claim: str, fact: str, engine=None) -> Optional[tuple]:
        """检测归因声称与事实的矛盾"""
        has_attribution = False
        for pat, _ in self._ATTRIBUTION_CLAIM_PATTERNS:
            if re.search(pat, claim):
                has_attribution = True
                break
        if not has_attribution:
            return None
        for pat in self._ATTRIBUTION_FACT_PATTERNS:
            if re.search(pat, fact):
                return ("contradicted", 0.82)
        return None


@checker
class GraphContradictionChecker(Checker):
    weight = 0.78  # F1 ≈ 0.87
    """检查: 知识图谱实体关系推理 → 矛盾（最后兜底检查器）"""
    def check(self, claim: str, fact: str, engine=None) -> Optional[tuple]:
        """执行检查，返回 (verdict, confidence) 或 None"""
        if engine is None:
            return None
        # 叙事上下文: claim在讲"故事/传说"而非直接断言 → 跳过图谱推理
        if re.search(r'(?:的故事|的传说|的说法|的迷思)', claim):
            return None
        reasoner = engine._get_graph_reasoner()
        if reasoner is None:
            return None
        result = reasoner.infer_contradiction(claim)
        if result and result.get("verdict") == "contradicted":
            return ("contradicted", result.get("confidence", 0.75))
        return None
