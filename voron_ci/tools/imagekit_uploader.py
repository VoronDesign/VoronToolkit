import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Self

from imagekitio import ImageKit

if TYPE_CHECKING:
    from imagekitio.models.results import UploadFileResult
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions

from voron_ci.utils.logging import init_logging

logger = init_logging(__name__)


class ImageKitUploader:
    def __init__(self: Self, args: argparse.Namespace) -> None:
        self.input_dir: Path = Path(Path.cwd(), args.input_dir)
        self.verbosity: bool = args.verbose
        self.fail_on_error: bool = args.fail_on_error

        try:
            self.imagekit: ImageKit = ImageKit(
                private_key=os.environ["IMAGEKIT_PRIVATE_KEY"],
                public_key=os.environ["IMAGEKIT_PUBLIC_KEY"],
                url_endpoint=os.environ["IMAGEKIT_URL_ENDPOINT"],
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
            imagekit_options.folder = image_path.parent.relative_to(Path(self.input_dir)).as_posix()
            result: UploadFileResult = self.imagekit.upload_file(file=image, file_name=image_path.name, options=imagekit_options)
            return result.url != ""

    def run(self: Self) -> None:
        if self.verbosity:
            logger.setLevel("INFO")

        logger.info("Processing Image files in %s", self.input_dir.as_posix())

        images: list[Path] = list(self.input_dir.glob("**/*.png"))
        if not images:
            logger.warning("No images found in input_dir %s!", self.input_dir.as_posix())
            return
        with ThreadPoolExecutor() as pool:
            results = pool.map(self.upload_image, images)

        if not all(results) and self.fail_on_error:
            logger.error("Errors detected during image upload!")
            sys.exit(255)


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="VoronDesign Imagekit uploader",
        description="This tool can be used to upload images to an imagekit account",
    )
    parser.add_argument(
        "-i",
        "--input_folder",
        required=True,
        action="store",
        type=str,
        help="Directory containing image files to be uploaded",
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
        "-v",
        "--verbose",
        required=False,
        action="store_true",
        help="Print debug output to stdout",
        default=False,
    )
    args: argparse.Namespace = parser.parse_args()
    ImageKitUploader(args=args).run()


if __name__ == "__main__":
    main()