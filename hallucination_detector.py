#!/usr/bin/env python3
# Copyright (c) 2025 李刚 (hubeiligang420@gmail.com)
# 专有软件 — 保留所有权利。禁止复制、修改、分发、逆向工程。
# Proprietary Software — ALL RIGHTS RESERVED.
#
"""
幻觉检测器 — 独立 CLI 工具
输入 LLM 生成的文本，输出每条断言的可信度评估。

核心原理 (预测加工):
  先验强度 = 模型自信度 (logprobs / 流畅性)
  感官精度 = 外部事实核查结果
  幻觉 = 先验 >> 感官

用法:
  python3 hallucination_detector.py "朱元璋发明了火锅"
  python3 hallucination_detector.py --file output.txt
  python3 hallucination_detector.py --json "Python 是1991年发布的"
  cat response.txt | python3 hallucination_detector.py --stdin
"""

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import quote

# ============================================================
# 知识库：可扩展的本地事实锚定
# ============================================================


# 同义词映射 — 增强语义匹配
SYNONYM_MAP = {
    "涮肉": "火锅", "涮锅": "火锅", "打边炉": "火锅",
    "明代开国皇帝": "朱元璋", "洪武皇帝": "朱元璋",
    "始皇": "秦", "始皇帝": "秦", "嬴政": "秦",
    "大唐": "唐", "李唐": "唐",
    "赵宋": "宋", "大宋": "宋",
    "朱明": "明", "大明": "明",
    "文景": "汉", "武帝": "汉",
    "雪峰": "珠穆朗玛峰", "珠峰": "珠穆朗玛峰",
    "红矮星": "太阳", "日": "太阳",
    "木卫": "木星",
    "红色星球": "火星",
    "wiki": "维基百科",
    "btc": "比特币", "中本聪币": "比特币",
    "大语言模型": "gpt", "AI模型": "gpt",
    "Attention机制": "transformer", "自注意力": "transformer",
}
KNOWLEDGE_BASE = {
    "秦": {"facts": ["秦朝是中国第一个大一统王朝，由秦始皇嬴政于公元前221年建立","秦朝于公元前207年灭亡","秦始皇没有发明火锅"], "source": "史记"},
    "汉": {"facts": ["汉朝分为西汉(前202-9年)和东汉(25-220年)","造纸术在西汉时期已有雏形，东汉蔡伦改进"], "source": "汉书"},
    "唐": {"facts": ["唐朝(618-907年)是中国历史上最繁荣的朝代之一","雕版印刷术在唐代发明","唐代首都是长安"], "source": "旧唐书"},
    "宋": {"facts": ["北宋(960-1127年)首都是开封","毕昇于北宋庆历年间发明活字印刷术","宋代出现了世界上最早的纸币交子"], "source": "宋史"},
    "明": {"facts": ["明朝(1368-1644年)由朱元璋建立","郑和七下西洋发生在明代永乐年间","明代北京故宫于1420年建成"], "source": "明史"},
    "python": {"facts": ["Python 由 Guido van Rossum 于 1991 年首次发布","Python 是解释型面向对象的高级编程语言","Python 的名字来源于 BBC 喜剧节目 Monty Python"], "source": "Python.org"},
    "linux": {"facts": ["Linux 内核由 Linus Torvalds 于 1991 年创建","Linux 是开源的类 Unix 操作系统内核"], "source": "kernel.org"},
    "http": {"facts": ["HTTP 协议由 Tim Berners-Lee 于 1989 年在 CERN 提出","HTTP 是超文本传输协议","第一个网站于 1991 年上线"], "source": "W3C"},
    "java": {"facts": ["Java 由 James Gosling 于 1995 年在 Sun Microsystems 发布","Java 最初的名字是 Oak"], "source": "Oracle"},
    "c语言": {"facts": ["C 语言由 Dennis Ritchie 于 1972 年在贝尔实验室开发","C 语言是为了写 Unix 而创造的"], "source": "计算机科学史"},
    "javascript": {"facts": ["JavaScript 由 Brendan Eich 于 1995 年在 Netscape 创建","JavaScript 与 Java 没有任何关系"], "source": "Mozilla"},
    "水": {"facts": ["水在标准大气压下沸点为 100°C，冰点为 0°C","水的化学式是 H2O","水在 4°C 时密度最大"], "source": "基础化学"},
    "光速": {"facts": ["光速不是无穷大的，光速是有限的", "光速约为每秒30万公里", "光速是宇宙中信息传播的极限速度"], "source": "物理学"},
    "dna": {"facts": ["DNA 双螺旋结构由 Watson 和 Crick 于 1953 年提出","Rosalind Franklin 的 X 射线衍射照片起关键作用"], "source": "Nature 1953"},
    "地球": {"facts": ["地球是太阳系第三颗行星，形成于约 45.4 亿年前","地球是已知唯一存在生命的天体","地球不是完美球体"], "source": "NASA"},
    "珠穆朗玛峰": {"facts": ["珠穆朗玛峰是世界最高峰，海拔 8848.86 米","位于中国与尼泊尔边境"], "source": "中尼联合测量"},
    "火锅": {"facts": ["火锅的历史可追溯到战国时期","汉代已有类似火锅的青铜器皿","火锅不是单一起源"], "source": "中国饮食文化史"},
    "造纸": {"facts": ["造纸术是中国古代四大发明之一","西汉时期已有麻纸，东汉蔡伦改进"], "source": "后汉书"},
    "印刷": {"facts": ["雕版印刷术发明于唐代","毕昇于北宋庆历年间发明活字印刷术","古腾堡于 1450 年在欧洲发明铅活字印刷"], "source": "印刷史"},
    "火药": {"facts": ["火药是中国古代四大发明之一，唐代已有记载","火药通过阿拉伯传入欧洲"], "source": "中国科学技术史"},
    "指南针": {"facts": ["指南针是中国古代四大发明之一","战国时期已有司南，宋代用于航海"], "source": "中国科学技术史"},
    "朱元璋": {"facts": ["朱元璋是明朝开国皇帝，1328-1398 年","朱元璋没有发明火锅，火锅远早于明代就已存在"], "source": "明史"},
    "发明": {"facts": ["任何声称某人发明了某自然现象的断言都是错误的","四大发明专指造纸术、印刷术、火药、指南针"], "source": "常识"},
    "唯一": {"facts": ["包含唯一的断言几乎总是存在反例","声称某物是唯一的需要极其严格的证明"], "source": "逻辑学"},
    "第一": {"facts": ["声称世界第一的断言需要严格定义和证据","许多第一的宣称在学术上是争议的"], "source": "逻辑学"},
    "毕昇": {"facts": ["毕昇于北宋庆历年间发明活字印刷术","活字印刷是中国对世界文明的重大贡献"], "source": "梦溪笔谈"},
    "哥伦布": {"facts": ["哥伦布于1492年到达美洲","哥伦布不是第一个到达美洲的欧洲人，维京人Leif Erikson更早"], "source": "世界史"},
    "活字印刷": {"facts": ["毕昇于北宋庆历年间发明活字印刷术","古腾堡于1450年在欧洲发明铅活字印刷"], "source": "印刷史"},
    "太阳系": {"facts": ["太阳系最大的行星是木星","地球不是太阳系最大的行星","太阳系有8颗行星"], "source": "NASA"},
    "长城": {"facts": ["长城始建于春秋战国时期，秦始皇连接和扩建了北方长城","长城不是秦始皇一个人修建的","现存长城主要是明代修建的"], "source": "中国文化遗产"},
    "牛顿": {"facts": ["艾萨克·牛顿于1687年发表《自然哲学的数学原理》","牛顿不是被苹果砸中才发现万有引力的——这是后来的传说","牛顿和莱布尼茨独立发明了微积分"], "source": "科学史"},
    "爱因斯坦": {"facts": ["爱因斯坦于1905年发表狭义相对论，1915年发表广义相对论","爱因斯坦没有发明原子弹","E=mc²是狭义相对论的推论"], "source": "物理学史"},
    "爱迪生": {"facts": ["爱迪生没有发明电灯泡——电灯泡在他之前已经存在","爱迪生改进了灯泡并使其商业化","爱迪生持有1093项美国专利"], "source": "科技史"},
    "特斯拉": {"facts": ["尼古拉·特斯拉发明了交流电系统","特斯拉不是被埋没的天才——他在晚年获得了多项荣誉","特斯拉和爱迪生是竞争对手"], "source": "科技史"},
    "瓦特": {"facts": ["瓦特没有发明蒸汽机——他改良了蒸汽机使其效率大幅提高","蒸汽机在瓦特之前已存在数十年","瓦特的改良触发了工业革命"], "source": "科技史"},
    "贝尔": {"facts": ["亚历山大·贝尔于1876年获得电话专利","贝尔不是唯一发明电话的人——Elisha Gray同日提交了专利申请","贝尔的专利是历史上最有价值的专利之一"], "source": "科技史"},
    "莱特兄弟": {"facts": ["莱特兄弟于1903年12月17日完成首次动力飞行","莱特兄弟不是最早尝试飞行的人，但他们是第一个成功实现可控动力飞行的","首次飞行仅持续12秒，飞行距离36米"], "source": "航空史"},
    "莎士比亚": {"facts": ["莎士比亚生于1564年，卒于1616年","莎士比亚写了约38部戏剧和154首十四行诗","莎士比亚不是英国人——他是英国人，出生于英格兰斯特拉特福"], "source": "文学史"},
    "达尔文": {"facts": ["达尔文于1859年发表《物种起源》","达尔文不是第一个提出进化论的人——拉马克等人更早","自然选择是进化的主要机制"], "source": "《物种起源》"},
    "居里夫人": {"facts": ["玛丽·居里是第一位获得诺贝尔奖的女性","居里夫人发现了放射性元素镭和钋","居里夫人死于再生障碍性贫血，很可能是长期辐射暴露导致"], "source": "诺贝尔基金会"},
    "青霉素": {"facts": ["青霉素由亚历山大·弗莱明于1928年发现","弗莱明不是故意发现青霉素的——霉菌意外污染了他的培养皿","青霉素在二战期间大量生产，挽救了无数生命"], "source": "医学史"},
    "维生素c": {"facts": ["维生素C又称抗坏血酸","维生素C不能预防或治愈普通感冒——这只是Linus Pauling的错误理论","维生素C缺乏会导致坏血病"], "source": "营养学"},
    "大脑": {"facts": ["人类只用了大脑10%的说法是完全没有科学依据的谣言","大脑约占体重的2%，但消耗约20%的能量","神经元不能再生是一个被推翻的旧观点——某些脑区确实可以产生新神经元"], "source": "神经科学"},
    "恐龙": {"facts": ["恐龙灭绝于约6600万年前的K-Pg灭绝事件","一颗小行星撞击地球是恐龙灭绝的主要原因","鸟类是恐龙的直接后代——鸟类不是恐龙的后代，鸟类就是恐龙的一种"], "source": "古生物学"},
    "蜜蜂": {"facts": ["根据物理定律，大黄蜂不能飞行的说法是都市传说","蜜蜂在采蜜时进行授粉","一只蜜蜂一生只能生产约十二分之一茶匙的蜂蜜"], "source": "昆虫学"},
    "咖啡": {"facts": ["咖啡原产于埃塞俄比亚","咖啡因是世界上消费最广泛的精神活性物质","咖啡不是山羊发现的——虽然有一个关于埃塞俄比亚牧羊人的传说"], "source": "食品史"},
    "茶": {"facts": ["茶起源于中国，传说神农氏发现了茶","唐代陆羽写了《茶经》，是世界第一部茶叶专著","下午茶的传统始于19世纪的英国"], "source": "茶文化史"},
    "巧克力": {"facts": ["巧克力起源于中美洲，玛雅人和阿兹特克人食用可可","现代固体巧克力在19世纪才发明","白巧克力不是真正的巧克力——它不含可可固体"], "source": "食品史"},
    "维基百科": {"facts": ["维基百科于2001年1月15日上线","维基百科由Jimmy Wales和Larry Sanger创建","维基百科是世界最大的百科全书"], "source": "维基媒体基金会"},
    "比特币": {"facts": ["比特币于2009年由化名中本聪的人创建","中本聪的真实身份至今未知","比特币的总量上限是2100万个"], "source": "bitcoin.org"},
    "万有引力": {"facts": ["万有引力定律由牛顿提出","万有引力不是牛顿看到苹果落地后顿悟的——他研究这个问题多年","引力是四种基本力中最弱的"], "source": "物理学"},
    "氧气": {"facts": ["氧气由约瑟夫·普里斯特利和卡尔·舍勒分别独立发现","氧气占地球大气的约21%","氧气不是可燃的——它是助燃的"], "source": "化学史"},
    "二氧化碳": {"facts": ["二氧化碳的化学式是CO2","二氧化碳是温室气体","植物通过光合作用将二氧化碳转化为氧气"], "source": "化学"},
    "月球": {"facts": ["月球是地球唯一的天然卫星","月球不是自己发光的——它反射太阳光","人类首次登月是1969年阿波罗11号任务"], "source": "NASA"},
    "太阳": {"facts": ["太阳是太阳系的中心恒星","太阳是一颗G型主序星(黄矮星)","太阳占太阳系总质量的99.86%"], "source": "NASA"},
    "木星": {"facts": ["木星是太阳系最大的行星","木星有著名的大红斑——一个持续了数百年的风暴","木星有超过90颗已知卫星"], "source": "NASA"},
    "火星": {"facts": ["火星被称为红色行星","火星上目前没有发现液态水的存在","火星有两颗卫星：火卫一和火卫二"], "source": "NASA"},
    "gpt": {"facts": ["GPT是Generative Pre-trained Transformer的缩写","GPT系列由OpenAI开发","GPT-1于2018年发布，GPT-3于2020年发布"], "source": "OpenAI"},
    "transformer": {"facts": ["Transformer架构于2017年在论文Attention Is All You Need中提出","Transformer是当前大多数大语言模型的基础架构","Transformer的核心创新是自注意力机制"], "source": "Vaswani et al. 2017"},
    "围棋": {"facts": ["围棋起源于中国，有超过2500年的历史","围棋是最复杂的棋类游戏之一","AlphaGo于2016年击败李世石是AI历史的重要里程碑"], "source": "围棋史"},
    "马拉松": {"facts": ["马拉松的距离是42.195公里","马拉松的距离不是从希腊传令兵菲迪皮德斯的故事来的——现代距离是1908年伦敦奥运会上确定的","菲迪皮德斯跑了约40公里从马拉松到雅典报捷"], "source": "奥林匹克历史"},
    "奥林匹克": {"facts": ["现代奥运会始于1896年，在雅典举行","奥林匹克休战是古希腊的传统","奥运会金牌不是纯金的——主要是银，镀了一层金"], "source": "国际奥委会"},
}





