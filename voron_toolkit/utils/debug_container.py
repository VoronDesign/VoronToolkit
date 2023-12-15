import os

from loguru import logger

from voron_toolkit.utils.logging import init_logging

init_logging(verbose=True)


def print_container_info() -> None:
    logger.info("## Debugging environment variables:\n")
    logger.info("\tGITHUB_OUTPUT=%s", os.environ.get("GITHUB_OUTPUT", ""))
    logger.info("\tGITHUB_STEP_SUMMARY=%s", os.environ.get("GITHUB_STEP_SUMMARY", ""))
    logger.info("\tGITHUB_REF=%s", os.environ.get("GITHUB_REF", ""))
    logger.info("\tGITHUB_REPOSITORY=%s", os.environ.get("GITHUB_REPOSITORY", ""))
    logger.info("\tGITHUB_TOKEN=%s", os.environ.get("GITHUB_TOKEN", ""))
