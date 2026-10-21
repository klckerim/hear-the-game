import pytest

from htg.generate import Cal, generate


@pytest.fixture(scope="session")
def synth_dir(tmp_path_factory):
    """One synthetic match (fixed seed) shared by the engine tests."""
    return generate(42, Cal(), tmp_path_factory.mktemp("synth42"))