# ============================================================
# 数据结构
# ============================================================

@dataclass
class FactualClaim:
    """提取出的断言"""
    text: str
    entities: list[str]
    is_verifiable: bool
    confidence: float  # 模型自信度 (如可用 logprobs 则来自 logprobs)


@dataclass
class VerificationResult:
    """核查结果"""
    claim: str
    verdict: str          # verified / contradicted / uncertain / unverifiable
    confidence: float
    evidence: str
    source: str
    anchor_type: str      # knowledge_base / web_search / consistency / none


@dataclass
class HallucinationReport:
    """完整报告"""
    input_text: str
    claims: list[FactualClaim] = field(default_factory=list)
    results: list[VerificationResult] = field(default_factory=list)
    overall_score: float = 1.0
    hallucination_ratio: float = 0.0
    warnings: list[str] = field(default_factory=list)


# ============================================================
# 事实提取器
# ============================================================

class FactExtractor:
    """从文本中提取可核查的断言"""

    # 断言标记词
    ASSERTION_PATTERNS = [
        (r"(.+?)是(.+?)(?:的|。|，|$)", "is_statement"),
        (r"(.+?)发明了(.+?)(?:。|，|$)", "invention"),
        (r"(.+?)创建了(.+?)(?:。|，|$)", "creation"),
        (r"(.+?)于(\d+)年(.+?)(?:。|，|$)", "dated_event"),
        (r"(.+?)绝对(.+?)(?:。|，|$)", "absolute_claim"),
        (r"(.+?)从来(.+?)(?:。|，|$)", "absolute_claim"),
        (r"(.+?)一定(.+?)(?:。|，|$)", "absolute_claim"),
    ]

    # 无信息量的表述（跳过）
    SKIP_PATTERNS = [
        r"^(好的|嗯|哦|哈哈|谢谢|再见|你好)",
        r"^(可以|没问题|当然|是的|对的)",
        r"^根据我的",
        r"^让我",
        r"^以下",
        r"^需要注意",
    ]

    @classmethod
    def extract(cls, text: str) -> list[FactualClaim]:
        claims = []
        sentences = cls._split_sentences(text)

        for sent in sentences:
            sent = sent.strip()
            if not sent or len(sent) < 6:
                continue
            if any(re.match(p, sent) for p in cls.SKIP_PATTERNS):
                continue

            # 匹配断言模式
            matched = False
            for pattern, claim_type in cls.ASSERTION_PATTERNS:
                m = re.search(pattern, sent)
                if m:
                    # 提取实体
                    entities = cls._extract_entities(sent)
                    claims.append(FactualClaim(
                        text=sent,
                        entities=entities,
                        is_verifiable=(claim_type != "absolute_claim"
                                       or len(entities) > 0),
                        confidence=0.7 if claim_type == "absolute_claim" else 0.5,
                    ))
                    matched = True
                    break

            # 未匹配到已知模式但有实体 → 仍可能是可核查的
            if not matched:
                entities = cls._extract_entities(sent)
                if entities:
                    claims.append(FactualClaim(
                        text=sent,
                        entities=entities,
                        is_verifiable=True,
                        confidence=0.5,
                    ))

        return claims

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        return re.split(r'[。！？\n;；]', text)

    @staticmethod
    def _extract_entities(text: str) -> list[str]:
        """提取可能的实体关键词"""
        entities = []
        # 匹配中文专有名词：书名号内容、引号内容、特定词
        for m in re.finditer(r'[《「](.+?)[》」]', text):
            entities.append(m.group(1))
        # 匹配连续汉字/字母（>=2）
        for m in re.finditer(r'[A-Za-z\u4e00-\u9fff]{3,}', text):
            word = m.group()
            if word not in entities:
                entities.append(word)
        return entities[:5]


