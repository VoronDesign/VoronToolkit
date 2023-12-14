import json
from enum import StrEnum
from importlib.resources import files
from pathlib import Path
from typing import Any, Self

import configargparse
import jsonschema
import yaml
from loguru import logger

from voron_toolkit import resources
from voron_toolkit.constants import StepIdentifier, StepResult
from voron_toolkit.utils.action_summary import ActionSummaryTable
from voron_toolkit.utils.file_helper import FileHelper
from voron_toolkit.utils.github_action_helper import ActionResult, GithubActionHelper
from voron_toolkit.utils.logging import init_logging


class FileErrors(StrEnum):
    file_from_metadata_missing = "The file '{}' is listed in the metadata.yml file but does not exist"
    file_outside_mod_folder = "The file '{}' is located outside the expected folder structure of `printer_mods/user/mod`"
    mod_has_no_cad_files = "The mod '{}' does not have any CAD files listed in the metadata.yml file"
    mod_missing_metadata = "The mod '{}' does not have a metadata.yml file"
    mod_has_invalid_metadata_file = "The metadata file of mod '{}' is invalid!"


IGNORE_FILES = ["README.md", "mods.json"]
MOD_DEPTH = 2
ENV_VAR_PREFIX = "MOD_STRUCTURE_CHECKER"


class ModStructureChecker:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.input_dir: Path = Path(Path.cwd(), args.input_dir)
        self.gh_helper: GithubActionHelper = GithubActionHelper(ignore_warnings=args.ignore_warnings)
        self.return_status: StepResult = StepResult.SUCCESS
        self.check_summary: list[list[str]] = []

        init_logging(verbose=args.verbose)

    def _check_mods(self: Self) -> None:
        mod_folders = [folder for folder in self.input_dir.glob("*/*") if folder.is_dir() and folder.relative_to(self.input_dir).as_posix() not in IGNORE_FILES]
        logger.info("Performing mod structure and metadata check")
        result: StepResult = StepResult.SUCCESS
        schema = json.loads(files(resources).joinpath("voronusers_metadata_schema.json").read_text())
        for mod_folder in mod_folders:
            if not Path(mod_folder, ".metadata.yml").exists():
                logger.error("Mod '{}' is missing a metadata file!", mod_folder)
                self.check_summary.append(
                    [mod_folder.relative_to(self.input_dir).as_posix(), StepResult.FAILURE.result_str, FileErrors.mod_missing_metadata.value.format(mod_folder)]
                )
                result = StepResult.FAILURE
                continue

            try:
                metadata: dict[str, Any] = yaml.safe_load(Path(mod_folder, ".metadata.yml").read_text())
                jsonschema.validate(instance=metadata, schema=schema)
            except (yaml.YAMLError, yaml.scanner.ScannerError) as e:
                logger.error("YAML error in metadata file of mod '{}': {}", mod_folder, e)
                self.check_summary.append(
                    [
                        Path(mod_folder, ".metadata.yml").relative_to(self.input_dir).as_posix(),
                        StepResult.FAILURE.result_str,
                        FileErrors.mod_has_invalid_metadata_file.value.format(mod_folder),
                    ]
                )
                result = StepResult.FAILURE
                continue
            except jsonschema.ValidationError as e:
                logger.error("Validation error in metadata file of mod '{}': {}", mod_folder, e.message)
                self.check_summary.append(
                    [
                        Path(mod_folder, ".metadata.yml").relative_to(self.input_dir).as_posix(),
                        StepResult.FAILURE.result_str,
                        FileErrors.mod_has_invalid_metadata_file.value.format(mod_folder),
                    ]
                )
                result = StepResult.FAILURE
                continue

            if "cad" in metadata and not metadata["cad"]:
                logger.warning("Mod '{}' has no CAD files!", mod_folder)
                self.check_summary.append(
                    [mod_folder.relative_to(self.input_dir).as_posix(), StepResult.FAILURE.result_str, FileErrors.mod_has_no_cad_files.value.format(mod_folder)]
                )
                result = StepResult.FAILURE

            for subelement in ["cad", "images"]:
                metadata_files = metadata[subelement]
                if not (isinstance(metadata_files, list) and len(metadata_files) > 0):
                    continue
                for file in metadata_files:
                    if not Path(mod_folder, file).exists():
                        logger.error("File '{}' is missing in mod folder '{}'!", file, mod_folder)
                        self.check_summary.append(
                            [
                                mod_folder.relative_to(self.input_dir).as_posix(),
                                StepResult.FAILURE.result_str,
                                FileErrors.file_from_metadata_missing.value.format(file),
                            ]
                        )
                        result = StepResult.FAILURE
            self.check_summary.append([mod_folder.relative_to(self.input_dir).as_posix(), StepResult.SUCCESS.result_str, ""])
            logger.success("Folder '{}' OK!", mod_folder.relative_to(self.input_dir).as_posix())
        self.return_status = result

    def _check_shallow_files(self: Self) -> None:
        logger.info("Performing shallow file check")
        files_folders = FileHelper.get_shallow_folders(input_dir=self.input_dir, max_depth=MOD_DEPTH - 1, ignore=IGNORE_FILES)
        result: StepResult = StepResult.SUCCESS
        for file_folder in files_folders:
            logger.error("File '{}' outside mod folder structure!", file_folder)
            self.check_summary.append([file_folder.relative_to(self.input_dir).as_posix(), FileErrors.file_outside_mod_folder.value.format(file_folder)])
            result = StepResult.FAILURE
        if result == StepResult.SUCCESS:
            logger.success("Shallow file check OK!")
        self.return_status = result

    def run(self: Self) -> None:
        logger.info("============ Mod Structure Checker ============")
        logger.info("Starting files check in '{}'", str(self.input_dir))

        self._check_shallow_files()
        self._check_mods()

        self.gh_helper.finalize_action(
            action_result=ActionResult(
                action_id=StepIdentifier.MOD_STRUCTURE_CHECK.step_id,
                action_name=StepIdentifier.MOD_STRUCTURE_CHECK.step_name,
                outcome=self.return_status,
                summary=ActionSummaryTable(
                    columns=["File/Folder", "Result", "Reason"],
                    rows=self.check_summary,
                ),
            )
        )


def main() -> None:
    parser: configargparse.ArgumentParser = configargparse.ArgumentParser(
        prog="VoronDesign Mod Structure Checker",
        description="This tool is used to check whether all mods in VoronUsers are properly specified",
    )
    parser.add_argument(
        "-i",
        "--input_dir",
        required=True,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_INPUT_DIR",
        help="Directory containing Mods to be checked",
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
        help="Whether to return an error exit code if bad files or badly structured mods are found",
        default=False,
    )
    args: configargparse.Namespace = parser.parse_args()
    ModStructureChecker(args=args).run()


if __name__ == "__main__":
    main()
