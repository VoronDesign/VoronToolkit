import json
import textwrap
from pathlib import Path
from typing import Any, Self

import configargparse
import yaml
from loguru import logger

from voron_ci.constants import ReturnStatus
from voron_ci.utils.action_summary import ActionSummaryTable
from voron_ci.utils.github_action_helper import ActionResult, GithubActionHelper
from voron_ci.utils.logging import init_logging

PREAMBLE = """# Mods

Printer mods for Voron 3D printers

## Legacy printers

Mods for legacy printers can be found [here](../legacy_printers/printer_mods).
If one of your legacy mods applies to a current Voron 3D printer and therefore should be included in this list,
contact the admins on Discord to have your mod moved to this folder.

---

"""

ENV_VAR_PREFIX = "README_GENERATOR"


class ReadmeGenerator:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.input_dir: Path = Path(Path.cwd(), args.input_dir)
        self.json: bool = args.json
        self.readme: bool = args.readme
        self.gh_helper: GithubActionHelper = GithubActionHelper(ignore_warnings=False)

        init_logging(verbose=args.verbose)

    def run(self: Self) -> None:
        logger.info("ReadmeGenerator starting up readme: '{}', json: '{}', input_dir: '{}'", self.readme, self.json, self.input_dir.as_posix())
        yaml_list = Path(self.input_dir).glob("**/.metadata.yml")
        mods: list[dict[str, Any]] = []
        for yml_file in sorted(yaml_list):
            logger.info("Parsing '{}'", yml_file.relative_to(self.input_dir).parent.as_posix())
            with Path(yml_file).open("r") as f:
                content = yaml.safe_load(f)
                mods.append(
                    {
                        "path": yml_file.relative_to(self.input_dir).parent.as_posix(),
                        "title": content["title"],
                        "creator": yml_file.relative_to(self.input_dir).parts[0],
                        "description": content["description"],
                        "printer_compatibility": f'{", ".join(sorted(content["printer_compatibility"]))}',
                        "last_changed": GithubActionHelper.last_commit_timestamp(file_or_directory=yml_file.parent),
                    }
                )

        readme_rows: list[list[str]] = []
        prev_username: str = ""
        logger.info("Generating rows for {} mods", len(mods))
        for mod in mods:
            readme_rows.append(
                [
                    mod["creator"] if mod["creator"] != prev_username else "",
                    f'[{textwrap.shorten(mod["title"], width=35, placeholder="...")}]({mod["path"]})',
                    textwrap.shorten(mod["description"], width=70, placeholder="..."),
                    mod["printer_compatibility"],
                    mod["last_changed"],
                ]
            )
            prev_username = mod["creator"]

        if self.json:
            logger.info("Writing json file!")
            self.gh_helper.set_artifact(file_name="mods.json", file_contents=json.dumps(mods, indent=4))

        if self.readme:
            logger.info("Writing README file!")
            self.gh_helper.set_artifact(
                file_name="README.md",
                file_contents=f"{PREAMBLE}\n\n"
                + ActionSummaryTable.create_markdown_table(
                    columns=["Creator", "Mod title", "Description", "Printer compatibility", "Last Changed"], rows=readme_rows
                ),
            )

        self.gh_helper.finalize_action(
            action_result=ActionResult(
                action_id="readme_generator",
                action_name="Readme generator",
                outcome=ReturnStatus.SUCCESS,
                summary=ActionSummaryTable(
                    title="Readme preview",
                    columns=["Creator", "Mod title", "Description", "Printer compatibility", "Last Changed"],
                    rows=readme_rows,
                ),
            )
        )


def main() -> None:
    parser: configargparse.ArgumentParser = configargparse.ArgumentParser(
        prog="VoronDesign VoronUsers readme generator",
        description="This tool is used to generate the readme and json overview files for VORONUsers",
    )
    parser.add_argument(
        "-i",
        "--input_dir",
        required=True,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_INPUT_DIR",
        help="Base directory to search for metadata files",
    )
    parser.add_argument(
        "-r",
        "--readme",
        required=False,
        action="store_true",
        env_var=f"{ENV_VAR_PREFIX}_README",
        help="Whether to generate a readme file",
        default=False,
    )
    parser.add_argument(
        "-j",
        "--json",
        required=False,
        action="store_true",
        env_var=f"{ENV_VAR_PREFIX}_JSON",
        help="Whether to generate a json file",
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
    ReadmeGenerator(args=args).run()


if __name__ == "__main__":
    main()