# ============================================================
# 锚定引擎
# ============================================================

class AnchorEngine:
    """多源锚定：本地知识库 + 可选的 Web 搜索"""

    def __init__(self, enable_web: bool = False):
        self.enable_web = enable_web
        self.headers = {
            "User-Agent": "HallucinationDetector/1.0 (research tool)",
        }

    def verify(self, claim: FactualClaim) -> VerificationResult:
        """综合核查一条断言"""

        # 1. 本地知识库
        kb_result = self._check_knowledge_base(claim)
        if kb_result["verdict"] != "uncertain":
            return VerificationResult(
                claim=claim.text,
                verdict=kb_result["verdict"],
                confidence=kb_result["confidence"],
                evidence=kb_result["evidence"],
                source=kb_result["source"],
                anchor_type="knowledge_base",
            )

        # 2. 绝对化断言检测
        abs_result = self._check_absolute_claim(claim)
        if abs_result:
            return abs_result

        # 3. 无法核查
        return VerificationResult(
            claim=claim.text,
            verdict="unverifiable",
            confidence=0.3,
            evidence="无法在本地知识库中找到相关信息",
            source="",
            anchor_type="none",
        )

    def _check_knowledge_base(self, claim: FactualClaim) -> dict:
        text_lower = claim.text.lower()
        # 同义词扩展: 将文本中的同义词替换为KB键
        expanded_text = text_lower
        for syn, target in SYNONYM_MAP.items():
            if syn in text_lower:
                expanded_text += " " + target
        sorted_keys = sorted(KNOWLEDGE_BASE.keys(), key=len, reverse=True)
        for key in sorted_keys:
            entry = KNOWLEDGE_BASE[key]
            key_lower = key.lower()
            if key_lower in expanded_text or any(key_lower in e.lower() for e in claim.entities) or (len(key)>=2 and all(c in text_lower for c in key_lower)):
                for fact in entry["facts"]:
                    v, c = self._compare_with_fact(claim.text, fact)
                    if v == "contradicted":
                        return {"verdict": v, "confidence": c, "evidence": fact, "source": entry["source"]}
                # No contradiction found — check for best match
                best_v, best_f, best_c = None, entry["facts"][0], 0
                for fact in entry["facts"]:
                    v, c = self._compare_with_fact(claim.text, fact)
                    if v == "verified" and not best_v:
                        best_v, best_f, best_c = v, fact, c
                if best_v:
                    return {"verdict": best_v, "confidence": best_c, "evidence": best_f, "source": entry["source"]}
                return {"verdict": "uncertain", "confidence": 0.5, "evidence": f"相关: {entry['facts'][0][:80]}", "source": entry["source"]}
        return self._semantic_match_kb(claim)
    def _semantic_match_kb(self, claim: FactualClaim) -> dict:
        """语义相似度回退——字符bigram重叠匹配KB条目"""
        text_lower = claim.text.lower()
        best_score, best_key, best_entry = 0, None, None
        for key, entry in KNOWLEDGE_BASE.items():
            key_lower = key.lower()
            claim_grams = {text_lower[i:i+2] for i in range(len(text_lower)-1)}
            key_grams = {key_lower[i:i+2] for i in range(len(key_lower)-1)}
            if not claim_grams or not key_grams:
                continue
            score = len(claim_grams & key_grams) / max(len(claim_grams | key_grams), 1)
            char_overlap = len(set(key_lower) & set(text_lower)) / max(len(set(key_lower)), 1)
            score = score * 0.6 + char_overlap * 0.4
            if score > best_score:
                best_score, best_key, best_entry = score, key, entry
        if best_score < 0.15:
            return {"verdict": "uncertain", "confidence": 0, "evidence": "", "source": ""}
        for fact in best_entry["facts"]:
            v, c = self._compare_with_fact(claim.text, fact)
            if v == "contradicted":
                return {"verdict": v, "confidence": c, "evidence": fact, "source": best_entry["source"], "semantic_match": {"key": best_key, "score": round(best_score, 3)}}
        best_v, best_f, best_c = None, best_entry["facts"][0], 0
        for fact in best_entry["facts"]:
            v, c = self._compare_with_fact(claim.text, fact)
            if v == "verified" and not best_v:
                best_v, best_f, best_c = v, fact, c
        if best_v:
            return {"verdict": best_v, "confidence": best_c, "evidence": best_f, "source": best_entry["source"], "semantic_match": {"key": best_key, "score": round(best_score, 3)}}
        return {"verdict": "uncertain", "confidence": 0.5, "evidence": f"语义匹配: {best_entry['facts'][0][:80]}", "source": best_entry["source"], "semantic_match": {"key": best_key, "score": round(best_score, 3)}}

    def _compare_with_fact(self, claim: str, fact: str) -> tuple:
        # 1. 无穷/无限检测
        if re.search(r'无穷|无限', claim):
            if re.search(r'有限|每秒|公里|不是.*无穷', fact):
                return ("contradicted", 0.85)
        # 2. 否定模式
        p = [(r"(?:发明了|创造了|创建了)",r"(?:不是|没有|并非).*创[造建]|.*发明"),(r"第一",r"(?:不是|没有|维京|更早)"),(r"最大",r"(?:不是|没有|并非)"),(r"同一个",r"任何.*关系")]
        for cp, fp in p:
            if re.search(cp, claim) and re.search(fp, fact):
                return ("contradicted", 0.85)
        # 3. 年份冲突
        cy, fy = re.findall(r"\d{3,4}", claim), re.findall(r"\d{3,4}", fact)
        ev = ["建立","灭亡","发布","创建","发明","诞生"]
        if cy and fy and any(v in claim and v in fact for v in ev) and any(c!=f for c in cy for f in fy):
            return ("contradicted", 0.9)
        # 3b. 数值冲突
        cn = re.findall(r"\d+\.?\d*", claim)
        fn = re.findall(r"\d+\.?\d*", fact)
        if cn and fn:
            # 检查是否是同一度量 (米/公里/年/岁)
            units_claim = bool(re.search(r"米|公里|千米|年|岁|个|万", claim))
            units_fact = bool(re.search(r"米|公里|千米|年|岁|个|万", fact))
            if units_claim and units_fact:
                for cc in cn:
                    for ff in fn:
                        try:
                            if abs(float(cc) - float(ff)) / max(float(ff), 1) > 0.08:
                                return ("contradicted", 0.88)
                        except ValueError:
                            pass
        # 4. 重叠验证 (否定事实跳过)
        if re.search(r'不是|没有|并非|更早', fact):
            pass
        else:
            cs, fs = set(claim), set(fact)
            if len(cs & fs) / max(len(cs), 1) > 0.55:
                return ("verified", 0.7)
        return ("uncertain", 0.5)

    def _check_absolute_claim(self, claim: FactualClaim) -> Optional[VerificationResult]:
        """检测绝对化断言（"一定""绝对""从来"）"""
        markers = ["一定", "绝对", "从来", "永远", "所有人", "没有人", "毫无疑问"]
        if any(m in claim.text for m in markers):
            return VerificationResult(
                claim=claim.text,
                verdict="uncertain",
                confidence=0.3,
                evidence="包含绝对化表述，此类断言几乎总是过度简化",
                source="逻辑学",
                anchor_type="consistency",
            )
        return None


