import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir():
    return FIXTURES_DIR


def load_fixture(provider: str, name: str) -> dict:
    path = FIXTURES_DIR / provider / f"{name}.json"
    return json.loads(path.read_text())
