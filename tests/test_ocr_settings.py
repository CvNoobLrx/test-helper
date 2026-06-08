from src.core.settings import load_settings, resolve_path


def test_ocr_settings_are_loaded():
    settings = load_settings(resolve_path("config/settings.yaml"))

    assert settings.ocr is not None
    assert settings.ocr.mode == "auto"
    assert settings.ocr.provider == "rapidocr"
    assert settings.ocr.dpi == 180
    assert settings.ocr.min_text_chars_per_page == 30
