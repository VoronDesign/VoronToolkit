import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Self

import configargparse
from admesh import Stl

from voron_ci.contants import EXTENDED_OUTCOME, ReturnStatus, SummaryStatus
from voron_ci.utils.file_helper import FileHelper
from voron_ci.utils.github_action_helper import GithubActionHelper
from voron_ci.utils.logging import init_logging

logger = init_logging(__name__)


ENV_VAR_PREFIX = "CORRUPTION_CHECKER"


class STLCorruptionChecker:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.input_dir: Path = Path(Path.cwd(), args.input_dir)
        self.output_dir: Path | None = Path(Path.cwd(), args.output_dir) if args.output_dir else None
        self.fail_on_error: bool = args.fail_on_error
        self.print_gh_step_summary: bool = args.github_step_summary
        self.return_status: ReturnStatus = ReturnStatus.SUCCESS
        self.check_summary: list[tuple[str, ...]] = []
        self.error_count: int = 0

        if args.verbose:
            logger.setLevel("INFO")

    def run(self: Self) -> None:
        logger.info("Searching for STL files in '%s'", str(self.input_dir))

        stl_paths: list[Path] = FileHelper.find_files(directory=self.input_dir, extension="stl", max_files=40)

        with ThreadPoolExecutor() as pool:
            return_statuses: list[ReturnStatus] = list(pool.map(self._check_stl, stl_paths))
        if return_statuses:
            self.return_status = max(*return_statuses, self.return_status)
        else:
            self.return_status = ReturnStatus.SUCCESS

        if self.print_gh_step_summary:
            with GithubActionHelper.expandable_section(
                title=f"STL corruption check (errors: {self.error_count})", default_open=self.return_status == ReturnStatus.SUCCESS
            ):
                GithubActionHelper.print_summary_table(
                    columns=["Filename", "Result", "Edges Fixed", "Backwards Edges", "Degenerate Facets", "Facets Removed", "Facets Added", "Facets Reversed"],
                    rows=self.check_summary,
                )

        GithubActionHelper.write_output(output={"extended-outcome": EXTENDED_OUTCOME[self.return_status]})

        if self.return_status > ReturnStatus.SUCCESS and self.fail_on_error:
            logger.error("Error detected during STL checking!")
            sys.exit(255)

    @staticmethod
    def _write_fixed_stl_file(stl: Stl, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Saving fixed STL to '%s'", path)
        stl.write_ascii(path.as_posix())

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
                logger.error("Corrupt STL detected! Please fix '%s'!", stl_file_path.relative_to(self.input_dir).as_posix())
                self.check_summary.append(
                    (
                        stl_file_path.name,
                        SummaryStatus.FAILURE,
                        str(stl.stats["edges_fixed"]),
                        str(stl.stats["backwards_edges"]),
                        str(stl.stats["degenerate_facets"]),
                        str(stl.stats["facets_removed"]),
                        str(stl.stats["facets_added"]),
                        str(stl.stats["facets_reversed"]),
                    )
                )
                if self.output_dir is not None:
                    self._write_fixed_stl_file(
                        stl=stl,
                        path=Path(self.output_dir, stl_file_path.relative_to(self.input_dir)),
                    )
                self.error_count += 1
                return ReturnStatus.FAILURE
            logger.info("STL '%s' does not contain any errors!", stl_file_path.relative_to(self.input_dir).as_posix())
            self.check_summary.append(
                (stl_file_path.name, SummaryStatus.SUCCESS, "0", "0", "0", "0", "0", "0"),
            )
            return ReturnStatus.SUCCESS
        except Exception as e:
            logger.exception("A fatal error occurred during corruption checking", exc_info=e)
            self.check_summary.append(
                (stl_file_path.name, SummaryStatus.EXCEPTION, "0", "0", "0", "0", "0", "0"),
            )
            self.error_count += 1
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
        "-o",
        "--output_dir",
        required=False,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_OUTPUT_DIR",
        help="Directory to store the fixed STL files into",
        default="",
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
        "--fail_on_error",
        required=False,
        action="store_true",
        env_var=f"{ENV_VAR_PREFIX}_FAIL_ON_ERROR",
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
    STLCorruptionChecker(args=args).run()


if __name__ == "__main__":
    main()
