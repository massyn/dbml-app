import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import resolve_settings
from crud import create_app

# The tests use their own fixed sample, so editing the project's test.dbml never breaks them
TEST_DBML = Path(__file__).resolve().parent / "sample.dbml"


@pytest.fixture
def make_app(tmp_path, monkeypatch):
    monkeypatch.delenv("DBML", raising=False)
    monkeypatch.delenv("DB", raising=False)

    def factory(dbml_text: str | None = None, db_name: str = "test.db"):
        dbml = TEST_DBML
        if dbml_text is not None:
            dbml = tmp_path / "schema.dbml"
            dbml.write_text(dbml_text, encoding="utf-8")
        app = create_app(resolve_settings(str(dbml), str(tmp_path / db_name)))
        app.config["TESTING"] = True
        return app

    return factory


@pytest.fixture
def client(make_app):
    return make_app().test_client()
