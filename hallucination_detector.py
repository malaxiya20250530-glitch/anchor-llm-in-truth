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
from pathlib import Path
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    from logger import log
except ImportError:
    class _NoopLog:
        def __getattr__(self, _): return lambda *a, **k: None
    log = _NoopLog()

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
    "大清": "清", "满清": "清",
    "蒙元": "元", "大元": "元",
    "狭义相对论": "相对论", "广义相对论": "相对论",
    "达尔文主义": "进化论", "自然选择学说": "进化论",
    "量子物理": "量子力学", "量子理论": "量子力学",
    "门捷列夫表": "元素周期表", "化学周期表": "元素周期表",
    "达尔文": "进化论",
    "爱因斯坦": "相对论",
    "互联网": "internet", "因特网": "internet", "网络": "internet",
    "AI": "人工智能", "机器学习": "人工智能",
    "飞行器": "飞机", "航空器": "飞机",
    "核武器": "核能", "原子能": "核能", "核弹": "核能",
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
    "地球": {"facts": ["地球是太阳系第三颗行星，形成于约 45.4 亿年前","地球是已知唯一存在生命的天体","地球不是平的，地球是近似球体","地球不是完美球体"], "source": "NASA"},
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
    "牛顿": {"facts": ["牛顿出生于1643年，逝世于1727年","艾萨克·牛顿于1687年发表《自然哲学的数学原理》","牛顿发现了万有引力定律和三大运动定律","牛顿和莱布尼茨分别独立发明了微积分","牛顿不是被苹果砸中才发现万有引力的——这是后来的传说"], "source": "科学史"},
    "爱因斯坦": {"facts": ["爱因斯坦于1905年发表狭义相对论，1915年发表广义相对论","爱因斯坦没有发明原子弹","E=mc²是狭义相对论的推论"], "source": "物理学史"},
    "爱迪生": {"facts": ["爱迪生没有发明电灯泡——电灯泡在他之前已经存在","爱迪生改进了灯泡并使其商业化","爱迪生持有1093项美国专利"], "source": "科技史"},
    "特斯拉": {"facts": ["尼古拉·特斯拉发明了交流电系统","特斯拉不是被埋没的天才——他在晚年获得了多项荣誉","特斯拉和爱迪生是竞争对手"], "source": "科技史"},
    "瓦特": {"facts": ["瓦特没有发明蒸汽机——他改良了蒸汽机使其效率大幅提高","蒸汽机在瓦特之前已存在数十年","瓦特的改良触发了工业革命"], "source": "科技史"},
    "贝尔": {"facts": ["亚历山大·贝尔于1876年获得电话专利","贝尔不是唯一发明电话的人——Elisha Gray同日提交了专利申请","贝尔的专利是历史上最有价值的专利之一"], "source": "科技史"},
    "莱特兄弟": {"facts": ["莱特兄弟于1903年12月17日完成首次动力飞行","莱特兄弟不是最早尝试飞行的人，但他们是第一个成功实现可控动力飞行的","首次飞行仅持续12秒，飞行距离36米"], "source": "航空史"},
    "莎士比亚": {"facts": ["威廉·莎士比亚是英国文艺复兴时期最伟大的剧作家","莎士比亚生于1564年，卒于1616年","莎士比亚的作品包括37部戏剧和154首十四行诗","莎士比亚不是一个人——关于其身份存在学术争议"], "source": "文学史"},
    "达尔文": {"facts": ["达尔文于1859年发表《物种起源》","达尔文不是第一个提出进化论的人——拉马克等人更早","自然选择是进化的主要机制"], "source": "《物种起源》"},
    "青霉素": {"facts": ["青霉素由亚历山大·弗莱明于1928年发现","弗莱明不是有意发现青霉素的——是实验室污染导致的意外发现","青霉素的发现标志着抗生素时代的开始","青霉素在二战期间大量生产，挽救了无数生命"], "source": "医学史"},
    "大脑": {"facts": ["人类只用了大脑10%的说法是完全没有科学依据的谣言","大脑约占体重的2%，但消耗约20%的能量","神经元不能再生是一个被推翻的旧观点——某些脑区确实可以产生新神经元"], "source": "神经科学"},
    "恐龙": {"facts": ["恐龙灭绝于约6600万年前的K-Pg灭绝事件","一颗小行星撞击地球是恐龙灭绝的主要原因","鸟类是恐龙的直接后代——鸟类不是恐龙的后代，鸟类就是恐龙的一种"], "source": "古生物学"},
    "蜜蜂": {"facts": ["根据物理定律，大黄蜂不能飞行的说法是都市传说","蜜蜂在采蜜时进行授粉","一只蜜蜂一生只能生产约十二分之一茶匙的蜂蜜"], "source": "昆虫学"},
    "咖啡": {"facts": ["咖啡原产于埃塞俄比亚","咖啡因是世界上消费最广泛的精神活性物质","咖啡不是山羊发现的——虽然有一个关于埃塞俄比亚牧羊人的传说"], "source": "食品史"},
    "茶": {"facts": ["茶起源于中国，传说神农氏发现了茶","唐代陆羽写了《茶经》，是世界第一部茶叶专著","下午茶的传统始于19世纪的英国"], "source": "茶文化史"},
    "巧克力": {"facts": ["巧克力起源于中美洲，玛雅人和阿兹特克人食用可可","现代固体巧克力在19世纪才发明","白巧克力不是真正的巧克力——它不含可可固体"], "source": "食品史"},
    "维基百科": {"facts": ["维基百科于2001年1月15日上线","维基百科由Jimmy Wales和Larry Sanger创建","维基百科是世界最大的百科全书"], "source": "维基媒体基金会"},
    "比特币": {"facts": ["比特币于2009年由化名中本聪的人创建","中本聪的真实身份至今未知","比特币的总量上限是2100万个"], "source": "bitcoin.org"},
    "万有引力": {"facts": ["万有引力定律由牛顿提出","万有引力不是牛顿看到苹果落地后顿悟的——他研究这个问题多年，牛顿也没有被苹果砸中","引力是四种基本力中最弱的"], "source": "物理学"},
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
    
    "清": {"facts": ["清朝(1644-1912年)是中国最后一个封建王朝","鸦片战争于1840年爆发，中国被迫打开国门","清朝由满族人建立，前身为后金"], "source": "清史稿"},
    "元": {"facts": ["元朝(1271-1368年)由忽必烈建立","元朝是中国历史上疆域最广阔的朝代之一","马可·波罗在元朝时期来到中国"], "source": "元史"},
    "三国": {"facts": ["三国时期(220-280年)是魏蜀吴三足鼎立的时代","赤壁之战发生在208年","三国不是由曹操统一的——最终由司马炎统一"], "source": "三国志"},
    "丝绸之路": {"facts": ["丝绸之路始于汉代，张骞出使西域开辟","丝绸之路不仅运输丝绸，还传播文化和技术","海上丝绸之路与陆上丝绸之路并行发展"], "source": "中外交通史"},
    "相对论": {"facts": ["狭义相对论由爱因斯坦于1905年提出","广义相对论于1915年提出","E=mc²是狭义相对论最著名的公式","相对论推翻了牛顿的绝对时空观"], "source": "物理学"},
    "进化论": {"facts": ["达尔文于1859年出版《物种起源》","进化论的核心机制是自然选择","进化论不是人是从猴子变来的——人和猴子有共同祖先","达尔文没有说适者生存——这是斯宾塞的说法"], "source": "生物学"},
    "量子力学": {"facts": ["量子力学于20世纪初由普朗克、玻尔、海森堡等人建立","量子力学描述微观世界的物理规律","量子纠缠是真实存在的物理现象","薛定谔的猫是一个思想实验，不是真实实验"], "source": "物理学"},
    
    "故宫": {"facts": ["故宫位于北京，不在纽约","故宫是明清两代的皇家宫殿，于1420年建成","故宫旧称紫禁城"], "source": "故宫博物院"},
    "富士山": {"facts": ["富士山位于日本，不在中国","富士山是日本最高峰，海拔3776米","富士山是一座活火山"], "source": "日本地理"},
    "元素周期表": {"facts": ["元素周期表由门捷列夫于1869年提出","门捷列夫准确预测了当时尚未发现的元素","元素周期表按原子序数排列，不是原子量"], "source": "化学"},
    "电": {"facts": ["电是自然现象，不是任何人发明的","本杰明·富兰克林没有发明电——他证明了闪电是电","法拉第发现了电磁感应定律"], "source": "物理学"},
    "internet": {"facts": ["互联网起源于1969年的ARPANET","万维网由Tim Berners-Lee于1989年发明","互联网和万维网不是同一个概念——万维网运行在互联网之上"], "source": "计算机科学"},
    "人工智能": {"facts": ["人工智能作为一个研究领域始于1956年达特茅斯会议","图灵于1950年提出图灵测试","AI不是万能的——当前AI是窄人工智能而非通用人工智能"], "source": "计算机科学"},
    "飞机": {"facts": ["莱特兄弟于1903年进行了首次动力飞行","莱特兄弟不是第一个飞上天空的人——滑翔机和气球更早出现","喷气式飞机在二战后期才投入实战"], "source": "航空史"},
    "疫苗": {"facts": ["爱德华·詹纳于1796年发明了天花疫苗——世界上第一种疫苗","疫苗通过激发免疫系统产生抗体来预防疾病","疫苗不会导致自闭症——这个说法来自一篇被撤稿的造假论文"], "source": "医学"},
    "核能": {"facts": ["恩里科·费米于1942年建造了第一个核反应堆","核裂变于1938年由哈恩和斯特拉斯曼发现","第一颗原子弹于1945年在新墨西哥州试爆"], "source": "物理学"},
    "奥林匹克": {"facts": ["现代奥运会始于1896年，在雅典举行","奥林匹克休战是古希腊的传统","奥运会金牌不是纯金的——主要是银，镀了一层金"], "source": "国际奥委会"},

    "黄帝": {"facts": ["黄帝是传说中中华民族的人文初祖","黄帝不是第一个皇帝——皇帝制度始于秦始皇","黄帝和炎帝并称炎黄，是华夏族的共同祖先"], "source": "史记"},
    "司马迁": {"facts": ["司马迁是西汉历史学家，著有《史记》","司马迁遭受宫刑后完成了《史记》","《史记》是中国第一部纪传体通史"], "source": "汉书"},
    "孙子兵法": {"facts": ["《孙子兵法》由春秋时期孙武所著","《孙子兵法》是世界上最早的兵书之一","孙子兵法不是现代管理学著作——但其中的策略被广泛借用"], "source": "中国军事史"},
    "拿破仑": {"facts": ["拿破仑·波拿巴于1804年称帝","拿破仑不是矮子——他身高约168-170厘米，高于当时的法国平均水平","滑铁卢战役发生于1815年，拿破仑在此战败"], "source": "欧洲史"},
    "文艺复兴": {"facts": ["文艺复兴于14-17世纪发源于意大利","文艺复兴不是突然出现的——它根植于中世纪晚期的社会变化","达芬奇、米开朗基罗和拉斐尔是文艺复兴三杰"], "source": "艺术史"},
    "工业革命": {"facts": ["第一次工业革命始于18世纪60年代的英国","工业革命不是由单一发明触发的——是纺织、蒸汽机、冶金等多个领域的综合变革","工业革命极大地改变了人类社会的生活方式"], "source": "经济史"},
    "法国大革命": {"facts": ["法国大革命爆发于1789年","攻占巴士底狱是法国大革命的标志性事件","法国大革命提出了自由、平等、博爱的口号"], "source": "欧洲史"},
    "十月革命": {"facts": ["十月革命发生于1917年11月7日（俄历10月25日）","十月革命不是唯一的俄国革命——同年二月革命已推翻了沙皇","十月革命建立了世界上第一个社会主义国家"], "source": "俄国史"},
    "圆周率": {"facts": ["圆周率π是一个无限不循环小数","π约等于3.14159","祖冲之在5世纪将π计算到小数点后7位","π不是3.14——3.14只是一个近似值"], "source": "数学"},
    "勾股定理": {"facts": ["勾股定理描述直角三角形三边关系：a²+b²=c²","勾股定理在中国古代由商高发现，西方称为毕达哥拉斯定理","勾股定理不是毕达哥拉斯第一个发现的——古巴比伦人更早"], "source": "数学"},
    "黄金分割": {"facts": ["黄金分割比例约为1:1.618","黄金分割在自然界和艺术中广泛存在","黄金分割不是美的唯一标准——很多经典作品并不遵循黄金分割"], "source": "数学"},
    "撒哈拉": {"facts": ["撒哈拉沙漠是世界上最大的热沙漠","撒哈拉不是世界上最大的沙漠——南极洲是最大的沙漠","撒哈拉曾经是绿洲，约1万年前气候湿润"], "source": "地理"},
    "尼罗河": {"facts": ["尼罗河是世界上最长的河流之一","尼罗河每年定期泛滥为古埃及农业提供了肥沃的土壤","尼罗河的源头之争持续了数千年"], "source": "地理"},
    "亚马逊": {"facts": ["亚马逊雨林是世界上最大的热带雨林","亚马逊雨林不是地球之肺——海洋产生更多氧气","亚马逊河是世界上流量最大的河流"], "source": "地理"},
    "蓝鲸": {"facts": ["蓝鲸是地球上已知最大的动物","蓝鲸不是鱼——是哺乳动物","蓝鲸以磷虾为食，每天可消耗数吨磷虾"], "source": "生物学"},
    "章鱼": {"facts": ["章鱼有3个心脏和9个大脑","章鱼是非常聪明的无脊椎动物","章鱼血液是蓝色的——因为含有血蓝蛋白而非血红蛋白"], "source": "生物学"},
    "维生素c": {"facts": ["维生素C又称抗坏血酸","缺乏维生素C会导致坏血病","维生素C不能预防感冒——这个说法缺乏科学证据"], "source": "营养学"},
    "莫扎特": {"facts": ["沃尔夫冈·阿马德乌斯·莫扎特是天才作曲家","莫扎特5岁开始作曲，35岁去世","莫扎特不是被萨列里毒死的——这是电影《莫扎特传》的虚构情节"], "source": "音乐史"},
    "红楼梦": {"facts": ["《红楼梦》是中国古典四大名著之一","《红楼梦》前80回由曹雪芹所著，后40回一般认为是高鹗续写","《红楼梦》不是爱情小说——它是一部封建社会的百科全书"], "source": "中国文学"},
    "足球": {"facts": ["现代足球起源于英国","足球不是英国发明的——古代中国和古希腊都有类似运动","世界杯足球赛始于1930年"], "source": "体育"},
    "通货膨胀": {"facts": ["通货膨胀是货币购买力持续下降的现象","通货膨胀不是物价上涨——物价上涨是通货膨胀的表现","适度的通货膨胀是经济增长的正常现象"], "source": "经济学"},
    "半导体": {"facts": ["半导体是导电性介于导体和绝缘体之间的材料","硅是最常用的半导体材料","摩尔定律预测集成电路上晶体管数量约每两年翻一番"], "source": "电子学"},
    "图灵": {"facts": ["艾伦·图灵是计算机科学的奠基人","图灵在二战期间破解了德国的恩尼格玛密码","图灵不是发明计算机的人——他提出了通用计算机的理论模型","图灵测试是判断机器是否具有智能的方法"], "source": "计算机科学"},
    "冥王星": {"facts": ["冥王星于2006年被降级为矮行星","冥王星不是太阳系最小的天体——它仍然是柯伊伯带中最大的天体之一","冥王星由克莱德·汤博于1930年发现"], "source": "天文学"},
    "土星": {"facts": ["土星是太阳系第二大行星","土星环主要由冰和岩石碎片组成","土星不是唯一有环的行星——木星、天王星和海王星也有环"], "source": "天文学"},


    "孔子": {"facts": ["孔子名丘，字仲尼，春秋时期鲁国人","孔子是儒家学派创始人","孔子不是《论语》的作者——《论语》是其弟子及再传弟子编纂的","孔子周游列国不是自愿旅行——是被迫的政治流亡"], "source": "史记"},
    "老子": {"facts": ["老子姓李名耳，春秋时期人","老子是道家学派创始人","《道德经》是否为老子本人所著存在学术争议","老子不是道教创始人——道教是东汉张道陵创立的"], "source": "史记"},
    "柏拉图": {"facts": ["柏拉图是古希腊哲学家，苏格拉底的学生","柏拉图创立了雅典学院","柏拉图不是第一个提出理想国概念的人——但他将其系统化了","柏拉图认为诗人应该被逐出理想国"], "source": "西方哲学史"},
    "亚里士多德": {"facts": ["亚里士多德是柏拉图的学生，亚历山大大帝的老师","亚里士多德不是所有科学之父——他的一些科学观点已被证明错误","亚里士多德认为重物比轻物下落更快——这是错的","亚里士多德著作涵盖逻辑学、物理学、生物学、伦理学等"], "source": "西方哲学史"},
    "罗马帝国": {"facts": ["罗马帝国不是一天建成的","罗马帝国分裂为东西两部分——西罗马于476年灭亡，东罗马持续到1453年","罗马不是世界上最大的帝国——大英帝国和蒙古帝国的面积更大","罗马帝国不是突然崩溃的——经历了几百年的衰落过程"], "source": "世界史"},
    "二战": {"facts": ["第二次世界大战于1939年爆发，1945年结束","二战不是由单一事件引发的——是多重因素累积的结果","中国抗日战争是二战的重要组成部分","原子弹不是结束二战的唯一原因——苏联对日宣战也是关键因素"], "source": "世界史"},
    "冷战": {"facts": ["冷战是二战后美苏两大阵营的对峙","冷战没有变成热战——但期间有许多代理人战争","冷战不是以一方投降结束的——苏联解体标志着冷战终结","柏林墙于1961年建立，1989年倒塌"], "source": "世界史"},
    "黑洞": {"facts": ["黑洞是由大质量恒星坍缩形成的天体","黑洞不是洞——它是一个密度极大的天体","黑洞不是只进不出的——霍金辐射理论认为黑洞会蒸发","黑洞不是爱因斯坦预言的——是广义相对论方程的一个解"], "source": "天文学"},
    "暗物质": {"facts": ["暗物质是宇宙中不发光的物质，占宇宙总质量的约27%","暗物质不是被证明存在的——目前通过引力效应间接推断","暗物质不是反物质——两者是不同的概念","暗物质可能由未知粒子组成"], "source": "物理学"},
    "大陆漂移": {"facts": ["大陆漂移学说由魏格纳于1912年提出","魏格纳不是第一个注意到大陆形状吻合的人——但他系统论证了","大陆漂移已被板块构造理论取代和完善","大陆不是漂浮在水上的——是漂浮在地幔上的"], "source": "地质学"},
    "光合作用": {"facts": ["光合作用是植物将光能转化为化学能的过程","光合作用不是植物独有的——某些细菌也能进行","光合作用释放氧气是副产物","植物不是只靠光合作用生存——夜间进行呼吸作用消耗氧气"], "source": "生物学"},
    "气候变暖": {"facts": ["全球气候变暖是指地球平均气温持续上升","气候变暖不是自然周期——当前暖化速度远超历史上任何自然周期","97%以上的气候科学家认同人类活动是主因","气候变暖不是只让地球变热——还导致极端天气增加"], "source": "IPCC"},
    "蓝牙": {"facts": ["蓝牙技术于1994年由爱立信公司发明","蓝牙不是十世纪丹麦国王发明的——虽然以他的名字命名","蓝牙低功耗模式于2010年随蓝牙4.0引入","蓝牙的有效距离通常为10-100米，不是无限距离"], "source": "通信技术"},
    "wifi": {"facts": ["WiFi是基于IEEE 802.11标准的无线网络技术","WiFi不是由单一个人发明的——是多方技术融合的产物","WiFi不是无线上网的唯一方式——蜂窝数据也是","WiFi这个名称不是Wireless Fidelity的缩写——只是一种品牌命名"], "source": "通信技术"},
    "区块链": {"facts": ["区块链是一种去中心化的分布式账本技术","区块链不等于比特币——比特币是区块链的第一个应用","区块链不是不可篡改的——51%攻击可以改写历史","区块链不是万能解决方案——许多场景不需要区块链"], "source": "计算机科学"},
    "蒙娜丽莎": {"facts": ["《蒙娜丽莎》是达芬奇于16世纪初创作的油画","蒙娜丽莎不是达芬奇唯一的作品——但确实是最著名的","《蒙娜丽莎》的微笑之谜可能只是达芬奇的sfumato技法","《蒙娜丽莎》不是被盗后才出名的——它被盗前已经很有名"], "source": "艺术史"},
    "梵高": {"facts": ["文森特·梵高是荷兰后印象派画家","梵高生前只卖出了一幅画——《红色葡萄园》","梵高不是割掉整个耳朵的——他只割掉了左耳的一部分","梵高不是因无人赏识而死——他患有精神疾病"], "source": "艺术史"},
    "毕加索": {"facts": ["巴勃罗·毕加索是20世纪最有影响力的艺术家之一","毕加索创立了立体主义画派","毕加索不是只会画抽象画——他早期的写实作品技艺精湛","《格尔尼卡》是毕加索反战题材的代表作"], "source": "艺术史"},
    "西游记": {"facts": ["《西游记》是中国古典四大名著之一","《西游记》作者一般认为是明代吴承恩","《西游记》不是佛教宣传书——它融合了儒释道三家思想","孙悟空的原型存在多种说法，尚无定论"], "source": "中国文学"},
    "三国演义": {"facts": ["《三国演义》是元末明初罗贯中所著","《三国演义》不是历史——是一部历史演义小说","《三国演义》中许多情节是虚构的——如草船借箭实际上不是诸葛亮所为","关羽使用的不是青龙偃月刀——这种兵器在三国时期还不存在"], "source": "中国文学"},
    "水浒传": {"facts": ["《水浒传》是中国古典四大名著之一","《水浒传》的故事背景是北宋末年宋江起义","《水浒传》108将大多不是真实历史人物——只有36人是历史记载的","林冲、武松等核心角色在正史中没有记载"], "source": "中国文学"},
    "死海": {"facts": ["死海是世界上海拔最低的湖泊","死海不是海——是一个内陆盐湖","死海的含盐量约为普通海水的10倍","死海中并非完全没有生命——存在嗜盐微生物"], "source": "地理"},
    "大堡礁": {"facts": ["大堡礁位于澳大利亚东北海岸，是世界上最大的珊瑚礁系统","大堡礁不是从一个太空可见的地球结构——它是少数几个可见的之一","大堡礁正在受气候变化和珊瑚白化的威胁","大堡礁的年龄约为50万年，不是从恐龙时代就存在的"], "source": "地理"},
    "黄石公园": {"facts": ["黄石国家公园位于美国，是世界上第一个国家公园","黄石公园坐落在一座超级火山上","黄石超级火山不会很快喷发——目前没有即将喷发的迹象","黄石公园不是美国最大的国家公园"], "source": "地理"},
    "南极洲": {"facts": ["南极洲是地球上最冷的大陆，平均温度约-57°C","南极洲不是没有生命——有企鹅、海豹和多种微生物","南极洲冰层储存了地球约70%的淡水","南极洲不属于任何国家——受《南极条约》保护"], "source": "地理"},
    "珊瑚": {"facts": ["珊瑚是动物，不是植物","珊瑚礁由珊瑚虫分泌的碳酸钙骨骼构成","珊瑚白化是由于共生藻类离开导致的","珊瑚不是石头——活的珊瑚是柔软的珊瑚虫群落"], "source": "生物学"},
    "蝙蝠": {"facts": ["蝙蝠是唯一能够飞行的哺乳动物","蝙蝠不是瞎子——大多数蝙蝠视力很好","蝙蝠不会主动攻击人类——吸血蝙蝠只分布于拉丁美洲","蝙蝠对生态系统至关重要——是重要的传粉者和害虫控制者"], "source": "生物学"},
    "蚂蚁": {"facts": ["蚂蚁在地球上已存在超过1亿年","蚂蚁的社会结构不是君主制——蚁后只是产卵机器","地球上蚂蚁的总重量超过所有人类的总重量","蚂蚁不是完全盲目的——它们依靠信息素导航和通讯"], "source": "生物学"},
    "蜘蛛": {"facts": ["蜘蛛不是昆虫——属于蛛形纲","不是所有蜘蛛都织网——狼蛛等猎食性蜘蛛不织网","蜘蛛丝比同等重量的钢更强韧","大多数蜘蛛对人类无害"], "source": "生物学"},
    "麻醉": {"facts": ["现代麻醉术始于1846年波士顿的乙醚麻醉演示","麻醉不是让人睡着——是诱导可逆的意识丧失和痛觉消失","中国古代华佗的麻沸散存在争议——缺乏可靠史料证实","麻醉不是万无一失的——需要专业麻醉医师全程监控"], "source": "医学史"},
    "x光": {"facts": ["X射线由威廉·伦琴于1895年发现","X光不是伦琴刻意寻找的——他在做阴极射线实验时意外发现","第一张X光片是伦琴夫人的手","X光不是完全无害的——高剂量辐射有致癌风险"], "source": "医学史"},
    "dna测序": {"facts": ["第一个人类基因组测序于2003年完成——人类基因组计划","DNA测序不是从2000年才开始——桑格测序法于1977年发明","DNA测序的成本不是不变的——从最初的数十亿美元降到了几百美元","DNA测序不能预测你的一切——基因只决定一部分特征"], "source": "基因组学"},
    "弗洛伊德": {"facts": ["西格蒙德·弗洛伊德是精神分析学创始人","弗洛伊德的理论不是科学界普遍接受的——许多理论已被现代心理学抛弃","弗洛伊德不是发现潜意识的第一人——这个概念在他之前就存在","弗洛伊德不是心理学家——他是神经科医生"], "source": "心理学史"},
    "安慰剂效应": {"facts": ["安慰剂效应是指病人因相信自己接受治疗而产生真实改善","安慰剂效应不是假的——它能在脑中产生真实的生理变化","安慰剂效应不能治愈癌症——但可以缓解某些症状","安慰剂不是无用的——它在临床试验和某些治疗中有重要价值"], "source": "医学"},
    "认知偏差": {"facts": ["认知偏差是系统性偏离理性判断的思维模式","确认偏误是人们倾向于寻找支持自己观点的证据","认知偏差不是智商问题——高智商的人同样会有认知偏差","认知偏差不是少数人的问题——每个人都会受到各种认知偏差的影响"], "source": "心理学"},
    "居里夫人": {"facts": ["玛丽·居里是第一位获得诺贝尔奖的女性","居里夫人发现了放射性元素镭和钋","居里夫人是唯一获得过两次诺贝尔奖的女性科学家","居里夫人死于再生障碍性贫血，可能与长期接触辐射有关","居里夫人的笔记本至今仍有放射性"], "source": "科学史"},
    "诺贝尔奖": {"facts": ["诺贝尔奖由阿尔弗雷德·诺贝尔于1895年设立","诺贝尔不是因为内疚才设立和平奖的——但这件事被广泛传播","诺贝尔奖没有数学奖——不是因为诺贝尔的恋人跟数学家跑了","诺贝尔经济学奖不是诺贝尔本人设立的——由瑞典央行于1968年设立"], "source": "科学史"},
    "三角形": {"facts": ["三角形内角和等于180度","三角形内角和不是永远180度——在非欧几何中可以大于或小于180度","勾股定理是描述直角三角形三边关系的定理","三角形是最稳定的几何结构之一"], "source": "数学"},
    "素数": {"facts": ["素数只能被1和自身整除","1不是素数","有无穷多个素数——欧几里得在公元前300年就证明了","最大的已知素数有数千万位数——由分布式计算项目找到"], "source": "数学"},
    "零": {"facts": ["零作为数字的概念最早由古印度数学家提出","零不是自然产生的概念——人类花了很长时间才接受零作为数字","零不能作为除数","阿拉伯数字中的零符号是通过阿拉伯人传入欧洲的"], "source": "数学史"},
    "地震": {"facts": ["地震是由地壳板块运动或火山活动引起的","地震不是可以被精确预测的——目前无法预测具体时间和地点","地震的震级不是线性的——每增加1级，释放的能量约增加32倍","动物不是总能预测地震——这个说法缺乏一致的科学证据"], "source": "地质学"},
    "火山": {"facts": ["火山是地球内部岩浆喷出地表形成的","火山喷发不是随机事件——通常有前兆如地震和地面变形","火山不是只会破坏——火山灰使土壤肥沃","休眠火山不是死火山——有再次喷发的可能"], "source": "地质学"},
    "睡眠": {"facts": ["成年人每晚需要7-9小时睡眠","睡眠不是统一状态——分为REM和非REM睡眠周期","补觉不能完全弥补缺觉的损害","睡眠不是浪费时间——记忆巩固和身体修复都在睡眠中进行"], "source": "生理学"},
    "梦境": {"facts": ["每个人每晚都会做多个梦——但不一定记得","梦不是有颜色的——大多数人的梦是有颜色的","梦不是一定有意义——许多梦只是大脑随机神经活动的产物","盲人的梦不是没有视觉——先天盲人的梦以声音和触觉为主"], "source": "心理学"},
    "酸奶": {"facts": ["酸奶是通过乳酸菌发酵制成的乳制品","酸奶不是所有细菌都对人体有益——只有特定益生菌株","酸奶不能治疗所有消化问题","酸奶的历史超过4000年——可能起源于中亚"], "source": "食品科学"},
    "辣椒": {"facts": ["辣椒的辣味来自辣椒素","辣椒不是原产于中国——它原产于美洲，明代才传入中国","吃辣不是味觉——辣是痛觉感受器被激活","四川人不是自古以来就吃辣——辣椒传入四川不超过400年"], "source": "食物史"},
    "土豆": {"facts": ["土豆原产于南美洲安第斯山区","土豆不是欧洲人发明的——16世纪才从美洲传入","土豆不是蔬菜——从营养学角度更接近主食","炸薯条不是法国人发明的——比利时人也声称发明权"], "source": "食物史"},
    "黄金": {"facts": ["黄金是地球上最稀有的贵金属之一","黄金不是来自地球——超新星爆炸或中子星碰撞产生金元素","黄金不是不会腐蚀——它只是化学反应性极低","地球上所有的黄金总量大约只能填满三个奥运会游泳池"], "source": "化学"},
    "声音": {"facts": ["声音通过介质传播，真空中无法传播","声音的速度不是固定的——在空气中约340m/s，在水中约1500m/s","超声波的频率超过人类听觉范围","声音不是能量——是机械振动在介质中的传播"], "source": "物理学"},

}


