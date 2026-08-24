import pytest
from pydantic import BaseModel

from research_mapper import workflows
from research_mapper.engine import registry
from research_mapper.engine.context import StepContext
from research_mapper.engine.registry import Step, register


class Params(BaseModel):
    pass


@pytest.fixture(autouse=True)
def clean_registry():
    """Drop only what this test registered; imports are cached and never re-run."""
    before = set(registry.REGISTRY)
    yield
    for operation_type in set(registry.REGISTRY) - before:
        del registry.REGISTRY[operation_type]


def build(**namespace) -> type[Step]:
    return type(
        "Anonymous", (Step,), {"Params": Params, "run": lambda s, c, p: {}, **namespace}
    )


def test_register_and_get():
    step = register(build(type="thing"))
    assert registry.get("thing") is step
    assert "thing" in registry.known_types()


@pytest.mark.parametrize("namespace", [{}, {"type": ""}, {"type": 3}])
def test_register_rejects_a_bad_type(namespace):
    with pytest.raises(TypeError):
        register(build(**namespace))


def test_register_rejects_a_duplicate():
    register(build(type="thing"))
    with pytest.raises(TypeError):
        register(build(type="thing"))


def test_get_unknown_type_raises():
    with pytest.raises(LookupError):
        registry.get("nope")


def test_step_cannot_be_instantiated_without_run():
    class Incomplete(Step[Params, StepContext]):
        type = "incomplete"

    with pytest.raises(TypeError):
        Incomplete()


def test_load_populates_the_registry():
    """The worker and the API both call this instead of a magic import."""
    workflows.load()

    assert "enhance_sparse_query" in registry.known_types()
    assert issubclass(registry.get("enhance_sparse_query"), Step)
    assert StepContext


def test_registering_the_same_step_twice_is_a_no_op():
    """load() is called by both entry points and must tolerate being repeated."""
    step = build(type="thing")
    assert register(step) is register(step)
