import pytest
from pydantic import BaseModel

from research_mapper.engine import registry
from research_mapper.engine.context import StepContext
from research_mapper.engine.registry import Step, register


class Params(BaseModel):
    pass


@pytest.fixture(autouse=True)
def clean_registry():
    """Keep tests from leaking step registrations into each other."""
    original = dict(registry.REGISTRY)
    yield
    registry.REGISTRY.clear()
    registry.REGISTRY.update(original)


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
    class Incomplete(Step[Params]):
        type = "incomplete"

    with pytest.raises(TypeError):
        Incomplete()


def test_importing_commands_populates_the_registry():
    """The worker and the API both rely on this import side effect."""
    import research_mapper.commands  # noqa: F401

    assert "enhance_sparse_query" in registry.known_types()
    assert issubclass(registry.get("enhance_sparse_query"), Step)
    assert StepContext
