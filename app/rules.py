"""Deterministic rule lookup. Textual refs are not globally unique."""

from dataclasses import dataclass
import hashlib
import json
import re

TOPICS = {
    'complaint.cheat': r'\bчит|cheat|сторонн.{0,20}(по|программ)',
    'complaint.insult': r'оскорб|нецензур|матер|расизм',
    'complaint.dm': r'\bdm\b|\bдм\b|убийств|убивать|урон',
    'complaint.scam': r'обман|мошен|вымог',
    'complaint.rmt_ads': r'реклам|реальн.{0,15}деньг|продаж.{0,15}аккаунт',
}


def terms(text):
    return {word[:5] for word in re.findall(r'[а-яa-z]{3,}', text.casefold().replace('ё', 'е'))}


@dataclass(frozen=True)
class Rule:
    section_id: int
    section: str
    ref: str
    text: str
    rules_hash: str

    def citation(self) -> dict:
        return {
            "section_id": self.section_id,
            "ref": self.ref,
            "rules_hash": self.rules_hash,
            "excerpt": self.text[:180],
        }


class RuleIndex:
    def __init__(self, rules: list[Rule]):
        self.rules = rules
        self.by_key = {(rule.section_id, rule.ref): rule for rule in rules}
        if len(self.by_key) != len(rules):
            raise ValueError("Duplicate rule key within a section")

    @classmethod
    def from_data(cls, data: dict) -> "RuleIndex":
        version = hashlib.sha256(
            json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        rules = [
            Rule(section_id=section["id"], section=section["category"],
                 ref=point["ref"], text=point["text"], rules_hash=version)
            for section in data["rules"] for point in section.get("points", [])
        ]
        return cls(rules)

    @classmethod
    def from_file(cls, path: str) -> "RuleIndex":
        with open(path, encoding="utf-8") as stream:
            return cls.from_data(json.load(stream))

    def resolve(self, ref: str, section_id: int | None = None) -> Rule | None:
        if section_id is not None:
            return self.by_key.get((section_id, ref))
        matches = [rule for rule in self.rules if rule.ref == ref]
        return matches[0] if len(matches) == 1 else None

    def search(self, text, category, ref=None, limit=5):
        """Lexical candidates only; scores are not calibrated relevance probabilities."""
        pattern = TOPICS.get(category)
        if not pattern:
            return []
        query = terms(text)
        ranked = []
        for rule in self.rules:
            if ref is not None and rule.ref != ref:
                continue
            content = rule.text.casefold().replace('ё', 'е')
            if not re.search(pattern, content):
                continue
            # Do not infer a prohibition from a definition or an explicit permission.
            if not re.search(r'запрещ|нельзя|недопуст|не допуска', content):
                continue
            if re.search(r'не запрещ|разреш|допускается', content.replace('не допускается', '')):
                continue
            overlap = len(query & terms(content))
            ranked.append((rule, overlap))
        ranked.sort(key=lambda item: (-item[1], item[0].section_id, item[0].ref))
        return ranked[:limit]

    def relevant_rule(self, text, category, ref):
        candidates = self.search(text, category, ref=ref, limit=len(self.rules))
        # Lexical ranking cannot prove section scope; multiple matches require a human.
        return candidates[0][0] if len(candidates) == 1 else None

    def validate_citation(self, citation):
        rule = self.by_key.get((citation.get('section_id'), citation.get('ref')))
        return bool(rule and citation.get('rules_hash') == rule.rules_hash
                    and citation.get('excerpt') == rule.text[:180])
