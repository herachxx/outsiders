"""Deterministic safe baseline, shared by HTTP and batch interfaces."""

import re

from .rules import RuleIndex
from .schemas import TriageRequest
from .priority import route, MANDATORY_HUMAN, multilingual_sensitive_category
from .preprocess import before_admin, player_text as extract_player_text, normalize
from .language import detect, language
from .facts import extract_facts
from .confidence import lookup
from .handling import decide
from .draft import build_draft
from .safety import check_draft


CATEGORY_PATTERNS = {
    "complaint": [
        ("complaint.admin", r"админ|администратор|admin|не\s?согл|снят[ье]?.{0,12}(бан|варн|наказ|блок)|разбан|амнисти|пересмотр|перевыда|ошибк\w* бана"),
        ("complaint.cheat", r"чит|cheat|aimbot|аимбот|летает|сквозь стен|\bсофт|\bsoft\b|\bфаст|скейт|кулак|прошивает|багоюз|багаюз"),
        ("complaint.scam", r"обман|мошен|вымог|скам"),
        ("complaint.rmt_ads", r"реальн.{0,8}деньг|прода.{0,10}аккаунт|реклам"),
        ("complaint.insult", r"\bоск|\bosk|оскорб|обзыва|матер|унизи|расизм|национальност|токсич|род(?:ни|ных|ню|ным)|\bмам[ауыеой]\b|\bмать\b|упом|обозвал|послал|[hx]aqorat|\bock\b|порнограф|хуй|хуе|пизд|ебан|шлюх|уебищ|долбаеб|\bсука\b|мразь"),
        ("complaint.dm", r"\bdm\b|\bдм\b|убил|убива|убийств|застрел|задави|задов|посад\w*.{0,25}(без причин|просто так|не за что)|урон|зел[её]н.{0,5}зон|deathmatch|drive.?by|\bnrp\b|\borp\b|\bурп\b|\bпго\b|\bcop\b"),
    ],
    "report": [
        ("report.account", r"взлом|аккаунт|парол|не могу войти|пропал.{0,15}имуществ"),
        ("report.payment", r"плат[её]ж|оплат|донат|деньги спис|не пришло.{0,10}(гк|донат)"),
        ("report.complaint", r"\bоск|оскорб|обзыва|\bчит|\bсофт|\bдм\b|\bdm\b|\bск\b|убил|убива|жалоб|(?:айди|\bid)\s*\d|\d\s*(?:дм|ск|dm)\b"),
        ("report.help", r"застрял|застряла|баг|телепорт|помогите выбраться|переверн|открой.{0,6}двер|выпусти|випусти|вытащи|машин.{0,15}(?:в воду|перевер)|moshina.{0,25}(?:och|tamir|ayl)|bag bo|kishan|qamal"),
        ("report.question", r"как |где |что такое|можно ли|подскажите|скажите|\?|сколько|почему|когда|что делать|\bnega\b|\bnima\b|qanday|\bwhat\b|\bhow\b|\bwhere\b"),
    ],
}

CITE_MIN_CONFIDENCE = 0.7  # a wrong category would make the cited point irrelevant


def category_rule_ref(category: str, text: str) -> str | None:
    """General taxonomy point for a complaint category; none where no single point fits (dm, admin, other)."""
    if category == 'complaint.insult':
        return '2.1'
    if category == 'complaint.cheat':
        return '5.2'
    if category == 'complaint.scam':
        return '4.2' if re.search(r'вымог|угроз', text) else '4.1'
    if category == 'complaint.rmt_ads':
        return '2.3' if re.search(r'реклам', text) else '4.4'
    return None


# Hints from the player-filled rule field; taxonomy rule refs, not verified claims.
REF_HINTS = [
    ("complaint.dm", r"\bgz\b|\bdm\b|\bдм\b|\bdb\b|\bдб\b|\bsk\b|\bск\b|\btk\b|\bтк\b|(?<![\w.])5\.[34](?![\d.])|\bnrp\b|\bнрп\b|\bурп\b"),
    ("complaint.cheat", r"(?<![\w.])5\.2(?![\d.])|чит|софт|\bsoft\b|\bсб\b"),
    ("complaint.scam", r"(?<![\w.])4\.[12](?![\d.])|скам|\bscam\b"),
    ("complaint.rmt_ads", r"(?<![\w.])(?:2\.3|4\.4)(?![\d.])"),
    ("complaint.insult", r"(?<![\w.])2\.[146](?![\d.])|\bоск|\bosk"),
]


class TriageService:
    def __init__(self, rules: RuleIndex, classifier=None, empirical_confidence: bool = True):
        self.rules = rules
        self.classifier = classifier
        self.empirical_confidence = empirical_confidence

    def triage(self, payload: dict | TriageRequest) -> dict:
        request = payload if isinstance(payload, TriageRequest) else TriageRequest.model_validate(payload)
        facts = extract_facts(request)
        player_text = extract_player_text(request.messages)
        search_text = normalize(player_text)
        language_decision = detect(player_text)
        lang = language_decision.lang
        heuristic_category = self._category(request.kind, search_text, request.rule_refs_raw or '')
        # A specific complaint rule (text or the player's rule field) wins; the model decides the rest.
        # Skipping the model call there saves most of its per-ticket cost without changing the result.
        rule_decided = request.kind == 'complaint' and heuristic_category != 'complaint.other'
        predicted = self.classifier.predict(request.kind, search_text) if self.classifier and not rule_decided else None
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
        model_calibrated = bool(confidence)
        if not confidence and not safety_override and self.empirical_confidence:
            source = 'model' if predicted else ('rule' if rule_decided else 'heuristic')
            confidence = lookup(source, category)
            if confidence:
                reasons.append('confidence_empirical')
        if self.classifier:
            reasons.append(('classifier_calibrated' if model_calibrated else 'classifier_uncalibrated') if predicted else 'classifier_fallback')
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
        if not cited and not safety_override and confidence >= CITE_MIN_CONFIDENCE:
            # Player named no usable point: use the taxonomy point for the category, still unique and relevant.
            default_ref = category_rule_ref(category, search_text)
            rule = self.rules.relevant_rule(search_text, category, default_ref) if default_ref else None
            if rule is not None and self.rules.validate_citation(rule.citation()):
                cited.append(rule.citation())
                reasons.append("citation_from_category")
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
        reasons.append('handling_' + decide(category, priority, needs_human, confidence, reasons, MANDATORY_HUMAN))
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
            "confidence": confidence,  # Category probability or empirical estimate; see reasons.
            "reasons": reasons,
        }

    @staticmethod
    def _category(kind: str, text: str, refs: str = '') -> str:
        if kind == 'report':
            sensitive = multilingual_sensitive_category(text)
            if sensitive:
                return sensitive
        for category, pattern in CATEGORY_PATTERNS[kind]:
            if re.search(pattern, text):
                return category
        if kind == 'complaint':
            # The player's own rule field is only a hint, used when the text names no category.
            refs = normalize(refs or '')
            for category, pattern in REF_HINTS:
                if re.search(pattern, refs):
                    return category
            return "complaint.other"
        return "report.offtopic"