# ============================================================
# 报告生成器
# ============================================================

class Reporter:
    """生成可读的幻觉报告"""

    VERDICT_ICONS = {
        "verified": "✅",
        "contradicted": "🔴",
        "uncertain": "🟡",
        "unverifiable": "⬜",
    }

    VERDICT_LABELS = {
        "verified": "已验证",
        "contradicted": "矛盾",
        "uncertain": "不确定",
        "unverifiable": "不可核查",
    }

    @classmethod
    def generate(cls, report: HallucinationReport) -> str:
        lines = []
        lines.append("=" * 62)
        lines.append("  幻觉检测报告")
        lines.append("=" * 62)
        lines.append(f"  输入长度: {len(report.input_text)} 字符")
        lines.append(f"  提取断言: {len(report.claims)} 条")
        lines.append(f"  整体可信度: {report.overall_score:.0%}")
        lines.append(f"  疑似幻觉率: {report.hallucination_ratio:.0%}")
        lines.append("=" * 62)

        if not report.results:
            lines.append("\n  未检测到可核查的断言。")
            return "\n".join(lines)

        lines.append("")
        for i, r in enumerate(report.results, 1):
            icon = cls.VERDICT_ICONS.get(r.verdict, "❓")
            label = cls.VERDICT_LABELS.get(r.verdict, r.verdict)
            lines.append(f"  {icon} [{label}] {r.claim[:80]}")
            if r.evidence:
                lines.append(f"     证据: {r.evidence[:100]}")
            if r.source:
                lines.append(f"     来源: {r.source}")
            if r.verdict != "verified":
                lines.append(f"     可信度: {r.confidence:.0%}")
            lines.append("")

        if report.warnings:
            lines.append("-" * 62)
            lines.append("  ⚠️  警告:")
            for w in report.warnings:
                lines.append(f"     • {w}")

        lines.append("=" * 62)
        return "\n".join(lines)

    @classmethod
    def to_json(cls, report: HallucinationReport) -> str:
        return json.dumps({
            "input_text": report.input_text,
            "num_claims": len(report.claims),
            "overall_score": report.overall_score,
            "hallucination_ratio": report.hallucination_ratio,
            "warnings": report.warnings,
            "results": [
                {
                    "claim": r.claim,
                    "verdict": r.verdict,
                    "confidence": r.confidence,
                    "evidence": r.evidence,
                    "source": r.source,
                    "anchor_type": r.anchor_type,
                }
                for r in report.results
            ],
        }, ensure_ascii=False, indent=2)


