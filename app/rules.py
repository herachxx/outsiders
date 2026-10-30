"""Deterministic rule lookup. Textual refs are not globally unique."""

from dataclasses import dataclass
import hashlib
import json


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
