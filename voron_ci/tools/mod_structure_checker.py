from enum import StrEnum
from pathlib import Path
from typing import Any, Self

import configargparse
import yaml

from voron_ci.constants import ReturnStatus
from voron_ci.utils.action_summary import ActionSummaryTable
from voron_ci.utils.file_helper import FileHelper
from voron_ci.utils.github_action_helper import ActionResult, GithubActionHelper
from voron_ci.utils.logging import init_logging

logger = init_logging(__name__)


class FileErrors(StrEnum):
    file_outside_mod_folder = "The file '{}' is located outside the expected folder structure of `printer_mods/user/mod`"
    mod_missing_metadata = "The mod '{}' does not have a metadata.yml file"
    file_from_metadata_missing = "The file '{}' is listed in the metadata.yml file but does not exist"


IGNORE_FILES = ["README.md", "mods.json"]
MOD_DEPTH = 2
ENV_VAR_PREFIX = "MOD_STRUCTURE_CHECKER"


class ModStructureChecker:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.input_dir: Path = Path(Path.cwd(), args.input_dir)
        self.gh_helper: GithubActionHelper = GithubActionHelper(
            output_path=None, do_gh_step_summary=args.github_step_summary, ignore_warnings=args.fail_on_error
        )
        self.return_status: ReturnStatus = ReturnStatus.SUCCESS
        self.check_summary: list[list[str]] = []

        if args.verbose:
            logger.setLevel("INFO")

    def _check_mods(self: Self) -> None:
        mod_folders = [folder for folder in self.input_dir.glob("*/*") if folder.is_dir() and folder.relative_to(self.input_dir).as_posix() not in IGNORE_FILES]

        logger.info("Performing mod file check")
        for mod_folder in mod_folders:
            logger.info("Checking folder '%s'", mod_folder.relative_to(self.input_dir).as_posix())
            if not Path(mod_folder, ".metadata.yml").exists():
                logger.warning("Mod '%s' is missing a metadata file!", mod_folder)
                self.check_summary.append([mod_folder.relative_to(self.input_dir).as_posix(), FileErrors.mod_missing_metadata.value.format(mod_folder)])
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
                        self.check_summary.append([mod_folder.relative_to(self.input_dir).as_posix(), FileErrors.file_from_metadata_missing.value.format(file)])
                        self.return_status = ReturnStatus.FAILURE

    def _check_shallow_files(self: Self) -> None:
        logger.info("Performing shallow file check")
        files_folders = FileHelper.get_shallow_folders(input_dir=self.input_dir, max_depth=MOD_DEPTH - 1, ignore=IGNORE_FILES)
        for file_folder in files_folders:
            logger.warning("File '%s' outside mod folder structure!", file_folder)
            self.check_summary.append([file_folder.relative_to(self.input_dir).as_posix(), FileErrors.file_outside_mod_folder.value.format(file_folder)])
            self.return_status = ReturnStatus.FAILURE

    def run(self: Self) -> None:
        logger.info("Starting files check in '%s'", str(self.input_dir))

        self._check_shallow_files()
        self._check_mods()

        self.gh_helper.postprocess_action(
            action_result=ActionResult(
                action_id="mod_structure_checker",
                action_name="Mod structure checker",
                outcome=self.return_status,
                summary=ActionSummaryTable(
                    title="Mod structure checker",
                    columns=["File/Folder", "Reason"],
                    rows=self.check_summary,
                ),
            )
        )


def main() -> None:
    parser: configargparse.ArgumentParser = configargparse.ArgumentParser(
        prog="VoronDesign VoronUsers mod checker",
        description="This tool is used to check whether all mods in VoronUsers are properly specified",
    )
    parser.add_argument(
        "-i",
        "--input_dir",
        required=True,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_INPUT_DIR",
        help="Directory containing STL files to be checked",
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
        help="Whether to return an error exit code if one of the STLs is faulty",
        default=False,
    )
    parser.add_argument(
        "-g",
        "--github_step_summary",
        required=False,
        action="store_true",
        env_var=f"{ENV_VAR_PREFIX}_GITHUB_STEP_SUMMARY",
        help="Whether to output a step summary when running inside a github action",
        default=False,
    )
    args: configargparse.Namespace = parser.parse_args()
    ModStructureChecker(args=args).run()


if __name__ == "__main__":
    main()
