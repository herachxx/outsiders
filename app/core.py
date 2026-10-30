"""Deterministic safe baseline, shared by HTTP and batch interfaces."""

import re

from .rules import RuleIndex
from .schemas import TriageRequest
from .priority import route, MANDATORY_HUMAN
from .preprocess import before_admin, player_text as extract_player_text, normalize
from .language import detect, language


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

RELEVANT_REFS = {
    "complaint.cheat": {"5.2"},
    "complaint.insult": {"2.1", "2.4", "2.6"},
    "complaint.dm": {"5.3", "5.4"},
    "complaint.scam": {"4.1", "4.2"},
    "complaint.rmt_ads": {"2.3", "4.4"},
}

PREFERRED_SECTIONS = {
    "complaint.cheat": 30,
    "complaint.insult": 30,
    "complaint.dm": 30,
    "complaint.scam": 30,
    "complaint.rmt_ads": 30,
}


class TriageService:
    def __init__(self, rules: RuleIndex, classifier=None):
        self.rules = rules
        self.classifier = classifier

    def triage(self, payload: dict | TriageRequest) -> dict:
        request = payload if isinstance(payload, TriageRequest) else TriageRequest.model_validate(payload)
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
        for ref in claimed_refs:
            candidates = [rule for rule in self.rules.rules if rule.ref == ref]
            if not candidates:
                reasons.append("rule_ambiguous_or_unknown")
                continue
            if ref not in RELEVANT_REFS.get(category, set()):
                reasons.append("rule_irrelevant_to_category")
                continue
            rule = self.rules.resolve(ref, section_id=PREFERRED_SECTIONS.get(category))
            if rule is None:
                reasons.append("rule_ambiguous_or_unknown")
                continue
            cited.append(rule.citation())
        if rule_ref and not claimed_refs:
            reasons.append("rule_unparsed")
        if request.kind == "complaint":
            reasons.append("evidence_not_verified")
        needs_human = routing.needs_human or language_decision.uncertain
        draft = self._draft(lang, category, needs_human)
        if cited and lang == "ru":
            refs = ", ".join(f"{item['section_id']}/{item['ref']}" for item in cited)
            draft += f" Указанные пункты правил ({refs}) будут проверены администратором."
        return {
            "lang": lang,
            "category": category,
            "priority": priority,
            "is_spam_or_duplicate": False,
            "extracted": {
                "nickname": request.reported_nick if request.kind == "complaint" else None,
                "rule_refs": claimed_refs,
                "has_evidence": has_attachments,
                "claims": [player_text] if player_text else [],
            },
            "draft_reply": {"lang": lang, "text": draft, "cited": cited},
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

    @staticmethod
    def _draft(lang: str, category: str, needs_human: bool) -> str:
        if lang == "kk":
            return "Өтінішіңіз қабылданды. Оны әкімші тексереді."
        if lang == "uz":
            return "Murojaatingiz qabul qilindi. Uni administrator tekshiradi."
        if lang == 'es':
            return 'Hemos recibido tu solicitud. Un administrador la revisará.'
        if lang == 'pt':
            return 'Recebemos sua solicitação. Um administrador irá analisá-la.'
        if lang in ("lat", "und", "en"):
            return "Your request has been received. A support agent will review it."
        if category == "report.offtopic":
            return "Пожалуйста, уточните, что произошло и на каком сервере."
        if needs_human:
            return "Спасибо за обращение. Передаём его администратору для проверки."
        return "Спасибо за вопрос. Администратор проверит информацию и ответит вам."
