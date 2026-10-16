from pathlib import Path

import pytest

from openfitkit.settings import Settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in (
        "OPENFITKIT_PROVIDER", "OPENFITKIT_MODEL", "OPENFITKIT_API_KEY", "OPENROUTER_API_KEY",
        "OPENFITKIT_DATA_DIR", "OPENFITKIT_PORT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_offline_and_data_is_outside_checkout(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "app-data"))
    settings = Settings.from_env()
    assert settings.provider == "demo"
    assert settings.port == 8766
    assert settings.data_dir == tmp_path / "app-data/openfitkit"
    assert settings.public() == {
        "provider": "demo", "model": "offline-example", "demo": True, "configured": True,
    }


def test_demo_ignores_live_model_and_both_keys(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-router-example-do-not-show")
    monkeypatch.setenv("OPENFITKIT_API_KEY", "private-example-do-not-show")
    monkeypatch.setenv("OPENFITKIT_MODEL", "unused model with spaces")
    settings = Settings.from_env()
    assert settings.provider == "demo"
    assert settings.model == ""
    assert settings.api_key == ""
    assert "private-example-do-not-show" not in repr(settings)
    assert "private-example-do-not-show" not in str(settings.public())
    assert "private-router-example-do-not-show" not in str(settings.public())
    assert set(settings.public()) == {"provider", "model", "demo", "configured"}


def test_explicit_live_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENFITKIT_PROVIDER", " OpenRouter ")
    monkeypatch.setenv("OPENFITKIT_MODEL", "google/gemini-example:variant")
    monkeypatch.setenv("OPENROUTER_API_KEY", " router-private-example ")
    monkeypatch.setenv("OPENFITKIT_API_KEY", "legacy-private-example")
    monkeypatch.setenv("OPENFITKIT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENFITKIT_PORT", "9001")
    settings = Settings.from_env()
    assert settings.provider == "openrouter"
    assert settings.model == "google/gemini-example:variant"
    assert settings.api_key == "router-private-example"
    assert settings.data_dir == tmp_path
    assert settings.port == 9001
    assert settings.public()["configured"] is True
    assert "data_dir" not in settings.public()
    assert "private-example" not in repr(settings)
    assert "private-example" not in str(settings.public())


@pytest.mark.parametrize("standard_key", [None, "", "  "])
def test_explicit_openrouter_accepts_legacy_key_fallback(monkeypatch, standard_key):
    monkeypatch.setenv("OPENFITKIT_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENFITKIT_MODEL", "example/model")
    if standard_key is not None:
        monkeypatch.setenv("OPENROUTER_API_KEY", standard_key)
    monkeypatch.setenv("OPENFITKIT_API_KEY", " legacy-private-example ")
    settings = Settings.from_env()
    assert settings.api_key == "legacy-private-example"
    assert settings.public()["configured"] is True


@pytest.mark.parametrize("value", ["0", "65536", "abc", "1.2", ""])
def test_invalid_ports_fail_without_echoing_input(monkeypatch, value):
    monkeypatch.setenv("OPENFITKIT_PORT", value)
    with pytest.raises(ValueError, match="OPENFITKIT_PORT must be"):
        Settings.from_env()


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="OPENFITKIT_PROVIDER"):
        Settings(provider="unknown")


@pytest.mark.parametrize("model", [
    "", "model-without-vendor", "/model", "vendor/", "vendor/model/extra",
    "bad model", "https://example.test?token=secret", "vendor/" + "m" * 174,
    "vendor/model\nsecret", "vendor/model:alias:other", "vendor/model:",
])
def test_invalid_live_model_is_rejected_without_echoing_it(model):
    with pytest.raises(ValueError, match="OpenRouter requires OPENFITKIT_MODEL") as error:
        Settings(provider="openrouter", model=model)
    assert str(error.value) == "OpenRouter requires OPENFITKIT_MODEL as a vendor/model ID of at most 180 characters."


@pytest.mark.parametrize("model", [
    "google/gemini-example", "vendor/model:free", "openrouter/auto",
    "vendor-name/model_name.v1:extended", "vendor/" + "m" * 173,
])
def test_vendor_model_slugs_and_colon_aliases_are_supported(model):
    assert Settings(provider="openrouter", model=model).model == model


def test_old_direct_provider_explains_how_to_migrate_without_exposing_key(monkeypatch):
    monkeypatch.setenv("OPENFITKIT_PROVIDER", "openai")
    monkeypatch.setenv("OPENFITKIT_API_KEY", "private-old-key")
    monkeypatch.setenv("OPENFITKIT_MODEL", "old-model")
    with pytest.raises(ValueError) as error:
        Settings.from_env()
    assert "Direct OpenAI routing is no longer supported" in str(error.value)
    assert "OPENFITKIT_PROVIDER=openrouter" in str(error.value)
    assert "OPENFITKIT_MODEL=vendor/model" in str(error.value)
    assert "OPENROUTER_API_KEY" in str(error.value)
    assert "private-old-key" not in str(error.value)


def test_missing_live_configuration_is_publicly_visible():
    settings = Settings(provider="openrouter", model="example/model")
    assert settings.public() == {
        "provider": "openrouter", "model": "example/model", "demo": False, "configured": False,
    }
    assert Settings(provider="openrouter", model="example/model", api_key="  ").public()["configured"] is False


def test_default_location_uses_home_when_xdg_is_unset(monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert Settings().data_dir == Path.home() / ".local/share/openfitkit"
