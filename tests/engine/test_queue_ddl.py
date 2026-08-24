import hashlib

from research_mapper.engine import queue

INSTALL_DIGEST = "dbd9f82903f66ae8"


def test_install_ddl_is_pinned():
    """If this fails, pgqueuer's schema moved: add a migration running upgrade_ddl()."""
    digest = hashlib.sha256(queue.install_ddl().encode()).hexdigest()[:16]
    assert digest == INSTALL_DIGEST


def test_upgrade_ddl_is_a_list_of_statements():
    statements = queue.upgrade_ddl()
    assert statements and all(isinstance(s, str) and s.strip() for s in statements)


def test_uninstall_drops_the_queue_tables():
    assert "DROP TABLE" in queue.uninstall_ddl()
