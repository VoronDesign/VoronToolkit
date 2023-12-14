import itertools
import os
from pathlib import Path
from typing import Self

from loguru import logger

from voron_ci.utils.github_action_helper import GithubActionHelper
from voron_ci.utils.logging import init_logging


class FileHelper:
    @classmethod
    def find_files_by_name(cls: type[Self], directory: Path, filename: str, max_files: int = -1) -> list[Path]:
        files: list[Path] = list(directory.glob(f"**/{filename}"))
        if len(files) > max_files and max_files > 0:
            logger.warning("Found %d files, but max_files is %d. Truncating list of results.", len(files), max_files)
            files = files[:max_files]
        return files

    @classmethod
    def find_files_by_extension(cls: type[Self], directory: Path, extension: str, max_files: int = -1) -> list[Path]:
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


def sanitize_file_list() -> None:
    init_logging(verbose=True)
    logger.info("============ Sanitize File List ============")
    file_list: list[str] = os.environ.get("FILE_LIST_SANITIZE_INPUT", "").splitlines()
    output_file_list: list[str] = [input_file.replace("[", "\\[").replace("]", "\\]") for input_file in file_list]
    gh_helper: GithubActionHelper = GithubActionHelper()
    gh_helper.set_output_multiline(output={"FILE_LIST_SANITIZE_OUTPUT": output_file_list})
    gh_helper.write_outputs()
    logger.success("Sanitize file list success!")
