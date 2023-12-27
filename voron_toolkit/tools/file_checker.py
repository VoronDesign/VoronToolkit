import string
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Self

import configargparse
from loguru import logger

from voron_toolkit.constants import ExtendedResultEnum, ItemResult, ToolIdentifierEnum, ToolResult, ToolSummaryTable
from voron_toolkit.utils.github_action_helper import GithubActionHelper
from voron_toolkit.utils.logging import init_logging

if TYPE_CHECKING:
    from collections.abc import Iterator

ENV_VAR_PREFIX = "FILE_CHECKER"


class WhitespaceChecker:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.input_dir = args.input_dir
        self.check_license = args.check_license
        self.check_file_size = args.check_file_size_mb
        self.return_status: ExtendedResultEnum = ExtendedResultEnum.SUCCESS
        self.input_file_list: list[Path] = []
        self.result_items: defaultdict[ExtendedResultEnum, list[ItemResult]] = defaultdict(list)

        self.gh_helper: GithubActionHelper = GithubActionHelper()
        self.ignore_warnings = args.ignore_warnings

        init_logging(verbose=args.verbose)

    def _check_for_whitespace(self: Self) -> None:
        for input_file in self.input_file_list:
            relative_file_path: str = input_file.relative_to(self.input_dir).as_posix()
            result_ok: bool = all(c not in string.whitespace for c in relative_file_path)

            if result_ok:
                logger.success("File '{}' OK!", input_file)
                self.result_items[ExtendedResultEnum.SUCCESS].append(ItemResult(item=relative_file_path, extra_info=[""]))
            else:
                logger.error("File '{}' contains whitespace!", relative_file_path)
                self.result_items[ExtendedResultEnum.FAILURE].append(ItemResult(item=relative_file_path, extra_info=["This file contains whitespace!"]))
                self.return_status = ExtendedResultEnum.FAILURE

    def _check_for_license_files(self: Self) -> None:
        for input_file in self.input_file_list:
            relative_file_path: str = input_file.relative_to(self.input_dir).as_posix()
            if "license" in input_file.as_posix().lower():
                logger.warning("File '{}' looks like a license file!", relative_file_path)
                self.result_items[ExtendedResultEnum.WARNING].append(ItemResult(item=relative_file_path, extra_info=["This file looks like a license file!"]))
                self.return_status = ExtendedResultEnum.WARNING

    def _check_file_size(self: Self) -> None:
        for input_file in self.input_file_list:
            relative_file_path: str = input_file.relative_to(self.input_dir).as_posix()
            if input_file.stat().st_size > self.check_file_size * 1024 * 1024:
                logger.error("File '{}' is larger than {} MB!", relative_file_path, self.check_file_size)
                self.result_items[ExtendedResultEnum.WARNING].append(
                    ItemResult(item=relative_file_path, extra_info=[f"This file is larger than {self.check_file_size} MB!"])
                )
                self.return_status = ExtendedResultEnum.WARNING

    def run(self: Self) -> None:
        logger.info("============ File Checker ============")
        logger.info("Using input_dir '{}'", self.input_dir)
        input_path_files: Iterator[Path] = Path(Path.cwd(), self.input_dir).glob("**/*")
        self.input_file_list = [x for x in input_path_files if x.is_file()]

        self._check_for_whitespace()
        if self.check_license:
            self._check_for_license_files()
        if self.check_file_size > 0:
            self._check_file_size()

        self.gh_helper.finalize_action(
            action_result=ToolResult(
                tool_id=ToolIdentifierEnum.FILE_CHECK.tool_id,
                tool_name=ToolIdentifierEnum.FILE_CHECK.tool_name,
                extended_result=self.return_status,
                tool_ignore_warnings=self.ignore_warnings,
                tool_result_items=ToolSummaryTable(
                    extra_columns=["Reason"],
                    items=self.result_items,
                ),
            )
        )


def main() -> None:
    parser: configargparse.ArgumentParser = configargparse.ArgumentParser(
        prog="VoronDesign VoronUsers file checker",
        description="This tool is used to check files in a directory. The list is also prepared for sparse-checkout",
    )
    parser.add_argument(
        "-i",
        "--input_dir",
        action="store",
        type=str,
        env_var="VORON_TOOLKIT_INPUT_DIR",
        help="Directory containing files to be checked",
        default="",
    )
    parser.add_argument(
        "-l",
        "--check_license",
        required=False,
        action="store_true",
        env_var=f"{ENV_VAR_PREFIX}_CHECK_LICENSE",
        help="Whether to check for license files",
        default=False,
    )
    parser.add_argument(
        "-s",
        "--check_file_size_mb",
        required=False,
        action="store",
        type=int,
        env_var=f"{ENV_VAR_PREFIX}_CHECK_FILE_SIZE_MB",
        help="Whether to check if any file size exceeds the given value in megabytes",
        default=0,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        required=False,
        action="store_true",
        env_var="VORON_TOOLKIT_VERBOSE",
        help="Print debug output to stdout",
        default=False,
    )
    parser.add_argument(
        "-f",
        "--ignore_warnings",
        required=False,
        action="store_true",
        env_var=f"{ENV_VAR_PREFIX}_IGNORE_WARNINGS",
        help="Whether to ignore warnings and return a success exit code",
        default=False,
    )
    args: configargparse.Namespace = parser.parse_args()
    WhitespaceChecker(args=args).run()


if __name__ == "__main__":
    main()
