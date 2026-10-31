from app.language import detect


def test_shared_letters_do_not_force_kazakh():
    assert detect('қғ қғ').lang == 'und'
    assert detect('Ҳисобимга киролмаяпман').lang == 'uz'
    assert detect('Маған көмек керек').lang == 'kk'


def test_uncertain_short_mixed_and_transliterated_text():
    assert detect('ok').lang == 'und'
    assert detect('pomogite vernite akkaunt').lang == 'lat'
    assert detect('Salom iltimos yordam bering').lang == 'uz'
    assert detect('помогите please help').mixed
    assert detect('https://example.com 123').lang == 'und'


def test_model_threshold_and_unsupported_language():
    class Model:
        def __init__(self, label, scores): self.label, self.scores = label, scores
        def predict(self, text, k): return [self.label, '__label__ru'], self.scores
    assert detect('please help me', Model('__label__en', [.95, .04])).lang == 'en'
    assert detect('please help me', Model('__label__en', [.6, .4])).lang == 'und'
    assert detect('please help me', Model('__label__de', [.95, .04])).lang == 'und'


def test_clear_text_is_confident_and_ambiguous_scripts_stay_uncertain():
    assert not detect('Он меня оскорбил в общем чате без причины').uncertain
    assert detect('Он меня оскорбил в общем чате без причины').lang == 'ru'
    assert not detect('Маған көмек керек, аккаунтқа кіре алмаймын').uncertain
    uz = detect('onam haqorat qilib meni sababsiz otib ketdi')
    assert uz.lang == 'uz' and not uz.uncertain
    assert detect('Hello, please help me with the car').lang == 'en'
    assert detect('адмін розверни мене пожалуста').uncertain          # Ukrainian/і-only
    assert detect('sk <url>').lang == 'und'                            # rule code, no language signal
    assert detect('Miras_Baranov52 деген не үшін бан').lang == 'kk'    # nickname ignored
