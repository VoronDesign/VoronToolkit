import argparse
import sys
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

import yaml

from voron_ci.contants import EXTENDED_OUTCOME, ReturnStatus
from voron_ci.utils.file_helper import FileHelper
from voron_ci.utils.github_action_helper import GithubActionHelper
from voron_ci.utils.logging import init_logging

logger = init_logging(__name__)


STEP_SUMMARY_PREAMBLE = """
## Folder check

"""


class FileErrors(StrEnum):
    file_outside_mod_folder = "The file '{}' is located outside the expected folder structure of `printer_mods/user/mod`"
    mod_missing_metadata = "The mod '{}' does not have a metadata.yml file"
    file_from_metadata_missing = "The file '{}' is listed in the metadata.yml file but does not exist"


IGNORE_FILES = ["README.md", "mods.json"]
MOD_DEPTH = 2


class FileChecker:
    def __init__(self: Self, args: argparse.Namespace) -> None:
        self.input_dir: Path = Path(Path.cwd(), args.input_dir)
        self.verbosity: bool = args.verbose
        self.fail_on_error: bool = args.fail_on_error
        self.print_gh_step_summary: bool = args.github_step_summary
        self.return_status: ReturnStatus = ReturnStatus.SUCCESS
        self.check_summary: list[tuple[str, ...]] = []

        self.errors: dict[Path, str] = {}

    def _check_mods(self: Self, input_dir: Path) -> None:
        mod_folders = [folder for folder in input_dir.glob("*/*") if folder.is_dir() and folder.relative_to(input_dir).as_posix() not in IGNORE_FILES]

        logger.info("Performing mod file check")
        for mod_folder in mod_folders:

            logger.info("Checking folder '%s'", mod_folder.relative_to(self.input_dir).as_posix())
            if not Path(mod_folder, ".metadata.yml").exists():
                logger.warning("Mod '%s' is missing a metadata file!", mod_folder)
                self.errors[mod_folder] = FileErrors.mod_missing_metadata.value.format(mod_folder)
                self.return_status = ReturnStatus.FAILURE
                continue

            metadata: dict[str, Any] = yaml.safe_load(Path(mod_folder, ".metadata.yml").read_text())

            for subelement in ["cad", "images"]:
                files = metadata[subelement]
                if not (isinstance(files, list) and len(files) > 0):
                    continue
                for file in files:
                    if not Path(mod_folder, file).exists():
                        logger.warning("File '%s' is missing in mod folder '%s'!", file, mod_folder)
                        self.errors[Path(mod_folder, file)] = FileErrors.file_from_metadata_missing.value.format(file)
                        self.return_status = ReturnStatus.FAILURE

    def _check_shallow_files(self: Self, input_dir: Path) -> None:
        logger.info("Performing shallow file check")
        files_folders = FileHelper.get_shallow_folders(input_dir=input_dir, max_depth=MOD_DEPTH - 1, ignore=IGNORE_FILES)
        for file_folder in files_folders:
            logger.warning("File '%s' outside mod folder structure!", file_folder)
            self.errors[file_folder] = FileErrors.file_outside_mod_folder.value.format(file_folder)
            self.return_status = ReturnStatus.FAILURE

    def run(self: Self) -> None:
        if self.verbosity:
            logger.setLevel("INFO")

        logger.info("Starting files check in '%s'", str(self.input_dir))

        self._check_shallow_files(input_dir=self.input_dir)
        self._check_mods(input_dir=self.input_dir)

        if self.print_gh_step_summary:
            self.check_summary = [(path.relative_to(self.input_dir).as_posix(), reason) for path, reason in self.errors.items()]
            GithubActionHelper.print_summary_table(
                preamble=STEP_SUMMARY_PREAMBLE,
                columns=[
                    "File/Folder",
                    "Reason",
                ],
                rows=self.check_summary,
            )

        GithubActionHelper.write_output(output={"extended-outcome": EXTENDED_OUTCOME[self.return_status]})

        if self.return_status > ReturnStatus.SUCCESS and self.fail_on_error:
            logger.error("Error detected during file/folder checking!")
            sys.exit(255)


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="VoronDesign VoronUsers mod checker",
        description="This tool is used to check whether all mods in VoronUsers are properly specified",
    )
    parser.add_argument(
        "-i",
        "--input_dir",
        required=True,
        action="store",
        type=str,
        help="Directory containing STL files to be checked",
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
        help="Whether to return an error exit code if one of the STLs is faulty",
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
    args: argparse.Namespace = parser.parse_args()
    FileChecker(args=args).run()


if __name__ == "__main__":
    main()
