from __future__ import annotations

import asyncio
import logging
import os

os.environ.setdefault('LANGGRAPH_STRICT_MSGPACK', 'true')

from .database import check_db_connection
from .durable_runtime import run_worker


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    check_db_connection()
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
