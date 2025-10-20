from services.api.main import detect_lang


def test_detect_lang_en_fr():
    assert detect_lang("This is an English sentence.") == "en"
    assert detect_lang("Ceci est une phrase française.") == "fr"
