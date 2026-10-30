"""Final gate for the current template backend; arbitrary generated prose is refused."""
import re
from pydantic import ValidationError

from .draft import build_draft
from .preprocess import player_text
from .schemas import Draft

FALLBACK = {
    'ru': 'Для ответа необходима проверка администратором. Уточните обстоятельства обращения.',
    'kk': 'Жауап беру үшін әкімшінің тексеруі қажет. Өтініштің мән-жайын нақтылаңыз.',
    'uz': 'Javob berish uchun administrator tekshiruvi zarur. Murojaat tafsilotlarini aniqlashtiring.',
    'en': 'An administrator needs to review this request. Please clarify the circumstances.',
}
UNSAFE = re.compile(
    r'верн[её]м|разбаним|забаним|нарушение (?:доказано|подтверждено)|'
    r'(?:мы |я )?(?:просмотрели|проверили) (?:скриншот|видео)|'
    r'по скриншотам видно|(?:пришлите|отправьте|сообщите).{0,30}(?:парол|код подтверждения)|'
    r'we (?:will refund|will ban|have verified|reviewed the screenshots)|'
    r'(?:send|provide) (?:your )?(?:password|verification code)', re.IGNORECASE)


def check_draft(candidate, rules, request, category, lang, has_evidence):
    reasons = []
    try:
        parsed = Draft.model_validate(candidate)
        data = parsed.model_dump()
        if not parsed.text.strip() or len(parsed.text) > 4000:
            reasons.append('safety_invalid_text')
        if UNSAFE.search(parsed.text):
            reasons.append('safety_unsafe_statement')
        for citation in data['cited']:
            if not rules.validate_citation(citation):
                reasons.append('safety_invalid_citation')
                continue
            relevant = rules.relevant_rule(player_text(request.messages), category, citation['ref'])
            if relevant is None or relevant.citation() != citation:
                reasons.append('safety_irrelevant_citation')
        # Only the deterministic backend is enabled. No arbitrary prose, hidden
        # instructions or unstructured LLM response may pass as a valid draft.
        expected = build_draft(request, category, lang, has_evidence, data['cited'])
        if data != expected:
            reasons.append('safety_unapproved_draft')
    except (ValidationError, TypeError, ValueError, KeyError):
        reasons.append('safety_invalid_draft')
    if reasons:
        actual_lang = lang if lang in FALLBACK else 'en'
        return {'lang': actual_lang, 'text': FALLBACK[actual_lang], 'cited': []}, sorted(set(reasons))
    return data, []
