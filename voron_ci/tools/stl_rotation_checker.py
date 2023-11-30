import random
import re
import string
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Self

import configargparse
from tweaker3 import FileHandler
from tweaker3.MeshTweaker import Tweak

from voron_ci.contants import EXTENDED_OUTCOME, ReturnStatus, SummaryStatus
from voron_ci.utils.file_helper import FileHelper
from voron_ci.utils.github_action_helper import GithubActionHelper
from voron_ci.utils.logging import init_logging

logger = init_logging(__name__)

TWEAK_THRESHOLD = 0.1
ENV_VAR_PREFIX = "ROTATION_CHECKER"


class STLRotationChecker:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.input_dir: Path = Path(Path.cwd(), args.input_dir)
        self.output_dir: Path | None = Path(Path.cwd(), args.output_dir) if args.output_dir else None
        self.fail_on_error: bool = args.fail_on_error
        self.imagekit_endpoint: str | None = args.url_endpoint if args.url_endpoint else None
        self.imagekit_subfolder: str = args.imagekit_subfolder
        self.print_gh_step_summary: bool = args.github_step_summary
        self.file_handler: FileHandler.FileHandler = FileHandler.FileHandler()
        self.return_status: ReturnStatus = ReturnStatus.SUCCESS
        self.check_summary: list[tuple[str, ...]] = []
        self.error_count: int = 0

        if args.verbose:
            logger.setLevel("INFO")

    @staticmethod
    def get_random_string(length: int) -> str:
        # choose from all lower/uppercase letters
        letters: str = string.ascii_lowercase + string.ascii_uppercase
        result_str: str = "".join(random.choice(letters) for _ in range(length))  # noqa: S311
        return result_str

    def make_markdown_image(self: Self, base_dir: Path | None, stl_file_path: Path) -> str:
        # Generate the filename:
        #  Replace stl with png
        #  Append 8 digit random string to avoid collisions. This is necessary so that old CI runs still show their respective images"
        if not self.output_dir or not self.imagekit_endpoint or not base_dir:
            return ""

        if self.imagekit_subfolder is None:
            self.logger.error("Warning, no imagekit subfolder provided!")

        image_file_name = stl_file_path.with_stem(stl_file_path.stem + "_" + self.get_random_string(8)).with_suffix(".png").name
        image_in_path = Path(base_dir, stl_file_path)
        image_out_path = Path(self.output_dir, "img", self.imagekit_subfolder, image_file_name)
        image_out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["stl-thumb", image_in_path.as_posix(), image_out_path.as_posix(), "-a", "fxaa", "-s", "300"]

        subprocess.check_output(cmd, stderr=subprocess.DEVNULL, shell=True)  # noqa: S602
        # Imagekit replaces "[", "]", "(", ")" with underscores
        image_address: str = re.sub(r"\]|\[|\)|\(", "_", f"{self.imagekit_endpoint}/{self.imagekit_subfolder}/{image_file_name}")
        return f'[<img src="{image_address}" width="100" height="100">]({image_address})'

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
                title=f"STL rotation check (errors: {self.error_count})", default_open=self.return_status == ReturnStatus.SUCCESS
            ):
                GithubActionHelper.print_summary_table(
                    columns=["Filename", "Result", "Current orientation", "Suggested orientation"],
                    rows=self.check_summary,
                )

        GithubActionHelper.write_output(output={"extended-outcome": EXTENDED_OUTCOME[self.return_status]})

        if self.return_status > ReturnStatus.SUCCESS and self.fail_on_error:
            logger.error("Error detected during STL checking!")
            sys.exit(255)

    def _write_fixed_stl_file(self: Self, stl: dict[int, Any], opts: Tweak, stl_file_path: Path) -> None:
        if not self.output_dir:
            return
        output_path = Path(self.output_dir, stl_file_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Saving rotated STL to '%s'", output_path)
        self.file_handler.write_mesh(objects=stl, info={0: {"matrix": opts.matrix, "tweaker_stats": opts}}, outputfile=output_path.as_posix())

    def _check_stl(self: Self, stl_file_path: Path) -> ReturnStatus:
        logger.info("Checking '%s'", stl_file_path.relative_to(self.input_dir).as_posix())
        rotated_image_url: str = ""
        try:
            mesh_objects: dict[int, Any] = self.file_handler.load_mesh(inputfile=stl_file_path.as_posix())
            if len(mesh_objects.items()) > 1:
                logger.warning("File '%s' contains multiple objects and is therefore skipped!", stl_file_path.relative_to(self.input_dir).as_posix())
                self.check_summary.append((stl_file_path.name, SummaryStatus.WARNING, "", ""))
                self.error_count += 1
                return ReturnStatus.WARNING
            rotated_mesh: Tweak = Tweak(mesh_objects[0]["mesh"], extended_mode=True, verbose=False, min_volume=True)
            original_image_url: str = self.make_markdown_image(base_dir=self.input_dir, stl_file_path=stl_file_path.relative_to(self.input_dir))

            if rotated_mesh.rotation_angle >= TWEAK_THRESHOLD:
                logger.warning("Found rotation suggestion for STL '%s'!", stl_file_path.relative_to(self.input_dir).as_posix())
                output_stl_path: Path = Path(
                    stl_file_path.relative_to(self.input_dir).with_stem(f"{stl_file_path.stem}_rotated"),
                )
                self._write_fixed_stl_file(stl=mesh_objects, opts=rotated_mesh, stl_file_path=output_stl_path)
                rotated_image_url = self.make_markdown_image(base_dir=self.output_dir, stl_file_path=output_stl_path)
                self.check_summary.append(
                    (
                        stl_file_path.name,
                        SummaryStatus.WARNING,
                        original_image_url,
                        rotated_image_url,
                    ),
                )
                self.error_count += 1
                return ReturnStatus.WARNING
            self.check_summary.append((stl_file_path.name, SummaryStatus.SUCCESS, original_image_url, ""))
            return ReturnStatus.SUCCESS
        except Exception as e:
            logger.exception("A fatal error occurred during rotation checking", exc_info=e)
            self.check_summary.append((stl_file_path.name, SummaryStatus.EXCEPTION, "", ""))
            self.error_count += 1
            return ReturnStatus.EXCEPTION


def main() -> None:
    parser: configargparse.ArgumentParser = configargparse.ArgumentParser(
        prog="VoronDesign STL rotation checker & fixer",
        description="This tool can be used to check the rotation of STLs in a folder and potentially fix them",
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
        "-u",
        "--url_endpoint",
        required=False,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_IMAGEKIT_ENDPOINT",
        help="Imagekit endpoint",
        default="",
    )
    parser.add_argument(
        "-c",
        "--imagekit_subfolder",
        required=False,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_IMAGEKIT_SUBFOLDER",
        help="Image subfolder within the imagekit storage",
        default="",
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
        "-v",
        "--verbose",
        required=False,
        action="store_true",
        env_var=f"{ENV_VAR_PREFIX}_VERBOSE",
        help="Print debug output to stdout",
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
    STLRotationChecker(args=args).run()


if __name__ == "__main__":
    main()
