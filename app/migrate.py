"""One-shot database schema bootstrap for Docker Compose and local operations."""

import logging

from .database import init_db


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.info("Starting Pinky Bread database schema bootstrap")
    init_db()
    logging.info("Pinky Bread database schema bootstrap completed")


if __name__ == "__main__":
    main()
