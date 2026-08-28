import argparse
import logging
import sys
from pathlib import Path

from research_mapper.config import (
    configure_dspy,
    init_destiny_client,
    load_environment,
)
from research_mapper.export import export_mapped_evidence_to_ris
from research_mapper.logs import ColourFormatter, configure_file_logging
from research_mapper.models.common import UserQuery
from research_mapper.orchestrator import (
    NoEvidenceToActOnError,
    ResearchMappingOrchestrator,
    SearchMode,
)
from research_mapper.taxonomy import RepoCommunity
from research_mapper.ui.tui import TerminalUI

_SEARCH_MODE_LABELS = {
    SearchMode.SPARSE: "Sparse search",
    SearchMode.TAXONOMY: "Taxonomy search",
}

_COMMUNITY_LABELS = {
    RepoCommunity.HPV: "HPV Vaccine Delivery",
    RepoCommunity.ESEA: "Education (ESEA)",
}

logger = logging.getLogger(__name__)


def initialise(env_file: str | None) -> None:
    """
    Initialises the destiny_sdk client and DSPy's LLM.
    :param env_file: optional explicit path to a .env file.
    :return: Nothing.
    """
    load_environment(env_file)
    init_destiny_client()
    logger.info("Destiny client ready")
    configure_dspy()


def _parse_args() -> argparse.Namespace:
    """
    Parses command-line arguments for the research-mapper CLI.
    :return: the parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Research Mapper CLI")
    parser.add_argument(
        "query", nargs="?", help="Research question (prompted if omitted)"
    )
    parser.add_argument(
        "--env-file",
        help=(
            "Path to a .env file to load. Overrides ./.env and "
            "~/.config/research-mapper/.env; already-exported shell "
            "variables still take precedence."
        ),
    )
    return parser.parse_args()


def _select_search_modes(tui: TerminalUI) -> set[SearchMode]:
    """
    Prompts the user to choose one or more search modes: sparse (Lucene), taxonomy
    (concept-filter), or both.
    :param tui: the terminal UI to prompt with
    :return: the chosen search mode(s)
    """
    selected = tui.select_from_list(
        list(SearchMode),
        label=lambda mode: _SEARCH_MODE_LABELS[mode],
        title="How would you like to search?",
    )
    return set(selected)


def _select_community(tui: TerminalUI) -> RepoCommunity:
    """
    Prompts the user to choose which repository community's taxonomy to search.
    :param tui: the terminal UI to prompt with
    :return: the chosen repository community
    """
    return tui.select_one(
        list(RepoCommunity),
        label=lambda community: _COMMUNITY_LABELS[community],
        title="Which community's taxonomy?",
    )


def _configure_logging() -> Path | None:
    """
    Configures console and file logging handlers. Console output stays at WARNING level;
    a per-run DEBUG-level file log is always written (see `configure_file_logging`) so
    issues can be traced after the fact regardless of what was visible on screen.
    :return: the log file path if file logging was set up, else None.
    """
    handler = logging.StreamHandler()
    handler.setLevel(logging.WARNING)
    handler.setFormatter(
        ColourFormatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    # These libraries' own DEBUG output is wire-level noise (TCP/TLS framing, full LLM
    # request/response dumps) that dwarfs our own logging without helping trace app bugs —
    # capping them at WARNING keeps the file log focused while still surfacing real errors.
    for noisy_logger in ("dspy", "httpcore", "openai", "asyncio", "LiteLLM"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
    return configure_file_logging()


def main() -> None:
    """
    Main function for running the research-mapper CLI.
    :return: Nothing.
    """
    args = _parse_args()

    tui = TerminalUI()
    logger.info("Starting research-mapper")
    tui.print_welcome()
    tui.print_process_status(
        initialise,
        "Initialising...\n\nPlease authenticate your DESTINY credentials in your browser.\nA page should have opened automatically.",
        args.env_file,
        complete_message="[green]✓[/green] Initialisation Successful!",
    )

    community = _select_community(tui)
    search_modes = _select_search_modes(tui)

    query = args.query or tui.prompt_user("How can I help?")
    logger.info("Running Research Mapping Agent for query: %s", query)
    orchestrator = ResearchMappingOrchestrator(tui=tui)
    evidence_map = orchestrator.run(
        UserQuery(query=query), search_modes=search_modes, community=community
    )
    logger.info(
        "Research Mapping complete — %d piece(s) of evidence mapped:",
        len(evidence_map.mapped_evidence),
    )
    tui.print_evidence_map(evidence_map)
    tui.prompt_file_export(
        writer=lambda f: export_mapped_evidence_to_ris(evidence_map.mapped_evidence, f),
        default_filename="results.ris",
        label="Export results to a RIS file?",
    )


def run() -> None:
    """Entry point for the ``research-mapper`` console script."""
    log_path = _configure_logging()
    try:
        main()
    except KeyboardInterrupt, EOFError:
        print("\nExiting...")
        sys.exit(130)
    except NoEvidenceToActOnError as exc:
        print(f"\n{exc}")
        sys.exit(1)
    except Exception:
        logger.exception("Unhandled error")
        if log_path:
            print(f"\nSee {log_path} for details.")
        raise
