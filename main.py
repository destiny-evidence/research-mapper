import argparse
import logging

from research_mapper.config import configure_dspy, get_destiny_client
from research_mapper.logs import ColourFormatter
from research_mapper.models import UserQuery
from research_mapper.modules.workflow_agent import WorkflowAgent
from research_mapper.ui import TerminalUI

logger = logging.getLogger(__name__)


def initialise() -> None:
    """
    Initialises the destiny_sdk client and DSPy's LLM.
    :return: Nothing.
    """
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
        complete_message="[green]✓[/green] Initialisation Successful!",
    )

    query = args.query or tui.prompt_user("How can I help?")
    logger.info("Running Research Mapping Agent for query: %s", query)
    mapping_agent = WorkflowAgent(tui=tui)
    mapping_agent(UserQuery(query=query))
    # logger.info("Research Mapping complete — %d screened sources found:", len(evidence))
    # tui.print_evidence(evidence_map)
    # tui.prompt_file_export(
    # writer=lambda f: export_to_ris(evidence, f),
    # default_filename="results.ris",
    # label="Export results to a RIS file?",
    # )


if __name__ == "__main__":
    main()