# 合并用户贡献的知识库
try:
    import json as _json
    from pathlib import Path as _Path
    _user_kb_path = _Path(__file__).parent / "kb_user.json"
    if _user_kb_path.exists():
        with open(_user_kb_path) as _f:
            _user_kb = _json.load(_f)
        for _key, _entry in _user_kb.items():
            if _key.startswith("_"):
                continue
            if _key in KNOWLEDGE_BASE:
                _existing = set(KNOWLEDGE_BASE[_key]["facts"])
                for _fct in _entry.get("facts", []):
                    if _fct not in _existing:
                        KNOWLEDGE_BASE[_key]["facts"].append(_fct)
            else:
                KNOWLEDGE_BASE[_key] = _entry
except (FileNotFoundError, json.JSONDecodeError, OSError):
    pass  # 用户KB损坏时不影响核心功能






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
        (r"(.+?)位于(.+?)(?:。|，|$)", "location"),
        (r"(.+?)在(.+?)(?:。|，|$)", "location"),
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
            if not sent or len(sent) < 5:
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

    def __init__(self, enable_web: bool = False, enable_feedback: bool = True,
                 enable_graph: bool = True):
        self.enable_web = enable_web
        self.enable_feedback = enable_feedback
        self.enable_graph = enable_graph
        self._graph_reasoner = None  # 惰性加载
        self.headers = {
            "User-Agent": "HallucinationDetector/1.0 (research tool)",
        }
        if self.enable_feedback:
            try:
                import feedback_store
                self.feedback = feedback_store
            except ImportError:
                self.enable_feedback = False

    def _get_graph_reasoner(self):
        """惰性加载知识图谱推理器"""
        if self._graph_reasoner is None and self.enable_graph:
            try:
                from knowledge_graph import get_reasoner
                self._graph_reasoner = get_reasoner()
            except ImportError:
                self.enable_graph = False
        return self._graph_reasoner

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

        # 2. 混合检索：BM25 + TF-IDF 向量（新增）
        try:
            from vector_kb import get_hybrid_retriever
            hr = get_hybrid_retriever()
            matches = hr.search(claim.text, top_k=2, threshold=0.12)
            for vk_key, vk_fact, vk_sim in matches:
                # 关键词重叠检查：避免无关事实被误判
                # 提取 claim 中 2-gram 关键词（中文按字切分）
                claim_kw = [claim.text[i:i+2] for i in range(len(claim.text)-1)]
                if claim_kw:
                    overlap = sum(1 for kw in claim_kw if kw in vk_fact)
                    if overlap == 0:
                        continue
                result = self._compare_with_fact(claim.text, vk_fact)
                if result[0] != "uncertain":
                    return VerificationResult(
                        claim=claim.text,
                        verdict=result[0],
                        confidence=max(result[1], vk_sim * 0.8),
                        evidence=vk_fact,
                        source=f"混合检索 (key={vk_key}, score={vk_sim:.2f})",
                        anchor_type="hybrid_retrieval",
                    )
        except ImportError:
            pass

        # 3. 联网验证 — 多源交叉验证（新增）
        if self.enable_web:
            web_sources = []
            # 源 1: DuckDuckGo
            try:
                from web_verifier import WebVerifier
                ddg = WebVerifier()
                web_sources.append(ddg.verify(claim.text))
            except (ImportError, Exception):
                pass
            # 源 2: Wikipedia
            try:
                from web_verifier import WikipediaVerifier
                wiki = WikipediaVerifier()
                web_sources.append(wiki.verify(claim.text))
            except (ImportError, Exception):
                pass

            # 加权融合多源结果
            verified_sources = [s for s in web_sources if s["verdict"] == "verified"]
            if verified_sources:
                best = max(verified_sources, key=lambda s: s["confidence"])
                return VerificationResult(
                    claim=claim.text,
                    verdict="verified",
                    confidence=best["confidence"] * (0.7 + 0.15 * len(verified_sources)),
                    evidence=best["evidence"],
                    source=f"{best['source']} (+{len(verified_sources)-1}源交叉验证)" if len(verified_sources) > 1 else best["source"],
                    anchor_type="web_search",
                )
            elif any(s["verdict"] == "uncertain" and s["confidence"] > 0.1 for s in web_sources):
                best_uncertain = max([s for s in web_sources if s["confidence"] > 0.1], key=lambda s: s["confidence"], default=None)
                if best_uncertain and best_uncertain["evidence"]:
                    return VerificationResult(
                        claim=claim.text,
                        verdict="uncertain",
                        confidence=best_uncertain["confidence"],
                        evidence=best_uncertain["evidence"],
                        source=best_uncertain["source"],
                        anchor_type="web_search",
                    )

        # 4. 绝对化断言检测
        abs_result = self._check_absolute_claim(claim)
        if abs_result:
            return abs_result

        # 记录不确定样本到反馈库
        try:
            import sqlite3, time
            from pathlib import Path
            db_path = Path(__file__).parent / "feedback.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                "INSERT INTO uncertain_samples (claim, verdict, confidence, context, created_at) VALUES (?,?,?,?,?)",
                (claim.text[:200], "uncertain", 0.3, "三级管道均未命中", time.time())
            )
            conn.commit()
            conn.close()
        except (URLError, OSError, json.JSONDecodeError, ValueError) as e:
            log.debug("web search failed", error=str(e)[:60])
            pass

        # 5. 无法核查
        return VerificationResult(
            claim=claim.text,
            verdict="unverifiable",
            confidence=0.3,
            evidence="无法在本地知识库和网络中验证此信息",
            source="",
            anchor_type="none",
        )

    def _expand_synonyms(self, text: str) -> str:
        """卫语句: 同义词扩展 — 单层, 立即返回"""
        expanded = text
        for syn, target in SYNONYM_MAP.items():
            if syn in text:
                expanded += " " + target
        return expanded

    def _key_matches_claim(self, key_lower: str, expanded_text: str, text_lower: str, entities: list[str]) -> bool:
        """卫语句: 判断KB键是否匹配当前断言 — 单层"""
        return (key_lower in expanded_text 
                or any(key_lower in e.lower() for e in entities)
                or (len(key_lower) >= 2 and all(c in text_lower for c in key_lower)))

    def _check_facts_against_entry(self, claim_text: str, entry: dict) -> dict:
        """检查条目所有事实 — 两遍扫描 + 反馈记录"""
        # 第一遍: 找矛盾
        for fact in entry["facts"]:
            v, c = self._compare_with_fact(claim_text, fact)
            if v == "contradicted":
                result = {"verdict": v, "confidence": c, "evidence": fact, "source": entry["source"]}
                self._record_feedback(claim_text, fact, result)
                return result
        # 第二遍: 找最佳匹配
        best_v, best_f, best_c = None, entry["facts"][0], 0
        for fact in entry["facts"]:
            v, c = self._compare_with_fact(claim_text, fact)
            if v == "verified" and not best_v:
                best_v, best_f, best_c = v, fact, c
        if best_v:
            result = {"verdict": best_v, "confidence": best_c, "evidence": best_f, "source": entry["source"]}
            self._record_feedback(claim_text, best_f, result)
            return result
        result = {"verdict": "uncertain", "confidence": 0.5, "evidence": f"相关: {entry['facts'][0][:80]}", "source": entry["source"]}
        self._record_feedback(claim_text, entry["facts"][0], result)
        return result

    def _check_knowledge_base(self, claim: FactualClaim) -> dict:
        """在知识库中匹配声明，优先走用户反馈的重映射键，否则按关键词查 KB。"""
        # 优先查重匹配记录：用户指定了正确的KB键
        if self.enable_feedback:
            rematch_key = self.feedback.find_rematch(claim.text)
            if rematch_key and rematch_key in KNOWLEDGE_BASE:
                result = self._check_facts_against_entry(claim.text, KNOWLEDGE_BASE[rematch_key])
                log.debug("rematch hit", key=rematch_key, claim=claim.text[:40])
                return result
        # 正常KB搜索
        expanded = self._expand_synonyms(claim.text.lower())
        for key in sorted(KNOWLEDGE_BASE.keys(), key=len, reverse=True):
            if not self._key_matches_claim(key.lower(), expanded, claim.text.lower(), claim.entities):
                continue
            result = self._check_facts_against_entry(claim.text, KNOWLEDGE_BASE[key])
            if result["verdict"] != "uncertain":
                return result
            return result
        return self._semantic_match_kb(claim)
    def _compute_similarity(self, text: str, key: str) -> float:
        """多粒度n-gram Jaccard + 字符重叠相似度"""
        # 提取1~3-gram（uni+bi+tri gram）
        def ngrams(s, n):
            return {s[i:i+n] for i in range(len(s)-n+1)}
        
        text_ngrams = set()
        key_ngrams = set()
        for n in (1, 2, 3):
            text_ngrams |= ngrams(text, n)
            key_ngrams |= ngrams(key, n)
        
        char_overlap = len(set(key) & set(text)) / max(len(set(key)), 1)
        
        if not key_ngrams and not text_ngrams:
            return char_overlap * 0.8
        if not key_ngrams:
            return char_overlap * 0.7
        if not text_ngrams:
            return char_overlap * 0.4
        
        ngram_score = len(text_ngrams & key_ngrams) / max(len(text_ngrams | key_ngrams), 1)
        # n-gram权重高于字符重叠（n-gram捕捉语序信息）
        return ngram_score * 0.65 + char_overlap * 0.35

    def _find_best_match(self, text_lower: str) -> tuple:
        """找到最相似的KB条目 — 多粒度 + 关键词权重提升"""
        best_score, best_key, best_entry = 0, None, None
        # 提取文本中的关键词（2字以上的实词）
        keywords = re.findall(r'[\u4e00-\u9fff\w]{2,}', text_lower)
        
        for key, entry in KNOWLEDGE_BASE.items():
            key_lower = key.lower()
            score = self._compute_similarity(text_lower, key_lower)
            # 关键词精确命中加成：如果KB键作为完整词出现在文本中
            if key_lower in keywords:
                score = min(score + 0.15, 1.0)
            # 文本中的关键词与KB键精确匹配时额外加分
            for kw in keywords:
                if kw == key_lower:
                    score = min(score + 0.2, 1.0)
                    break
            if score > best_score:
                best_score, best_key, best_entry = score, key, entry
        return best_score, best_key, best_entry

    def _semantic_match_kb(self, claim: FactualClaim) -> dict:
        """语义回退匹配 — 多粒度相似度 + 自适应阈值"""
        text_lower = claim.text.lower()
        best_score, best_key, best_entry = self._find_best_match(text_lower)
        
        # 自适应阈值：文本越长，阈值越低（长文本信息更多）
        text_len = len(text_lower)
        if text_len < 10:
            threshold = 0.18
        elif text_len < 30:
            threshold = 0.15
        else:
            threshold = 0.12
        
        if best_score < threshold:
            return {"verdict": "uncertain", "confidence": 0, "evidence": "", "source": ""}
        
        result = self._check_facts_against_entry(claim.text, best_entry)
        result["semantic_match"] = {"key": best_key, "score": round(best_score, 3)}
        return result

    # --- 事实比对子检查器 (每个单一职责) ---

    # 检查器优先级列表 (按执行顺序)
    _PRIORITY_CHECKERS = [
        "_check_infinity",
        "_check_negation",
        "_check_year_conflict",
        "_check_numeric_conflict",
        "_check_temporal_order",
        "_check_location_conflict",
        "_check_overlap",
        "_check_graph_contradiction",  # 知识图谱推理（最后兜底）
    ]

    def _check_infinity(self, claim: str, fact: str):
        """检查: 声称无穷 vs 事实有限 → 矛盾"""
        if re.search(r'无穷|无限', claim) and re.search(r'有限|每秒|公里|不是.*无穷', fact):
            return ("contradicted", 0.85)
        return None

    def _check_negation(self, claim: str, fact: str):
        """检查: 否定模式匹配 → 矛盾"""
        # 先做通用正反对立检查: 如果fact包含否定词且与claim共享关键词 → 矛盾
        if re.search(r'不是|没有|并非|不可以|不能|不会|不在', fact):
            # 提取 claim 中紧接在 是/能/会/可以 后面的词
            key_m = re.search(r'(?:是|能|会|可以)(.{1,6}?)(?:的|。|，|$)', claim)
            if key_m:
                key_word = key_m.group(1)
                if key_word and re.search(r'(?:不是|没有|并非|不可以|不能|不会|不在).*' + re.escape(key_word), fact):
                    return ("contradicted", 0.85)
        patterns = [
            (r"(?:发明了|创造了|创建了)", r"(?:不是|没有|并非).*创[造建]|.*发明"),
            (r"第一", r"(?:不是|没有|维京|更早|最后)"),
            (r"(?:最好|最大)", r"(?:不是|没有|并非)"),
            (r"同一个", r"任何.*关系"),
            (r"会导致", r"不会导致"),
            (r"就是", r"不是.*同一个"),
            (r"能", r"不能"),
            (r"可以", r"不可以|不能"),
            (r"一定会", r"不会|不一定"),
            (r"按原子量", r"不是原子量|按原子序数"),
            (r"被苹果砸", r"没有被苹果"),
        ]
        for cp, fp in patterns:
            if re.search(cp, claim) and re.search(fp, fact):
                return ("contradicted", 0.85)
        return None

    def _check_year_conflict(self, claim: str, fact: str):
        """检查: 同年份不同数值 → 矛盾"""
        cy, fy = re.findall(r"\d{3,4}", claim), re.findall(r"\d{3,4}", fact)
        if not cy or not fy:
            return None
        event_words = ["建立","灭亡","发布","创建","发明","诞生"]
        if any(v in claim and v in fact for v in event_words):
            if any(c != f for c in cy for f in fy):
                return ("contradicted", 0.9)
        return None

    def _check_numeric_conflict(self, claim: str, fact: str):
        """检查: 同度量数值偏差 > 8% → 矛盾 — 扁平化版本"""
        cn = re.findall(r"\d+\.?\d*", claim)
        fn = re.findall(r"\d+\.?\d*", fact)
        if not cn or not fn:
            return None
        unit_re = r"米|公里|千米|年|岁|个|万"
        if not (re.search(unit_re, claim) and re.search(unit_re, fact)):
            return None
        # 提取为独立比较逻辑
        return self._compare_number_pairs(cn, fn)

    def _compare_number_pairs(self, nums_a: list[str], nums_b: list[str]):
        """卫语句: 逐对比较数值 — 单层"""
        for a in nums_a:
            for b in nums_b:
                if self._nums_conflict(a, b):
                    return ("contradicted", 0.88)
        return None

    def _nums_conflict(self, a: str, b: str) -> bool:
        """卫语句: 两个数值是否冲突 (>8%偏差)"""
        try:
            return abs(float(a) - float(b)) / max(float(b), 1) > 0.08
        except ValueError:
            return False

    def _check_overlap(self, claim: str, fact: str):
        """检查: 字符重叠 > 55% → 验证通过"""
        if re.search(r'不是|没有|并非|更早', fact):
            return None
        cs, fs = set(claim), set(fact)
        if len(cs & fs) / max(len(cs), 1) > 0.55:
            return ("verified", 0.7)
        return None

    def _check_temporal_order(self, claim: str, fact: str):
        """检查: 时间顺序矛盾 — 将人物/事件放在错误朝代 → 矛盾"""
        era_map = {
            "秦": (-221, -207), "汉": (-202, 220), "三国": (220, 280),
            "唐": (618, 907), "宋": (960, 1279), "元": (1271, 1368),
            "明": (1368, 1644), "清": (1644, 1912),
        }
        person_era = {
            "蔡伦": "汉", "张衡": "汉", "诸葛亮": "三国", "曹操": "三国",
            "李白": "唐", "杜甫": "唐", "苏轼": "宋", "毕昇": "宋",
            "岳飞": "宋", "成吉思汗": "元", "忽必烈": "元",
            "朱元璋": "明", "郑和": "明", "康熙": "清", "乾隆": "清",
            "林则徐": "清", "詹纳": "清",  # 1796年对应清朝
        }
        for person, era in person_era.items():
            if person in claim:
                for era_name in era_map:
                    if era_name in claim and era_name != era:
                        return ("contradicted", 0.88)
        return None

    def _check_location_conflict(self, claim: str, fact: str):
        """检查: 地点归属矛盾 — 地标放错位置 → 矛盾"""
        loc_map = {
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
        all_places = [
            "北京", "上海", "广州", "深圳", "成都", "重庆", "武汉", "南京", "杭州", "西安",
            "四川", "云南", "西藏", "新疆", "河南", "河北",
            "日本", "韩国", "朝鲜", "泰国", "越南", "印度", "俄罗斯",
            "美国", "英国", "法国", "德国", "意大利", "西班牙", "巴西", "澳大利亚",
            "埃及", "南非",
            "纽约", "伦敦", "巴黎", "东京", "柏林", "罗马", "悉尼", "开罗", "莫斯科",
            "非洲", "欧洲", "亚洲", "南美", "南极", "月球",
        ]
        for landmark, correct_locs in loc_map.items():
            if landmark in claim:
                for place in all_places:
                    if place in claim and place not in correct_locs:
                        return ("contradicted", 0.85)
        return None

    def _check_graph_contradiction(self, claim: str, fact: str):
        """检查: 知识图谱实体关系推理 → 矛盾（最后兜底检查器）"""
        reasoner = self._get_graph_reasoner()
        if reasoner is None:
            return None
        result = reasoner.infer_contradiction(claim)
        if result and result.get("verdict") == "contradicted":
            return ("contradicted", result.get("confidence", 0.75))
        return None

    def _compare_with_fact(self, claim: str, fact: str) -> tuple:
        """反馈优先 + 责任链: 先查自进化库 → 再跑检查器"""
        # 第一层: 查询自进化反馈库
        if self.enable_feedback:
            record = self.feedback.find_applied_correction(claim, fact)
            if record:
                log.debug("feedback hit", claim=claim[:40])
                return (record["verdict"], record["confidence"])
        # 第二层: 责任链检查器
        for method_name in self._PRIORITY_CHECKERS:
            check = getattr(self, method_name)
            result = check(claim, fact)
            if result:
                log.debug("checker hit", checker=method_name,
                          verdict=result[0], claim=claim[:40])
                return result
        log.debug("all checkers miss", claim=claim[:40])
        return ("uncertain", 0.5)

    def _record_feedback(self, claim: str, fact: str, result: dict) -> None:
        """记录反馈（跳过已有记录避免重复）"""
        if not self.enable_feedback:
            return
        try:
            existing = self.feedback.find_similar(claim, fact)
            if not existing:
                self.feedback.FeedbackRecord(
                    claim=claim,
                    fact=fact,
                    verdict=result["verdict"],
                    confidence=result["confidence"],
                    evidence=result.get("evidence", ""),
                    source=result.get("source", ""),
                )
                # 插入
                import feedback_store
                feedback_store.insert_record(feedback_store.FeedbackRecord(
                    claim=claim,
                    fact=fact,
                    verdict=result["verdict"],
                    confidence=result["confidence"],
                    evidence=result.get("evidence", ""),
                    source=result.get("source", ""),
                ))
        except (OSError, ValueError, AttributeError):
            pass  # 反馈记录失败不阻塞主流程

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


def _load_config():
    """Load configuration from config.json, return dict or empty dict on failure."""
    config_path = Path(__file__).parent / "config.json"
    try:
        with open(config_path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

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
        self._generate_warnings(report, contradicted, uncertain)

        return report

    def _generate_warnings(self, report, contradicted: int, uncertain: int):
        """Generate warnings from verification results."""
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


def generate_correction_prompt(text: str) -> str:
    """分析文本，若有事实矛盾则生成纠正性提示，供注入 LLM system prompt。
    返回空字符串表示无需纠正。"""
    detector = HallucinationDetector()
    report = detector.analyze(text)
    corrections = []
    for r in report.results:
        if r.verdict == 'contradicted' and r.evidence:
            corrections.append(
                f"- 用户说「{r.claim}」，但已知事实是：{r.evidence}（来源：{r.source}）"
            )
    if not corrections:
        return ''
    parts = [
        '[觉察层 · 自动事实纠正]',
        '以下用户消息中存在与已知事实矛盾的内容，请在回复中礼貌纠正：',
    ]
    parts.extend(corrections)
    parts.append('纠正时请引用可靠来源，保持礼貌和专业。')
    return chr(10).join(parts)

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
