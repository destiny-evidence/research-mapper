from research_mapper.db.types import PydanticJSONB
from research_mapper.engine.views import Progress


def test_round_trips_a_model():
    column = PydanticJSONB(Progress)
    progress = Progress(done=3, total=10, note="screening")
    stored = column.process_bind_param(progress, None)

    assert stored == {"done": 3, "total": 10, "failed": 0, "note": "screening"}
    assert column.process_result_value(stored, None) == progress


def test_passes_none_through():
    column = PydanticJSONB(Progress)
    assert column.process_bind_param(None, None) is None
    assert column.process_result_value(None, None) is None


def test_is_cacheable():
    """Without this SQLAlchemy recompiles every statement touching the column."""
    assert PydanticJSONB.cache_ok is True
