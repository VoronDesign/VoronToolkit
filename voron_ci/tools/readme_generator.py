import argparse
import json
import textwrap
from pathlib import Path
from typing import Any, Self

import yaml

from voron_ci.utils.github_action_helper import GithubActionHelper
from voron_ci.utils.logging import init_logging

logger = init_logging(__name__)

PREAMBLE = """# Mods

Printer mods for Voron 3D printers

## Legacy printers

Mods for legacy printers can be found [here](../legacy_printers/printer_mods).
If one of your legacy mods applies to a current Voron 3D printer and therefore should be included in this list,
contact the admins on Discord to have your mod moved to this folder.

---

"""


class ReadmeGenerator:
    def __init__(self: Self, args: argparse.Namespace) -> None:
        self.input_dir: Path = Path(Path.cwd(), args.input_dir)
        self.verbosity: bool = args.verbose
        self.json_path: str = args.json_path
        self.readme_path: str = args.readme_path

    def run(self: Self) -> None:
        if self.verbosity:
            logger.setLevel("INFO")
        yaml_list = Path(self.input_dir).glob("**/.metadata.yml")
        mods: list[dict[str, Any]] = []
        for yml_file in sorted(yaml_list):
            with Path(yml_file).open("r") as f:
                content = yaml.safe_load(f)
                mods.append(
                    {
                        "path": yml_file.relative_to(self.input_dir).parent.as_posix(),
                        "title": textwrap.shorten(content["title"], width=35, placeholder="..."),
                        "creator": yml_file.relative_to(self.input_dir).parts[0],
                        "description": textwrap.shorten(content["description"], width=70, placeholder="..."),
                        "printer_compatibility": f'{", ".join(sorted(content["printer_compatibility"]))}',
                        "last_changed": GithubActionHelper.last_commit_timestamp(file_or_directory=yml_file.relative_to(self.input_dir).parent),
                    }
                )

        readme_rows: list[tuple[str, ...]] = []
        prev_username: str = ""
        for mod in mods:
            readme_rows.append(
                (
                    mod["creator"] if mod["creator"] != prev_username else "",
                    f'[{mod["title"]}]({mod["path"]})',
                    mod["description"],
                    mod["printer_compatibility"],
                    mod["last_changed"],
                )
            )
            prev_username = mod["creator"]

        GithubActionHelper.print_summary_table(
            preamble="# Printer Readme Preview", columns=["Creator", "Mod title", "Description", "Printer compatibility", "Last Changed"], rows=readme_rows
        )

        if self.json_path:
            with Path(self.json_path).open("w", encoding="utf-8") as f:
                json.dump(mods, f, indent=4)

        if self.readme_path:
            with Path(self.readme_path).open("w", encoding="utf-8") as f:
                f.write(
                    GithubActionHelper.create_markdown_table(
                        preamble=PREAMBLE, columns=["Creator", "Mod title", "Description", "Printer compatibility", "Last Changed"], rows=readme_rows
                    )
                )


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="VoronDesign VoronUsers readme generator",
        description="This tool is used to generate the readme and json overview files for VORONUsers",
    )
    parser.add_argument(
        "-i",
        "--input_dir",
        required=True,
        action="store",
        type=str,
        help="Base directory to search for metadata files",
    )
    parser.add_argument(
        "-r",
        "--readme_path",
        required=True,
        action="store",
        type=str,
        help="Readme output path (leave empty to not generate a Readme file)",
        default="",
    )
    parser.add_argument(
        "-j",
        "--json_path",
        required=True,
        action="store",
        type=str,
        help="Json output path (leave empty to not generate a json file)",
        default="",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        required=True,
        action="store_true",
        help="Print debug output to stdout",
        default=False,
    )
    args: argparse.Namespace = parser.parse_args()
    ReadmeGenerator(args=args).run()


if __name__ == "__main__":
    main()
