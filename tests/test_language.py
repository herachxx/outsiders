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


def test_kazakh_without_special_letters_and_ukrainian_markers():
    assert detect('осындай секс керек па саған').lang == 'kk'
    assert detect('Маған не үшін бан берді').lang == 'kk'
    assert detect('2.1оп дати бан на 31 день щоб знав як потрібно розмовляти').lang == 'und'
    assert detect('қғ қғ').lang == 'und'


def test_kazakh_word_with_i_is_not_swallowed_by_the_ukrainian_branch():
    assert detect('сіз маған неге бан бердіңіз').lang == 'kk'
    assert detect('адмін розверни мене пожалуста').lang == 'und'


def test_cp1251_look_alike_kazakh_letters_are_recognised_but_ukrainian_is_not_converted():
    assert detect('Кґмек керек, ќалай жїктейміз').lang == 'kk'
    assert detect('машинамды ќалай серверге жїктей аламын').lang == 'kk'
    assert detect('сервеге кіріп шыќќаннан кейін кґлігімді таппай ќалдым').lang == 'kk'
    ukrainian = detect('оск матері в голосової чат, їде зброї поліції')
    assert ukrainian.lang == 'und' and ukrainian.uncertain


def test_extra_cp1251_look_alike_letters_from_the_task_example():
    text = 'Квест жҧмыс істемейді жјне маркер шыќпады, текстурада тўрып ќалдым, кљмектесіѕіздерші'
    assert detect(text).lang == 'kk'
