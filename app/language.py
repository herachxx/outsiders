"""Conservative language routing with an optional trusted local fastText model."""
from dataclasses import dataclass
from functools import lru_cache
import os
import re

SUPPORTED = {'ru', 'kk', 'uz', 'en', 'es', 'pt'}


@dataclass(frozen=True)
class LanguageDecision:
    lang: str
    uncertain: bool
    mixed: bool = False


UZ_LATIN_WORDS = {
    'salom', 'iltimos', 'yordam', 'bering', 'hisobim', 'uchun', 'qanday', 'chora', 'korila', 'sokdi', 'sokib',
    'onadan', 'haqorat', 'sababsiz', 'sabab', 'menga', 'meni', 'mani', 'manga', 'bilan', 'qilib', 'otib', 'ketdi',
    'kishanladi', 'moshina', 'qurol', 'edim', 'ekan', 'nima', 'noroziman', 'jazo', 'qilyabdi', 'qildi', 'bogan'}
EN_WORDS = {'help', 'please', 'the', 'is', 'my', 'you', 'what', 'how', 'hello', 'where', 'this', 'not', 'and', 'with',
            'was', 'for', 'to', 'me', 'he', 'his', 'it', 'on', 'do', 'i'}
KK_WORDS = {'керек', 'және', 'деген', 'болып', 'емес', 'жоқ', 'саған', 'маған', 'менің', 'неге', 'үшін', 'қалай',
            'осындай', 'болды', 'рахмет', 'сәлем', 'бердi', 'берді', 'сіз', 'біз', 'олар', 'қазір', 'бүгін', 'ештеңе'}
UK_WORDS = {'щоб', 'потрібно', 'мені', 'мене', 'дати', 'знав', 'будь', 'ласка', 'допоможіть', 'який', 'яка', 'їх'}
UZ_CYRILLIC_WORDS = {'билан', 'учун', 'килиб', 'қилиб', 'гаплашиш', 'ёрдам', 'илтимос', 'йўқ', 'уйинчилар', 'тахдид'}
# Rule codes and nicknames carry no language signal.
NOISE = re.compile(r"\b(?:gz|op|dm|sk|tk|db|fw|rp|nrp|orp|url|digits|handle|ck)\b|\b\w+_\w+\b")


@lru_cache(maxsize=1)
def load_model(path):
    import fasttext
    return fasttext.load_model(path)


def detect(text, model=None):
    text = re.sub(r'https?://\S+|\b\d+(?:\.\d+)*\b', ' ', text.casefold())
    text = NOISE.sub(' ', text)
    text = text.translate(str.maketrans({'’': "'", 'ʻ': "'", 'ʼ': "'", '`': "'"}))
    latin = len(re.findall('[a-z]', text))
    cyrillic = len(re.findall('[а-яёәіңғүұқөһўҳ]', text))
    mixed = min(latin, cyrillic) >= 4 and min(latin, cyrillic) / max(latin, cyrillic, 1) > .3
    if latin + cyrillic < 4:
        return LanguageDecision('und', True)
    if mixed:
        return LanguageDecision('und', True, True)
    path = os.environ.get('GRAND_LANGUAGE_MODEL_PATH')
    if model is None and path:
        model = load_model(path)
    if model is not None:
        labels, scores = model.predict(' '.join(text.split()), k=2)
        lang = labels[0].removeprefix('__label__')
        if lang in SUPPORTED and scores[0] >= .8 and (len(scores) == 1 or scores[0] - scores[1] >= .2):
            return LanguageDecision(lang, False)
        return LanguageDecision('und', True)
    # Shared letters қ/ғ alone cannot distinguish Kazakh from Uzbek; і is also Ukrainian/Belarusian.
    kazakh_letters = re.findall('[әңүұөһ]', text)
    uzbek = bool(re.search('[ўҳ]', text))
    if kazakh_letters and uzbek:
        return LanguageDecision('und', True, True)
    if kazakh_letters:
        return LanguageDecision('kk', len(kazakh_letters) < 2 and cyrillic < 20)
    words = set(re.findall('[а-яёіқғәңүұөһ]+', text))
    if not words & UK_WORDS and len(words & KK_WORDS) and not re.search('[їєґ]', text):
        return LanguageDecision('kk', len(words & KK_WORDS) < 2)
    if re.search('[їєґ]', text) or ('і' in text and not re.search('[ыэъ]', text)):
        # Ukrainian/Belarusian (and і-only Kazakh) cannot be told apart from Russian by letters alone.
        return LanguageDecision('und', True)
    if uzbek:
        return LanguageDecision('uz', False)
    if re.search('[їєґ]', text):
        return LanguageDecision('und', True)
    if latin >= cyrillic * 2:
        tokens = set(re.findall("[a-z']+", text))
        uz_hits = len(tokens & UZ_LATIN_WORDS) + (1 if re.search("[og][ʻʼ'`‘’]", text) else 0)
        if uz_hits >= 1 and len(tokens & EN_WORDS) <= uz_hits:
            return LanguageDecision('uz', uz_hits < 2)
        if len(tokens & EN_WORDS) >= 2:
            return LanguageDecision('en', False)
        return LanguageDecision('lat', True)
    if words & UK_WORDS:
        return LanguageDecision('und', True)
    if re.search('[қғ]', text):
        return LanguageDecision('und', True)
    if words & UZ_CYRILLIC_WORDS:
        return LanguageDecision('uz', True)
    # Plain Russian letters only: trust a sentence-sized text, keep short fragments uncertain.
    return LanguageDecision('ru', cyrillic < 8)


def language(text):
    return detect(text).lang
