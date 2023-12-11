import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Self

import configargparse
from imagekitio import ImageKit
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
from loguru import logger

from voron_ci.utils.github_action_helper import GithubActionHelper
from voron_ci.utils.logging import init_logging

if TYPE_CHECKING:
    from collections.abc import Iterator

    from imagekitio.models.results import UploadFileResult

ENV_VAR_PREFIX = "IMAGEKIT_UPLOADER"
IMAGE_SUBDIRECTORY = "rotation_checker/img"


class ImageKitUploader:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.artifact_name: str = args.artifact_name
        self.workflow_run_id: str = args.workflow_run_id
        self.fail_on_error: bool = args.fail_on_error
        self.github_repository: str = args.github_repository
        self.tmp_path: Path = Path()
        self.image_base_path: Path = Path()

        init_logging(verbose=args.verbose)

        try:
            self.imagekit: ImageKit = ImageKit(
                private_key=args.private_key,
                public_key=args.public_key,
                url_endpoint=args.imagekit_endpoint,
            )
            self.imagekit_options_common: UploadFileRequestOptions = UploadFileRequestOptions(
                use_unique_file_name=False,
                is_private_file=False,
                overwrite_file=True,
                overwrite_ai_tags=True,
                overwrite_tags=True,
                overwrite_custom_metadata=True,
            )
        except (KeyError, ValueError):
            logger.warning("No suitable imagekit credentials were found. Skipping image upload!")
            if self.fail_on_error:
                sys.exit(255)
            sys.exit(0)

    def upload_image(self: Self, image_path: Path) -> bool:
        with Path(image_path).open(mode="rb") as image:
            imagekit_options: UploadFileRequestOptions = self.imagekit_options_common
            imagekit_options.folder = image_path.parent.relative_to(Path(self.image_base_path)).as_posix()
            result: UploadFileResult = self.imagekit.upload_file(file=image, file_name=image_path.name, options=imagekit_options)
            return result.url != ""

    def run(self: Self) -> None:
        logger.info("Downloading artifact '{}' from workflow '{}'", self.artifact_name, self.workflow_run_id)
        with tempfile.TemporaryDirectory() as tmpdir:
            logger.info("Created temporary directory '{}'", tmpdir)
            tmp_path = Path(tmpdir)

            GithubActionHelper.download_artifact(
                repo=self.github_repository,
                workflow_run_id=self.workflow_run_id,
                artifact_name=self.artifact_name,
                target_directory=tmp_path,
            )

            self.image_base_path = Path(tmp_path, IMAGE_SUBDIRECTORY)

            logger.info("Processing Image files in '{}'", tmp_path.as_posix())

            images: list[Path] = list(self.image_base_path.glob("**/*.png"))
            if not images:
                logger.warning("No images found in input_dir '{}'!", self.image_base_path.as_posix())
                return
            with ThreadPoolExecutor() as pool:
                results: Iterator[bool] = pool.map(self.upload_image, images)

            if not all(results) and self.fail_on_error:
                logger.error("Errors detected during image upload!")
                sys.exit(255)


def main() -> None:
    parser: configargparse.ArgumentParser = configargparse.ArgumentParser(
        prog="VoronDesign Imagekit uploader",
        description="This tool can be used to upload images to an imagekit account",
    )
    parser.add_argument(
        "-i",
        "--workflow_run_id",
        required=True,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_WORKFLOW_RUN_ID",
        help="Run ID of the workflow from which to pull the artifact",
    )
    parser.add_argument(
        "-n",
        "--artifact_name",
        required=True,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_ARTIFACT_NAME",
        help="Name of the artifact to download and extract images from",
    )
    parser.add_argument(
        "-r",
        "--private_key",
        required=True,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_PRIVATE_KEY",
        help="Imagekit private key",
    )
    parser.add_argument(
        "-p",
        "--public_key",
        required=True,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_PUBLIC_KEY",
        help="Imagekit public key",
    )
    parser.add_argument(
        "-u",
        "--imagekit_endpoint",
        required=True,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_IMAGEKIT_ENDPOINT",
        help="Imagekit url endpoint (e.g. https://ik.imagekit.io/username)",
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
        "--github_repository",
        required=False,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_GITHUB_REPOSITORY",
        default=os.environ["GITHUB_REPOSITORY"],
        help="Repository from which to download the artifact",
    )
    args: configargparse.Namespace = parser.parse_args()
    ImageKitUploader(args=args).run()


if __name__ == "__main__":
    main()