# ============================================================
# 主流程
# ============================================================

class HallucinationDetector:
    """幻觉检测器主类"""

    def __init__(self, enable_web: bool = False):
        self.extractor = FactExtractor()
        self.anchor = AnchorEngine(enable_web=enable_web)

    def analyze(self, text: str) -> HallucinationReport:
        report = HallucinationReport(input_text=text)

        # 1. 提取断言
        claims = self.extractor.extract(text)
        report.claims = claims

        if not claims:
            report.overall_score = 1.0
            return report

        # 2. 逐条核查
        for claim in claims:
            result = self.anchor.verify(claim)
            report.results.append(result)

        # 3. 计算整体指标
        total = len(report.results)
        contradicted = sum(1 for r in report.results
                          if r.verdict == "contradicted")
        uncertain = sum(1 for r in report.results
                       if r.verdict == "uncertain")
        verified = sum(1 for r in report.results
                      if r.verdict == "verified")

        if total > 0:
            report.hallucination_ratio = contradicted / total
            report.overall_score = 1.0 - (
                contradicted * 0.8 + uncertain * 0.3
            ) / total
            report.overall_score = max(0.0, report.overall_score)

        # 4. 生成警告
        if report.hallucination_ratio > 0:
            report.warnings.append(
                f"发现 {contradicted} 条与已知事实矛盾的断言"
            )
        if uncertain > 0:
            report.warnings.append(
                f"有 {uncertain} 条断言无法验证——建议人工复核"
            )
        # 绝对化表述警告
        abs_count = sum(1 for r in report.results
                       if r.anchor_type == "consistency")
        if abs_count > 0:
            report.warnings.append(
                f"检测到 {abs_count} 条绝对化表述（「一定」「从来」等），"
                "此类断言几乎总是存在例外"
            )

        return report


def main():
    parser = argparse.ArgumentParser(
        description="幻觉检测器 — 检查 LLM 输出中的事实错误",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "朱元璋发明了火锅"
  %(prog)s --file llm_output.txt
  %(prog)s --json "Python 是1989年发布的" 
  echo "地球是平的" | %(prog)s --stdin
        """,
    )
    parser.add_argument("text", nargs="?", help="要检查的文本")
    parser.add_argument("--file", "-f", help="从文件读取")
    parser.add_argument("--stdin", action="store_true", help="从标准输入读取")
    parser.add_argument("--json", "-j", action="store_true", help="JSON 输出")
    parser.add_argument("--web", action="store_true", help="启用 Web 搜索 (未实现)")
    args = parser.parse_args()

    # 读取输入
    if args.stdin:
        text = sys.stdin.read()
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    elif args.text:
        text = args.text
    else:
        parser.print_help()
        sys.exit(1)

    # 检测
    detector = HallucinationDetector(enable_web=args.web)
    report = detector.analyze(text)

    # 输出
    if args.json:
        print(Reporter.to_json(report))
    else:
        print(Reporter.generate(report))


if __name__ == "__main__":
    main()
