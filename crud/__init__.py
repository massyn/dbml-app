"""App factory: load the DBML schema, sync the database, register the CRUD views."""

from pathlib import Path

from flask import Flask

from config import Settings

from . import db
from .labels import label
from .markdown import render_markdown
from .model import Schema
from .schema import load_schema
from .sync import sync_schema

ROOT = Path(__file__).resolve().parent.parent


def get_schema(app: Flask) -> Schema:
    return app.extensions["dbml_schema"]


def create_app(settings: Settings) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    app.config.update(
        SECRET_KEY=settings.secret_key,
        DB_PATH=settings.db_path,
        PAGE_SIZE=settings.page_size,
    )

    schema = load_schema(settings.dbml_path)
    sync_schema(schema, settings.db_path)
    app.extensions["dbml_schema"] = schema

    from .views import bp

    app.register_blueprint(bp)
    app.teardown_appcontext(db.close_db)
    app.add_template_filter(render_markdown, "markdown")
    app.add_template_filter(label, "label")

    @app.context_processor
    def inject_schema() -> dict:
        return {
            "nav_groups": schema.nav_groups,
            "all_tables": schema.tables,
            "project": schema.project,
        }

    return app
