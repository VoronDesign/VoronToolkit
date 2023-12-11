import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Self

import configargparse
from admesh import Stl
from loguru import logger

from voron_ci.constants import ReturnStatus, SummaryStatus
from voron_ci.utils.action_summary import ActionSummaryTable
from voron_ci.utils.file_helper import FileHelper
from voron_ci.utils.github_action_helper import ActionResult, GithubActionHelper
from voron_ci.utils.logging import init_logging

ENV_VAR_PREFIX = "CORRUPTION_CHECKER"


class STLCorruptionChecker:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.input_dir: Path = Path(Path.cwd(), args.input_dir)
        self.return_status: ReturnStatus = ReturnStatus.SUCCESS
        self.check_summary: list[list[str]] = []
        self.gh_helper: GithubActionHelper = GithubActionHelper(ignore_warnings=args.ignore_warnings)

        init_logging(verbose=args.verbose)

    def run(self: Self) -> None:
        logger.info("Searching for STL files in '{}'", str(self.input_dir))

        stl_paths: list[Path] = FileHelper.find_files(directory=self.input_dir, extension="stl", max_files=40)

        with ThreadPoolExecutor() as pool:
            return_statuses: list[ReturnStatus] = list(pool.map(self._check_stl, stl_paths))
        if return_statuses:
            self.return_status = max(*return_statuses, self.return_status)
        else:
            self.return_status = ReturnStatus.SUCCESS

        self.gh_helper.finalize_action(
            action_result=ActionResult(
                action_id="stl_corruption_checker",
                action_name="STL Corruption Checker",
                outcome=self.return_status,
                summary=ActionSummaryTable(
                    title="STL Corruption Checker",
                    columns=["Filename", "Result", "Edges Fixed", "Backwards Edges", "Degenerate Facets", "Facets Removed", "Facets Added", "Facets Reversed"],
                    rows=self.check_summary,
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

    def _check_stl(self: Self, stl_file_path: Path) -> ReturnStatus:
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
                self.check_summary.append(
                    [
                        stl_file_path.name,
                        SummaryStatus.FAILURE,
                        str(stl.stats["edges_fixed"]),
                        str(stl.stats["backwards_edges"]),
                        str(stl.stats["degenerate_facets"]),
                        str(stl.stats["facets_removed"]),
                        str(stl.stats["facets_added"]),
                        str(stl.stats["facets_reversed"]),
                    ]
                )
                self._write_fixed_stl_file(stl=stl, path=Path(stl_file_path.relative_to(self.input_dir)))
                return ReturnStatus.FAILURE
            logger.success("STL '{}' OK!", stl_file_path.relative_to(self.input_dir).as_posix())
            return ReturnStatus.SUCCESS
        except Exception:  # noqa: BLE001
            logger.exception("A fatal error occurred while checking '{}'!", stl_file_path.relative_to(self.input_dir).as_posix())
            self.check_summary.append(
                [stl_file_path.name, SummaryStatus.EXCEPTION, "0", "0", "0", "0", "0", "0"],
            )
            return ReturnStatus.EXCEPTION


def main() -> None:
    parser: configargparse.ArgumentParser = configargparse.ArgumentParser(
        prog="VoronDesign STL checker & fixer",
        description="This tool can be used to check a provided folder of STLs and potentially fix them",
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
        env_var=f"{ENV_VAR_PREFIX}_VERBOSE",
        help="Print debug output to stdout",
        default=False,
    )
    args: configargparse.Namespace = parser.parse_args()
    STLCorruptionChecker(args=args).run()


if __name__ == "__main__":
    main()
