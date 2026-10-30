"""Deterministic safe baseline, shared by HTTP and batch interfaces."""

import re

from .rules import RuleIndex
from .schemas import TriageRequest
from .priority import route, MANDATORY_HUMAN
from .preprocess import before_admin, player_text as extract_player_text, normalize
from .language import detect, language
from .facts import extract_facts
from .draft import build_draft
from .safety import check_draft


CATEGORY_PATTERNS = {
    "complaint": [
        ("complaint.admin", r"админ|администратор|admin"),
        ("complaint.cheat", r"чит|cheat|aimbot|аимбот|летает|сквозь стен"),
        ("complaint.scam", r"обман|мошен|вымог|скам"),
        ("complaint.rmt_ads", r"реальн.{0,8}деньг|прода.{0,10}аккаунт|реклам"),
        ("complaint.insult", r"оскорб|матер|унизи|расизм|токсич"),
        ("complaint.dm", r"\bdm\b|\bдм\b|убил|убийств|урон|зел[её]н.{0,5}зон"),
    ],
    "report": [
        ("report.account", r"взлом|аккаунт|парол|не могу войти|пропал.{0,15}имуществ"),
        ("report.payment", r"плат[её]ж|оплат|донат|деньги спис|не пришло.{0,10}(гк|донат)"),
        ("report.complaint", r"оскорб|читер|\bдм\b|убил|жалоб"),
        ("report.help", r"застрял|застряла|баг|телепорт|помогите выбраться"),
        ("report.question", r"как |где |что такое|можно ли|подскажите"),
    ],
}

class TriageService:
    def __init__(self, rules: RuleIndex, classifier=None):
        self.rules = rules
        self.classifier = classifier

    def triage(self, payload: dict | TriageRequest) -> dict:
        request = payload if isinstance(payload, TriageRequest) else TriageRequest.model_validate(payload)
        facts = extract_facts(request)
        player_text = extract_player_text(request.messages)
        search_text = normalize(player_text)
        language_decision = detect(player_text)
        lang = language_decision.lang
        heuristic_category = self._category(request.kind, search_text)
        predicted = self.classifier.predict(request.kind, search_text) if self.classifier else None
        category = predicted or heuristic_category
        # An uncalibrated model must not override existing sensitive routing.
        safety_override = heuristic_category in MANDATORY_HUMAN and category != heuristic_category
        if safety_override:
            category = heuristic_category
        has_attachments = request.images_count > 0 or any(m.attachments > 0 for m in before_admin(request.messages) if m.role == 'player')
        routing = route(category, search_text, has_attachments)
        priority = routing.priority
        rule_ref = (request.rule_refs_raw or "").strip()
        claimed_refs = re.findall(r"\b\d+(?:\.\d+){1,2}\b", rule_ref)
        reasons = ["history_unavailable", *routing.reasons]
        confidence = 0.0
        if predicted and not safety_override and hasattr(self.classifier, 'confidence'):
            confidence = self.classifier.confidence(request.kind, search_text)
        if self.classifier:
            reasons.append(('classifier_calibrated' if confidence else 'classifier_uncalibrated') if predicted else 'classifier_fallback')
        if safety_override:
            reasons.append('sensitive_category_override')
        if language_decision.uncertain:
            reasons.append("language_uncertain")
        if language_decision.mixed:
            reasons.append('language_mixed')
        cited = []
        for ref in dict.fromkeys(claimed_refs):
            candidates = [rule for rule in self.rules.rules if rule.ref == ref]
            if not candidates:
                reasons.append("rule_ambiguous_or_unknown")
                continue
            if not self.rules.search(search_text, category, ref=ref):
                reasons.append("rule_irrelevant_to_category")
                continue
            rule = self.rules.relevant_rule(search_text, category, ref)
            if rule is None:
                reasons.append("rule_ambiguous_or_unknown")
                continue
            citation = rule.citation()
            if self.rules.validate_citation(citation):
                cited.append(citation)
        if rule_ref and not claimed_refs:
            reasons.append("rule_unparsed")
        if request.kind == "complaint":
            reasons.append("evidence_not_verified")
        needs_human = routing.needs_human or language_decision.uncertain
        draft = build_draft(request, category, lang, has_attachments, cited)
        draft, safety_reasons = check_draft(draft, self.rules, request, category, lang, has_attachments)
        reasons.extend(safety_reasons)
        if safety_reasons:
            needs_human = True
        return {
            "lang": lang,
            "category": category,
            "priority": priority,
            "is_spam_or_duplicate": False,
            "extracted": {
                "nickname": request.reported_nick if request.kind == "complaint" else None,
                "rule_refs": claimed_refs,
                "has_evidence": has_attachments,
                "claims": [fact.value for fact in facts if fact.kind == 'claim'],
            },
            "draft_reply": draft,
            "needs_human": needs_human,
            "confidence": confidence,  # Probability of category only, not draft correctness.
            "reasons": reasons,
        }

    @staticmethod
    def _category(kind: str, text: str) -> str:
        for category, pattern in CATEGORY_PATTERNS[kind]:
            if re.search(pattern, text):
                return category
        return "complaint.other" if kind == "complaint" else "report.offtopic"
