"""Entry point: python app.py --dbml schema.dbml --db data.db"""

import argparse
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from config import ConfigError, resolve_settings
from crud import create_app
from crud.schema import SchemaError
from crud.sync import SchemaDriftError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="CRUD app generated from a DBML file")
    parser.add_argument("--dbml", help="DBML schema file (or DBML= in .env)")
    parser.add_argument("--db", help="SQLite database file (or DB= in .env)")
    args = parser.parse_args()

    try:
        settings = resolve_settings(args.dbml, args.db)
    except ConfigError as exc:
        parser.error(str(exc))

    try:
        app = create_app(settings)
    except (SchemaError, SchemaDriftError) as exc:
        logger.error("%s", exc)
        return 1

    app.run(host=settings.host, port=settings.port, debug=settings.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
