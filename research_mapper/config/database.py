from research_mapper.db.session import db_manager


def init_database() -> None:
    """Initializes the database session manager from environment variables."""
    db_manager.init()


def close_database() -> None:
    """Closes the database session manager."""
    db_manager.close()
