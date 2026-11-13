import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


def _global_env_path() -> Path:
    if os.name == "nt":
        config_home = os.environ.get("APPDATA", "~/AppData/Roaming")
    else:
        config_home = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(config_home).expanduser() / "research-mapper" / ".env"


def load_environment(env_file: str | None = None) -> None:
    """
    Loads configuration from environment variables and .env files.

    Precedence (highest to lowest): variables already exported in the shell,
    an explicit ``env_file``, ``./.env`` (or a parent directory's), and
    finally a machine-wide fallback (``$XDG_CONFIG_HOME/research-mapper/.env``,
    or ``%APPDATA%\\research-mapper\\.env`` on Windows). Already-set
    variables are never overridden, so higher-precedence sources just need
    to be loaded first.
    :param env_file: optional explicit path to a .env file.
    :return: Nothing.
    """
    if env_file:
        path = Path(env_file)
        if not path.is_file():
            msg = f"--env-file {env_file} does not exist"
            raise FileNotFoundError(msg)
        load_dotenv(path)
    # usecwd=True: without it, load_dotenv() searches upward from the *calling
    # file's* location rather than the user's actual working directory — for an
    # installed console script, that's somewhere in site-packages, never the
    # user's cwd, so their local .env would silently never be found.
    load_dotenv(find_dotenv(usecwd=True))
    load_dotenv(_global_env_path())
