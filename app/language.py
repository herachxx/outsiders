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


@lru_cache(maxsize=1)
def load_model(path):
    import fasttext
    return fasttext.load_model(path)


def detect(text, model=None):
    text = re.sub(r'https?://\S+|\b\d+(?:\.\d+)*\b', ' ', text.casefold())
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
    # Shared letters қ/ғ alone cannot distinguish Kazakh from Uzbek.
    kazakh = bool(re.search('[әіңүұөһ]', text))
    uzbek = bool(re.search('[ўҳ]', text))
    if kazakh and uzbek:
        return LanguageDecision('und', True, True)
    if kazakh:
        return LanguageDecision('kk', True)
    if uzbek:
        return LanguageDecision('uz', True)
    if latin >= cyrillic * 2:
        tokens = set(re.findall("[a-z']+", text))
        if len(tokens & {'salom', 'iltimos', 'yordam', 'bering', 'hisobim', 'uchun', 'qanday'}) >= 2:
            return LanguageDecision('uz', True)
        return LanguageDecision('lat', True)
    if re.search('[қғ]', text):
        return LanguageDecision('und', True)
    return LanguageDecision('ru', True)


def language(text):
    return detect(text).lang
