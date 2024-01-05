import os
import sys
from pathlib import Path
from typing import Self

import configargparse
from loguru import logger

from voron_toolkit.utils.github_action_helper import GithubActionHelper
from voron_toolkit.utils.logging import init_logging

ENV_VAR_PREFIX = "SPARSE_CHECKOUT_HELPER"

MOD_MINIMUM_PARTS = 3


class SparseCheckoutHelper:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.mod_subfolder: Path = Path(args.mod_subfolder)
        self.input_file_list: str = args.input_file_list
        self.gh_helper: GithubActionHelper = GithubActionHelper()

        init_logging(verbose=args.verbose)

    def run(self: Self) -> None:
        logger.info("============ Sparse Checkout Helper ============")
        if "SPARSE_CHECKOUT_HELPER_INPUT" not in os.environ:
            logger.warning("Input environment variable 'SPARSE_CHECKOUT_HELPER_INPUT' not found in environment")
            sys.exit(255)
        file_list: list[str] = os.environ.get("SPARSE_CHECKOUT_HELPER_INPUT", "").splitlines()
        if not file_list:
            logger.warning("Input file list from env var 'SPARSE_CHECKOUT_HELPER_INPUT' is empty")
            sys.exit(255)

        sparse_checkout_patterns: set[str] = set()

        for pr_file in file_list:
            file_path = Path(pr_file)
            try:
                file_path_relative: Path = file_path.relative_to(self.mod_subfolder)
            except ValueError:
                logger.warning("File '{}' is not relative to mod subdirectory directory '{}'. Skipping.", file_path, self.mod_subfolder)
                continue
            # The expected layout is self.mod_subfolder/<author>/<mod_name>/.. so if the file path has less than 3 parts, it's too far up in the hierarchy
            if len(file_path_relative.parts) < MOD_MINIMUM_PARTS:
                logger.warning("Folder depth of file '{}' is too shallow. Skipping.", file_path_relative)
                continue
            pattern: str = Path(self.mod_subfolder, *file_path_relative.parts[:2], "**", "*").as_posix().replace("[", "\\[").replace("]", "\\]")
            sparse_checkout_patterns.add(pattern)
            logger.success("Added pattern '{}' to sparse_checkout_patterns", pattern)

        self.gh_helper.set_output_multiline(output={"SPARSE_CHECKOUT_HELPER_OUTPUT": list(sparse_checkout_patterns)})


def main() -> None:
    parser: configargparse.ArgumentParser = configargparse.ArgumentParser(
        prog="VoronDesign Sparse Checkout Helper",
        description="""
This tool takes in a list of files and folders and outputs a list of
files and folders that can be used as input for a sparse checkout action.
        """,
    )
    parser.add_argument(
        "-i",
        "--mod_subfolder",
        required=True,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_MOD_SUBFOLDER",
        help="Relative directory where mods are stored (and where most file changes should be made)",
    )
    parser.add_argument(
        "-e",
        "--input_file_list",
        required=True,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_INPUT",
        help="Environment variable that contains the input file list, separated by newlines",
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
    args: configargparse.Namespace = parser.parse_args()
    SparseCheckoutHelper(args=args).run()


if __name__ == "__main__":
    main()
