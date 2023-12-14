import sys

import loguru


def init_logging(*, verbose: bool) -> None:
    loguru.logger.remove()
    loguru.logger.level("INFO", color="<blue>", icon="📢")
    loguru.logger.level("SUCCESS", color="<green>", icon="✅")
    loguru.logger.level("WARNING", color="<yellow>", icon="⚠️")
    loguru.logger.level("ERROR", color="<red>", icon="❌")
    loguru.logger.level("CRITICAL", color="<red><bold>", icon="💀")
    loguru.logger.add(sys.stderr, level="INFO" if verbose else "WARNING", colorize=True, format="<level> {level.icon} </level>- {message}")
