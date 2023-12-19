import os
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

ENV_VAR_PREFIX = "WHITESPACE_CHECKER"


class WhitespaceChecker:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.input_dir = args.input_dir
        self.input_env_var = args.input_env_var

        self.return_status: ExtendedResultEnum = ExtendedResultEnum.SUCCESS
        self.input_file_list: list[str] = []
        self.result_items: defaultdict[ExtendedResultEnum, list[ItemResult]] = defaultdict(list)

        self.gh_helper: GithubActionHelper = GithubActionHelper()
        self.ignore_warnings = args.ignore_warnings

        init_logging(verbose=args.verbose)

    def _check_for_whitespace(self: Self) -> None:
        for input_file in self.input_file_list:
            if not input_file:
                continue
            result_ok: bool = all(c not in string.whitespace for c in input_file)

            if result_ok:
                logger.success("File '{}' OK!", input_file)
                self.result_items[ExtendedResultEnum.SUCCESS].append(ItemResult(item=input_file, extra_info=[""]))
            else:
                logger.error("File '{}' contains whitespace!", input_file)
                self.result_items[ExtendedResultEnum.FAILURE].append(ItemResult(item=input_file, extra_info=["This folder/file contains whitespace!"]))
                self.return_status = ExtendedResultEnum.FAILURE

    def run(self: Self) -> None:
        logger.info("============ Whitespace Checker ============")
        if self.input_dir:
            logger.info("Using input_dir '{}'", self.input_dir)
            input_path: Path = Path(Path.cwd(), self.input_dir)
            input_path_files: Iterator[Path] = Path(Path.cwd(), self.input_dir).glob("**/*")
            files = [x for x in input_path_files if x.is_file()]
            self.input_file_list = [file_path.relative_to(input_path).as_posix() for file_path in files]
        else:
            logger.info("Using input_env_var '{}'", self.input_env_var)
            self.input_file_list = os.environ.get(self.input_env_var, "").splitlines()

        self._check_for_whitespace()

        self.gh_helper.finalize_action(
            action_result=ToolResult(
                tool_id=ToolIdentifierEnum.WHITESPACE_CHECK.tool_id,
                tool_name=ToolIdentifierEnum.WHITESPACE_CHECK.tool_name,
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
        prog="VoronDesign VoronUsers whitespace checker",
        description="This tool is used to check changed files inside an env var for whitespace. The list is also prepared for sparse-checkout",
    )
    input_grp = parser.add_mutually_exclusive_group(required=True)
    input_grp.add_argument(
        "-i",
        "--input_dir",
        action="store",
        type=str,
        env_var="VORON_TOOLKIT_INPUT_DIR",
        help="Directory containing files to be checked",
        default="",
    )
    input_grp.add_argument(
        "-e",
        "--input_env_var",
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_INPUT_ENV_VAR",
        help="Environment variable name containing a newline separated list of files to be checked",
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
