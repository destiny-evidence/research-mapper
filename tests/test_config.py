from unittest.mock import MagicMock, patch

import pytest

from research_mapper.config import configure_dspy, load_environment


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


def test_configure_dspy_rejects_empty_response():
    with patch("research_mapper.config.dspy") as mock_dspy:
        mock_dspy.LM.return_value = MagicMock(return_value=[""])

        with pytest.raises(AssertionError):
            configure_dspy()
