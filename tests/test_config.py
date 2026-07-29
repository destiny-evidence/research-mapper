from unittest.mock import patch

from research_mapper.config import load_environment


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
