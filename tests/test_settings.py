from pathlib import Path

import pytest

from openfitkit.settings import Settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in (
        "OPENFITKIT_PROVIDER", "OPENFITKIT_MODEL", "OPENFITKIT_API_KEY",
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


def test_demo_ignores_live_model_and_does_not_expose_key(monkeypatch):
    monkeypatch.setenv("OPENFITKIT_API_KEY", "private-example-do-not-show")
    monkeypatch.setenv("OPENFITKIT_MODEL", "unused model with spaces")
    settings = Settings.from_env()
    assert settings.provider == "demo"
    assert settings.model == ""
    assert "private-example-do-not-show" not in repr(settings)
    assert "private-example-do-not-show" not in str(settings.public())
    assert set(settings.public()) == {"provider", "model", "demo", "configured"}


def test_explicit_live_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENFITKIT_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENFITKIT_MODEL", "google/gemini-example:variant")
    monkeypatch.setenv("OPENFITKIT_API_KEY", "test-secret")
    monkeypatch.setenv("OPENFITKIT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENFITKIT_PORT", "9001")
    settings = Settings.from_env()
    assert settings.model == "google/gemini-example:variant"
    assert settings.data_dir == tmp_path
    assert settings.port == 9001
    assert settings.public()["configured"] is True
    assert "data_dir" not in settings.public()


@pytest.mark.parametrize("value", ["0", "65536", "abc", "1.2", ""])
def test_invalid_ports_fail_without_echoing_input(monkeypatch, value):
    monkeypatch.setenv("OPENFITKIT_PORT", value)
    with pytest.raises(ValueError, match="OPENFITKIT_PORT must be"):
        Settings.from_env()


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="OPENFITKIT_PROVIDER"):
        Settings(provider="unknown")


@pytest.mark.parametrize("model", ["bad model", "https://example.test?token=secret", "m" * 181, "m\nsecret"])
def test_invalid_live_model_is_rejected_without_echoing_it(model):
    with pytest.raises(ValueError) as error:
        Settings(provider="openai", model=model)
    assert model not in str(error.value)


def test_missing_live_configuration_is_publicly_visible():
    assert Settings(provider="openai").public()["configured"] is False
    assert Settings(provider="openai", model="test-model").public()["configured"] is False


def test_default_location_uses_home_when_xdg_is_unset(monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert Settings().data_dir == Path.home() / ".local/share/openfitkit"
