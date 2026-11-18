from __future__ import annotations

import asyncio
import logging

from .database import init_db
from .durable_runtime import run_worker


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    init_db()
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
