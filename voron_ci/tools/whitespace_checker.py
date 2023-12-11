import os
import string
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Self

import configargparse

from voron_ci.constants import ReturnStatus
from voron_ci.utils.action_summary import ActionSummaryTable
from voron_ci.utils.github_action_helper import ActionResult, GithubActionHelper
from voron_ci.utils.logging import init_logging

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = init_logging(__name__)

ENV_VAR_PREFIX = "WHITESPACE_CHECKER"


class WhitespaceChecker:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.return_status: ReturnStatus = ReturnStatus.SUCCESS
        self.check_summary: list[list[str]] = []
        self.gh_helper: GithubActionHelper = GithubActionHelper(ignore_warnings=args.ignore_warnings)

        if args.verbose:
            logger.setLevel("INFO")

        if (args.input_dir and args.input_env_var) or (not args.input_dir and not args.input_env_var):
            logger.error(
                "Please provide either '--input_dir' (env: WHITESPACE_CHECKER_INPUT_DIR) or '--input_env_var' (env: WHITESPACE_CHECKER_ENV_VAR), not both!"
            )
            sys.exit(255)

        if args.input_dir:
            logger.info("Using input_dir '%s'", args.input_dir)
            input_path: Path = Path(Path.cwd(), args.input_dir)
            input_path_files: Iterator[Path] = Path(Path.cwd(), args.input_dir).glob("**/*")
            files = [x for x in input_path_files if x.is_file()]
            self.input_file_list: list[str] = [file_path.relative_to(input_path).as_posix() for file_path in files]
        else:
            logger.info("Using input_env_var '%s'", args.input_env_var)
            self.input_file_list = os.environ.get(args.input_env_var, "").splitlines()

    def _check_for_whitespace(self: Self) -> None:
        for input_file in self.input_file_list:
            if not input_file:
                continue
            logger.info("Checking file '%s' ...", input_file)
            for c in input_file:
                if c in string.whitespace:
                    logger.error("File '%s' contains whitespace!", input_file)
                    self.check_summary.append([input_file, "This file contains whitespace!"])
                    self.return_status = ReturnStatus.FAILURE
                    break

    def run(self: Self) -> None:
        logger.info("Starting whitespace check ...")

        self._check_for_whitespace()

        self.gh_helper.finalize_action(
            action_result=ActionResult(
                action_id="whitespace_check",
                action_name="Whitespace check",
                outcome=self.return_status,
                summary=ActionSummaryTable(
                    title="Whitespace check",
                    columns=["File/Folder", "Reason"],
                    rows=self.check_summary,
                ),
            )
        )


def main() -> None:
    parser: configargparse.ArgumentParser = configargparse.ArgumentParser(
        prog="VoronDesign VoronUsers whitespace checker",
        description="This tool is used to check changed files inside an env var for whitespace. The list is also prepared for sparse-checkout",
    )
    parser.add_argument(
        "-i",
        "--input_dir",
        required=False,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_INPUT_DIR",
        help="Directory containing files to be checked",
        default="",
    )
    parser.add_argument(
        "-e",
        "--input_env_var",
        required=False,
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
        env_var=f"{ENV_VAR_PREFIX}_VERBOSE",
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
