#!/usr/bin/env python3
"""
KB 生成器 — 从实体定义自动生成知识库事实

实体格式 (JSON):
{
  "name": "牛顿",
  "type": "person",
  "birth": 1643, "death": 1727,
  "country": "英国",
  "era": "17-18世纪",
  "known_for": ["万有引力定律", "三大运动定律", "微积分"],
  "relations": [
    {"verb": "发明", "target": "反射望远镜"},
    {"verb": "发现", "target": "万有引力"}
  ],
  "negate": ["被苹果砸中发现万有引力"],
  "source": "物理学史"
}

→ 自动生成 8-12 条事实

用法:
  python3 ci/kb_generator.py --input entities.json --output kb_generated.json
"""

import json, sys
from pathlib import Path
from typing import Optional


class KBGenerator:
    """从实体定义生成 KB 事实"""

    # 关系动词 → 否定模板
    NEGATION_TEMPLATES = {
        "发明": "{name}不是{target}的唯一发明者",
        "发现": "{name}不是第一个发现{target}的人",
        "创造": "{name}没有创造{target}",
        "建立": "{name}不是{target}的唯一建立者",
        "撰写": "{name}可能不是{target}的唯一作者",
    }

    def generate(self, entity: dict) -> dict:
        """从实体生成 KB 条目，返回 {key: {facts, source}}"""
        name = entity["name"]
        etype = entity.get("type", "person")
        facts = []
        source = entity.get("source", "自动生成")

        # 1. 生卒年份
        birth = entity.get("birth")
        death = entity.get("death")
        if birth and death:
            facts.append(f"{name}出生于{birth}年，逝世于{death}年")
        elif birth:
            facts.append(f"{name}出生于{birth}年")
        elif death:
            facts.append(f"{name}逝世于{death}年")

        # 2. 国籍/时代
        country = entity.get("country")
        if country:
            facts.append(f"{name}是{country}人" if etype == "person" else f"{name}位于{country}")

        era = entity.get("era")
        if era:
            facts.append(f"{name}是{era}时期的人物" if etype == "person" else f"{name}建于{era}")

        # 3. 知名成就
        known_for = entity.get("known_for", [])
        for achievement in known_for[:3]:
            facts.append(f"{name}以{achievement}闻名")

        # 4. 关系事实
        relations = entity.get("relations", [])
        for rel in relations:
            verb = rel.get("verb", "")
            target = rel.get("target", "")
            if verb and target:
                facts.append(f"{name}{verb}了{target}")
                # 否定模板
                if verb in self.NEGATION_TEMPLATES:
                    facts.append(self.NEGATION_TEMPLATES[verb].format(name=name, target=target))

        # 5. 错误认知否定
        negate = entity.get("negate", [])
        for n in negate:
            facts.append(f"{name}不是{n}")

        # 6. 自定义事实
        custom = entity.get("facts", [])
        facts.extend(custom)

        return {
            name: {
                "facts": facts,
                "source": source,
            }
        }

    def generate_batch(self, entities: list[dict]) -> dict:
        """批量生成 KB 条目"""
        kb = {}
        for entity in entities:
            kb.update(self.generate(entity))
        return kb


def main():
    import argparse
    parser = argparse.ArgumentParser(description="KB 自动生成器")
    parser.add_argument("--input", required=True, help="实体定义 JSON 文件")
    parser.add_argument("--output", default="kb_generated.json", help="输出路径")
    parser.add_argument("--merge", help="合并到现有 KB JSON 文件")
    args = parser.parse_args()

    with open(args.input) as f:
        entities = json.load(f)

    if isinstance(entities, dict):
        entities = list(entities.values())

    gen = KBGenerator()
    kb = gen.generate_batch(entities)

    total_facts = sum(len(v["facts"]) for v in kb.values())
    print(f"✅ 生成 {len(kb)} 个实体, {total_facts} 条事实")

    if args.merge and Path(args.merge).exists():
        with open(args.merge) as f:
            existing = json.load(f)
        existing.update(kb)
        with open(args.output, 'w') as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        print(f"   已合并到 {args.merge} → {args.output}")
    else:
        with open(args.output, 'w') as f:
            json.dump(kb, f, indent=2, ensure_ascii=False)
        print(f"   已保存到 {args.output}")


if __name__ == "__main__":
    main()
