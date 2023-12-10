import logging

import coloredlogs


def init_logging(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    coloredlogs.install(level="DEBUG", fmt="%(levelname)s %(message)s", logger=logger, isatty=True, reconfigure=True)
    logger.setLevel("WARNING")
    return logger
