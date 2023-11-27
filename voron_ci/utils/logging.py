import logging


def init_logging(name: str) -> logging.Logger:
    logging.basicConfig(format="[%(asctime)s] %(message)s")
    return logging.getLogger(name)
