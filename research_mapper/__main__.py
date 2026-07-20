import argparse
import logging
import sys

from research_mapper.config import configure_dspy, get_destiny_client, load_environment
from research_mapper.export import export_mapped_evidence_to_ris
from research_mapper.logs import ColourFormatter
from research_mapper.models import UserQuery
from research_mapper.orchestrator import ResearchMappingOrchestrator
from research_mapper.ui import TerminalUI

logger = logging.getLogger(__name__)


def initialise(env_file: str | None) -> None:
    """
    Initialises the destiny_sdk client and DSPy's LLM.
    :param env_file: optional explicit path to a .env file.
    :return: Nothing.
    """
    load_environment(env_file)
    get_destiny_client()
    logger.info("Destiny client ready")
    configure_dspy()


def main() -> None:
    """
    Main function for running the research-mapper CLI.
    :return: Nothing.
    """
    parser = argparse.ArgumentParser(description="Research Mapper CLI")
    parser.add_argument(
        "query", nargs="?", help="Research question (prompted if omitted)"
    )
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Enable debug logging"
    )
    parser.add_argument("--info", "-i", action="store_true", help="Enable info logging")
    parser.add_argument(
        "--env-file",
        help=(
            "Path to a .env file to load. Overrides ./.env and "
            "~/.config/research-mapper/.env; already-exported shell "
            "variables still take precedence."
        ),
    )
    args = parser.parse_args()

    handler = logging.StreamHandler()
    handler.setFormatter(
        ColourFormatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    logging.getLogger().setLevel(
        logging.DEBUG if args.debug else logging.INFO if args.info else logging.WARNING
    )
    logging.getLogger().addHandler(handler)
    logging.getLogger("dspy").setLevel(logging.WARNING)

    tui = TerminalUI()
    logger.info("Starting research-mapper")
    tui.print_welcome()
    tui.print_process_status(
        initialise,
        "Initialising...\n\nPlease authenticate your DESTINY credentials in your browser.\nA page should have opened automatically.",
        args.env_file,
        complete_message="[green]✓[/green] Initialisation Successful!",
    )

    query = args.query or tui.prompt_user("How can I help?")
    logger.info("Running Research Mapping Agent for query: %s", query)
    orchestrator = ResearchMappingOrchestrator(tui=tui)
    evidence_map = orchestrator.run(UserQuery(query=query))
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
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting...")
        sys.exit(130)


if __name__ == "__main__":
    run()
