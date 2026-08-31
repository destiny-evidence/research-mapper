from unittest.mock import MagicMock, patch

import sys

import httpx
import pytest

from research_mapper import local_destiny_auth
from research_mapper.config import (
    HEALTHCHECK_TIMEOUT,
    NoDestinyCredential,
    configure_dspy,
    get_destiny_client,
    load_environment,
)


# ---------------------------------------------------------------------------
# load_environment — .env discovery must search from the user's actual working
# directory, not wherever config.py happens to be installed (e.g. site-packages
# for a `uv tool install`ed console script), otherwise a local ./.env is
# silently never found. See find_dotenv's `usecwd` parameter.
# ---------------------------------------------------------------------------


def test_load_environment_searches_dotenv_from_cwd():
    with (
        patch("research_mapper.config.find_dotenv") as mock_find_dotenv,
        patch("research_mapper.config.load_dotenv") as mock_load_dotenv,
    ):
        mock_find_dotenv.return_value = "/home/user/project/.env"

        load_environment()

        mock_find_dotenv.assert_called_once_with(usecwd=True)
        mock_load_dotenv.assert_any_call("/home/user/project/.env")


def test_load_environment_explicit_env_file_takes_precedence(tmp_path):
    env_file = tmp_path / "custom.env"
    env_file.write_text("MAPPER_LLM_MODEL=custom\n")

    with (
        patch("research_mapper.config.find_dotenv") as mock_find_dotenv,
        patch("research_mapper.config.load_dotenv") as mock_load_dotenv,
    ):
        mock_find_dotenv.return_value = ""

        load_environment(str(env_file))

        first_call_path = mock_load_dotenv.call_args_list[0].args[0]
        assert first_call_path == env_file


# ---------------------------------------------------------------------------
# configure_dspy — the LLM sanity check must accept any non-empty response,
# not just literal "hello world": different providers/models phrase their
# reply differently (e.g. "Hello, world! 🌍", capitalised, punctuated,
# translated, etc.), so asserting an exact substring/element match rejects
# perfectly valid responses.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _required_env(monkeypatch):
    monkeypatch.setenv("MAPPER_LLM_MODEL", "test-model")
    monkeypatch.setenv("MAPPER_LLM_BASE_URL", "https://example.test")
    monkeypatch.setenv("MAPPER_LLM_API_KEY", "test-key")


@pytest.mark.parametrize(
    "response",
    [
        ["Hello, world! 🌍"],
        ["HELLO WORLD"],
        ["Bonjour le monde"],
    ],
)
def test_configure_dspy_accepts_any_non_empty_response(response):
    with patch("research_mapper.config.dspy") as mock_dspy:
        mock_dspy.LM.return_value = MagicMock(return_value=response)

        configure_dspy()

        mock_dspy.configure.assert_called_once()


@pytest.mark.parametrize("response", [[], [""], [None]])
def test_configure_dspy_warns_on_an_empty_response_but_still_configures(response):
    """A useless reply is worth a warning, not a worker that will not boot."""
    with (
        patch("research_mapper.config.dspy") as mock_dspy,
        patch("research_mapper.config.logger") as mock_logger,
    ):
        mock_dspy.LM.return_value = MagicMock(return_value=response)

        configure_dspy()

        mock_logger.warning.assert_called_once()
        mock_dspy.configure.assert_called_once()


# ---------------------------------------------------------------------------
# get_destiny_client — authentication must happen eagerly, when the client is
# built, not deferred until a caller's first search/lookup — a bad credential
# or unreachable DESTINY instance should fail at startup, not on first use.
# ---------------------------------------------------------------------------


@pytest.fixture
def _no_credential(monkeypatch):
    for name in (
        "AZURE_CLIENT_ID",
        "MAPPER_DESTINY_APPLICATION_ID",
        local_destiny_auth.REFRESH_TOKEN_VAR,
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _clear_destiny_client_cache():
    get_destiny_client.cache_clear()
    yield
    get_destiny_client.cache_clear()


def test_get_destiny_client_triggers_auth_eagerly(monkeypatch, _no_credential):
    # With no credential the SDK opens a browser, which is only allowed at a
    # terminal — so this is the interactive path.
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    with patch("research_mapper.config.OAuthClient") as mock_oauth_client:
        mock_instance = mock_oauth_client.return_value

        get_destiny_client()

        mock_instance.get_client.return_value.get.assert_called_once_with(
            "/v1/system/healthcheck/", timeout=httpx.USE_CLIENT_DEFAULT
        )


def test_get_destiny_client_uses_managed_identity_when_configured(monkeypatch):
    monkeypatch.setenv("AZURE_CLIENT_ID", "client-id")
    monkeypatch.setenv("MAPPER_DESTINY_APPLICATION_ID", "app-id")
    monkeypatch.delenv("MAPPER_DESTINY_ENV", raising=False)

    with (
        patch("research_mapper.config.OAuthClient") as mock_oauth_client,
        patch("research_mapper.config.OAuthMiddleware") as mock_middleware,
    ):
        get_destiny_client()

        mock_middleware.assert_called_once_with(
            azure_client_id="client-id",
            azure_application_id="app-id",
            use_managed_identity=True,
        )
        mock_oauth_client.assert_called_once_with(
            auth=mock_middleware.return_value, env="production"
        )


def test_get_destiny_client_is_cached(monkeypatch, _no_credential):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    with patch("research_mapper.config.OAuthClient"):
        first = get_destiny_client()
        second = get_destiny_client()

        assert first is second


# A missing DESTINY credential used to hang forever: the SDK falls back to
# opening a browser, and a worker container has nobody to open it for.
# ---------------------------------------------------------------------------


def test_no_credential_without_a_terminal_fails_instead_of_waiting(
    monkeypatch, _no_credential
):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with patch("research_mapper.config.OAuthClient") as mock_oauth_client:
        with pytest.raises(NoDestinyCredential, match="no terminal"):
            get_destiny_client()

        # It gives up before building anything, so nothing can block.
        mock_oauth_client.assert_not_called()


def test_the_error_says_how_to_fix_it(monkeypatch, _no_credential):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with patch("research_mapper.config.OAuthClient"):
        with pytest.raises(NoDestinyCredential) as raised:
            get_destiny_client()

    message = str(raised.value)
    assert local_destiny_auth.REFRESH_TOKEN_VAR in message
    assert "research_mapper login" in message


def test_a_stored_token_needs_no_terminal_and_bounds_the_healthcheck(monkeypatch):
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    monkeypatch.delenv("MAPPER_DESTINY_APPLICATION_ID", raising=False)
    monkeypatch.setenv(local_destiny_auth.REFRESH_TOKEN_VAR, "a-token")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with (
        patch("research_mapper.config.OAuthClient") as mock_oauth_client,
        patch.object(local_destiny_auth, "RefreshTokenAuth"),
        patch.object(local_destiny_auth, "auth_code_flow"),
    ):
        get_destiny_client()

        # Nothing here waits on a human, so an unreachable DESTINY must time out
        # rather than hang the worker.
        mock_oauth_client.return_value.get_client.return_value.get.assert_called_once_with(
            "/v1/system/healthcheck/", timeout=HEALTHCHECK_TIMEOUT
        )
