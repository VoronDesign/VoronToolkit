import os
import string
import sys
from typing import Self

import configargparse

from voron_ci.contants import EXTENDED_OUTCOME, ReturnStatus
from voron_ci.utils.github_action_helper import GithubActionHelper
from voron_ci.utils.logging import init_logging

logger = init_logging(__name__)

STEP_SUMMARY_PREAMBLE = """
## Whitespace check errors

"""


class WhitespaceChecker:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.input_env_var: str = args.input_env_var
        self.verbosity: bool = args.verbose
        self.fail_on_error: bool = args.fail_on_error
        self.print_gh_step_summary: bool = args.github_step_summary
        self.return_status: ReturnStatus = ReturnStatus.SUCCESS
        self.check_summary: list[tuple[str, ...]] = []
        self.error_count: int = 0

    def _check_for_whitespace(self: Self) -> None:
        input_file_list = os.environ.get(self.input_env_var, "").splitlines()

        for input_file in input_file_list:
            if not input_file:
                continue
            logger.info("Checking file '%s' for whitespace!", input_file)
            for c in input_file:
                if c in string.whitespace:
                    logger.error("File '%s' contains whitespace!", input_file)
                    self.check_summary.append((input_file, "This file contains whitespace!"))
                    self.error_count += 1
                    self.return_status = ReturnStatus.FAILURE
                    break

    def _write_sanitized_output(self: Self) -> None:
        input_file_list = os.environ.get(self.input_env_var, "").splitlines()

        output_file_list: list[str] = [input_file.replace("[", "\\[").replace("]", "\\]") for input_file in input_file_list]

        GithubActionHelper.write_output_multiline(output={"FILE_LIST_SANITIZED": output_file_list})

    def run(self: Self) -> None:
        if self.verbosity:
            logger.setLevel("INFO")

        logger.info("Starting files check from env var '%s'", self.input_env_var)

        self._check_for_whitespace()
        self._write_sanitized_output()

        if self.print_gh_step_summary:
            with GithubActionHelper.expandable_section(
                title=f"Whitespace checks (errors: {self.error_count})", default_open=self.return_status != ReturnStatus.SUCCESS
            ):
                GithubActionHelper.print_summary_table(
                    columns=[
                        "File/Folder",
                        "Reason",
                    ],
                    rows=self.check_summary,
                )

        GithubActionHelper.write_output(output={"extended-outcome": EXTENDED_OUTCOME[self.return_status]})

        if self.return_status > ReturnStatus.SUCCESS and self.fail_on_error:
            logger.error("Error detected during whitespace checking!")
            sys.exit(255)


def main() -> None:
    parser: configargparse.ArgumentParser = configargparse.ArgumentParser(
        prog="VoronDesign VoronUsers whitespace checker",
        description="This tool is used to check changed files inside an env var for whitespace. The list is also prepared for sparse-checkout",
    )
    parser.add_argument(
        "-i",
        "--input_env_var",
        required=True,
        action="store",
        type=str,
        help="Environment variable name containing a newline separated list of files to be checked",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        required=False,
        action="store_true",
        help="Print debug output to stdout",
        default=False,
    )
    parser.add_argument(
        "-f",
        "--fail_on_error",
        required=False,
        action="store_true",
        help="Whether to return an error exit code if one of the files contains whitespace",
        default=False,
    )
    parser.add_argument(
        "-g",
        "--github_step_summary",
        required=False,
        action="store_true",
        help="Whether to output a step summary when running inside a github action",
        default=False,
    )
    args: configargparse.Namespace = parser.parse_args()
    WhitespaceChecker(args=args).run()


if __name__ == "__main__":
    main()
