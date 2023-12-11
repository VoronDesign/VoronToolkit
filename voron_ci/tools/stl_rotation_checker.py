import random
import re
import string
import struct
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Self

import configargparse
from loguru import logger
from tweaker3.FileHandler import FileHandler
from tweaker3.MeshTweaker import Tweak

from voron_ci.constants import ReturnStatus, SummaryStatus
from voron_ci.utils.action_summary import ActionSummaryTable
from voron_ci.utils.file_helper import FileHelper
from voron_ci.utils.github_action_helper import ActionResult, GithubActionHelper
from voron_ci.utils.logging import init_logging

TWEAK_THRESHOLD = 0.1
ENV_VAR_PREFIX = "ROTATION_CHECKER"
STL_THUMB_IMAGE_SIZE = 500


class STLRotationChecker:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.input_dir: Path = Path(Path.cwd(), args.input_dir)
        self.imagekit_endpoint: str | None = args.imagekit_endpoint if args.imagekit_endpoint else None
        self.imagekit_subfolder: str = args.imagekit_subfolder
        self.return_status: ReturnStatus = ReturnStatus.SUCCESS
        self.check_summary: list[list[str]] = []
        self.gh_helper: GithubActionHelper = GithubActionHelper(ignore_warnings=args.ignore_warnings)

        init_logging(verbose=args.verbose)

    def _get_rotated_stl_bytes(self: Self, objects: dict[int, Any], info: dict[int, Any]) -> bytes:
        # Adapted from https://github.com/ChristophSchranz/Tweaker-3/blob/master/FileHandler.py
        # to return the bytes instead of writing them to a file
        # Note: At this point we have already established that there is only one object in the STL file

        header: bytes = "Tweaked on {}".format(time.strftime("%a %d %b %Y %H:%M:%S")).encode().ljust(79, b" ") + b"\n"
        length: bytes = b""
        mesh: list[bytes] = []
        for part, content in objects.items():
            mesh = content["mesh"]
            partlength = int(len(mesh) / 3)
            mesh = FileHandler().rotate_bin_stl(info[part]["matrix"], mesh)
            length = struct.pack("<I", partlength)
            break
        return bytes(bytearray(header + length + b"".join(mesh)))

    @staticmethod
    def _get_random_string(length: int) -> str:
        # choose from all lower/uppercase letters
        letters: str = string.ascii_lowercase + string.ascii_uppercase
        result_str: str = "".join(random.choice(letters) for _ in range(length))  # noqa: S311
        return result_str

    def _make_markdown_image(self: Self, stl_file_path: Path, stl_file_contents: bytes | None = None) -> str:
        # Check inputs
        if not self.imagekit_endpoint:
            return ""
        if self.imagekit_subfolder is None:
            logger.warning("Warning, no imagekit subfolder provided!")

        # Generate the filename:
        #  Replace stl with png
        #  Append 8 digit random string to avoid collisions. This is necessary so that old CI runs still show their respective images"
        output_image_file_name = stl_file_path.with_stem(stl_file_path.stem + "_" + self._get_random_string(8)).with_suffix(".png").name
        image_out_path = Path("img", self.imagekit_subfolder, output_image_file_name)

        # If the stl file contents have been passed, we need to write out the stl file first
        temp_file = None
        if stl_file_contents:
            temp_file = tempfile.NamedTemporaryFile(suffix=".stl")
            temp_file.write(stl_file_contents)
            temp_file.flush()
            stl_in_path: Path = Path(temp_file.name)
        else:
            stl_in_path = Path(self.input_dir, stl_file_path)

        # Generate the thumbnail using stl-thumb
        # Note: When run entirely headless, stl-thumb will return a non-zero exit code, but still produce the image
        stl_thumb_result: subprocess.CompletedProcess = subprocess.run(  # noqa: PLW1510
            f"stl-thumb {stl_in_path.as_posix()} -a fxaa -s {STL_THUMB_IMAGE_SIZE} -",
            shell=True,  # noqa: S602
            capture_output=True,
        )
        if stl_thumb_result.stdout:
            self.gh_helper.set_artifact(file_name=image_out_path.as_posix(), file_contents=stl_thumb_result.stdout)

        if temp_file is not None:
            temp_file.close()

        # Generate the markdown code for the image
        image_address: str = re.sub(r"\]|\[|\)|\(", "_", f"{self.imagekit_endpoint}/{self.imagekit_subfolder}/{output_image_file_name}")
        return f'[<img src="{image_address}" width="100" height="100">]({image_address})'

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
                action_id="rotation_checker",
                action_name="STL rotation checker",
                outcome=self.return_status,
                summary=ActionSummaryTable(
                    title="STL rotation checker",
                    columns=["Filename", "Result", "Original orientation", "Suggested orientation"],
                    rows=self.check_summary,
                ),
            )
        )

    def _write_fixed_stl_file(self: Self, stl: dict[int, Any], opts: Tweak, stl_file_path: Path) -> None:
        self.gh_helper.set_artifact(
            file_name=stl_file_path.as_posix(), file_contents=self._get_rotated_stl_bytes(objects=stl, info={0: {"matrix": opts.matrix, "tweaker_stats": opts}})
        )

    def _check_stl(self: Self, stl_file_path: Path) -> ReturnStatus:
        try:
            mesh_objects: dict[int, Any] = FileHandler().load_mesh(inputfile=stl_file_path.as_posix())
            if len(mesh_objects.items()) > 1:
                logger.warning("File '{}' contains multiple objects and is therefore skipped!", stl_file_path.relative_to(self.input_dir).as_posix())
                self.check_summary.append([stl_file_path.name, SummaryStatus.WARNING, "", ""])
                return ReturnStatus.WARNING
            rotated_mesh: Tweak = Tweak(mesh_objects[0]["mesh"], extended_mode=True, verbose=False, min_volume=True)

            if rotated_mesh.rotation_angle >= TWEAK_THRESHOLD:
                logger.warning("Found rotation suggestion for STL '{}'!", stl_file_path.relative_to(self.input_dir).as_posix())
                output_stl_path: Path = Path(
                    stl_file_path.relative_to(self.input_dir).with_stem(f"{stl_file_path.stem}_rotated"),
                )
                rotated_stl_bytes: bytes = self._get_rotated_stl_bytes(
                    objects=mesh_objects, info={0: {"matrix": rotated_mesh.matrix, "tweaker_stats": rotated_mesh}}
                )

                self.gh_helper.set_artifact(file_name=output_stl_path.as_posix(), file_contents=rotated_stl_bytes)

                original_image_url: str = self._make_markdown_image(stl_file_path=stl_file_path.relative_to(self.input_dir))
                rotated_image_url: str = self._make_markdown_image(stl_file_path=output_stl_path, stl_file_contents=rotated_stl_bytes)

                self.check_summary.append(
                    [
                        stl_file_path.name,
                        SummaryStatus.WARNING,
                        original_image_url,
                        rotated_image_url,
                    ],
                )
                return ReturnStatus.WARNING

            logger.success("File '{}' OK!", stl_file_path.relative_to(self.input_dir).as_posix())
            return ReturnStatus.SUCCESS
        except Exception:  # noqa: BLE001
            logger.critical("A fatal error occurred while checking {}", stl_file_path.relative_to(self.input_dir).as_posix())
            self.check_summary.append([stl_file_path.name, SummaryStatus.EXCEPTION, "", ""])
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
        "-u",
        "--imagekit_endpoint",
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
    STLRotationChecker(args=args).run()


if __name__ == "__main__":
    main()
