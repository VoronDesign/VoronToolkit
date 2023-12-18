import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Self

import configargparse
from admesh import Stl
from loguru import logger

from voron_toolkit.constants import ExtendedResultEnum, ItemResult, ToolIdentifierEnum, ToolResult, ToolSummaryTable
from voron_toolkit.utils.file_helper import FileHelper
from voron_toolkit.utils.github_action_helper import GithubActionHelper
from voron_toolkit.utils.logging import init_logging

ENV_VAR_PREFIX = "CORRUPTION_CHECKER"


class STLCorruptionChecker:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.input_dir: Path = Path(Path.cwd(), args.input_dir)
        self.return_status: ExtendedResultEnum = ExtendedResultEnum.SUCCESS
        self.result_items: defaultdict[ExtendedResultEnum, list[ItemResult]] = defaultdict(list)
        self.gh_helper: GithubActionHelper = GithubActionHelper()
        self.ignore_warnings = args.ignore_warnings

        init_logging(verbose=args.verbose)

    def run(self: Self) -> None:
        logger.info("============ STL Corruption Checker & Fixer ============")
        logger.info("Searching for STL files in '{}'", str(self.input_dir))

        stl_paths: list[Path] = FileHelper.find_files_by_extension(directory=self.input_dir, extension="stl", max_files=40)

        with ThreadPoolExecutor() as pool:
            return_statuses: list[ExtendedResultEnum] = list(pool.map(self._check_stl, stl_paths))
        if return_statuses:
            self.return_status = max(*return_statuses, self.return_status)
        else:
            self.return_status = ExtendedResultEnum.SUCCESS

        self.gh_helper.finalize_action(
            action_result=ToolResult(
                tool_id=ToolIdentifierEnum.CORRUPTION_CHECK.tool_id,
                tool_name=ToolIdentifierEnum.CORRUPTION_CHECK.tool_name,
                extended_result=self.return_status,
                tool_ignore_warnings=self.ignore_warnings,
                tool_result_items=ToolSummaryTable(
                    extra_columns=["Number of STL fixes applicable"],
                    items=self.result_items,
                ),
            )
        )

    def _write_fixed_stl_file(self: Self, stl: Stl, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Saving fixed STL to '{}'", path)
        temp_file = tempfile.NamedTemporaryFile(suffix=".stl")
        stl.write_binary(temp_file.name)
        self.gh_helper.set_artifact(file_name=path.as_posix(), file_contents=Path(temp_file.name).read_bytes())
        temp_file.close()

    def _check_stl(self: Self, stl_file_path: Path) -> ExtendedResultEnum:
        try:
            stl: Stl = Stl(stl_file_path.as_posix())
            stl.repair(verbose_flag=False)
            if (
                stl.stats["edges_fixed"] > 0
                or stl.stats["backwards_edges"] > 0
                or stl.stats["degenerate_facets"] > 0
                or stl.stats["facets_removed"] > 0
                or stl.stats["facets_added"] > 0
                or stl.stats["facets_reversed"] > 0
            ):
                logger.error("Corrupt STL detected '{}'!", stl_file_path.relative_to(self.input_dir).as_posix())
                number_of_errors: int = sum(
                    int(stl.stats[key]) for key in ["edges_fixed", "backwards_edges", "degenerate_facets", "facets_removed", "facets_added", "facets_reversed"]
                )
                self.result_items[ExtendedResultEnum.FAILURE].append(ItemResult(item=stl_file_path.name, extra_info=[str(number_of_errors)]))
                self._write_fixed_stl_file(stl=stl, path=Path(stl_file_path.relative_to(self.input_dir)))
                return ExtendedResultEnum.FAILURE
            logger.success("STL '{}' OK!", stl_file_path.relative_to(self.input_dir).as_posix())
            self.result_items[ExtendedResultEnum.SUCCESS].append(ItemResult(item=stl_file_path.name, extra_info=["0"]))
            return ExtendedResultEnum.SUCCESS
        except Exception:  # noqa: BLE001
            logger.critical("A fatal error occurred while checking '{}'!", stl_file_path.relative_to(self.input_dir).as_posix())
            self.result_items[ExtendedResultEnum.EXCEPTION].append(ItemResult(item=stl_file_path.name, extra_info=["0"]))
            return ExtendedResultEnum.EXCEPTION


def main() -> None:
    parser: configargparse.ArgumentParser = configargparse.ArgumentParser(
        prog="VoronDesign STL Corruption Checker & Fixer",
        description="This tool can be used to check a provided folder of STLs and potentially fix them",
    )
    parser.add_argument(
        "-i",
        "--input_dir",
        required=True,
        action="store",
        type=str,
        env_var="VORON_TOOLKIT_INPUT_DIR",
        help="Directory containing STL files to be checked",
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
    STLCorruptionChecker(args=args).run()


if __name__ == "__main__":
    main()
