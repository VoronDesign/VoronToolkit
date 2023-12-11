import itertools
from pathlib import Path
from typing import Self

from loguru import logger


class FileHelper:
    @classmethod
    def find_files(cls: type[Self], directory: Path, extension: str, max_files: int = -1) -> list[Path]:
        files: list[Path] = list(
            itertools.chain(
                directory.glob(f"**/*.{extension.lower()}"),
                directory.glob(f"**/*.{extension.upper()}"),
            ),
        )
        if len(files) > max_files and max_files > 0:
            logger.warning("Found %d files, but max_files is %d. Truncating list of results.", len(files), max_files)
            files = files[:max_files]
        return files

    @classmethod
    def get_shallow_folders(cls: type[Self], input_dir: Path, max_depth: int, ignore: list[str]) -> list[Path]:
        return [
            element
            for element in input_dir.glob("*/*")
            if len(element.relative_to(input_dir).parts) <= max_depth and element.relative_to(input_dir).as_posix() not in ignore
        ]

    @classmethod
    def get_all_folders(cls: type[Self], _: Path) -> list[Path]:
        return []
