import argparse
import logging

from research_mapper.config import configure_dspy
from research_mapper.logs import ColourFormatter
from research_mapper.models import UserQuery
from research_mapper.modules import SearchAgent
from research_mapper.ui import print_evidence
from research_mapper.utils import get_destiny_client

logger = logging.getLogger(__name__)


# TODO add unit tests of core parts, e.g. the query generator, tools, etc
def main():
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

    logger.info("Starting research-mapper")
    get_destiny_client()
    logger.info("Destiny client ready")
    configure_dspy()

    print()
    query = args.query or input("❯ ")
    print()
    logger.info("Running SearchAgent for query: %s", query)
    search_agent = SearchAgent()
    evidence = search_agent(UserQuery(query=query)).evidence
    logger.info("SearchAgent complete — %d sources found", len(evidence))
    print_evidence(evidence)


if __name__ == "__main__":
    main()
