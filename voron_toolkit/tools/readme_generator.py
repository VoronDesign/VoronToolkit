import json
import textwrap
from collections import defaultdict
from importlib.resources import files
from pathlib import Path
from typing import Any, Self

import configargparse
import jsonschema
import yaml
from loguru import logger

from voron_toolkit import resources
from voron_toolkit.constants import ExtendedResultEnum, ItemResult, ToolIdentifierEnum, ToolResult, ToolSummaryTable
from voron_toolkit.utils.file_helper import FileHelper
from voron_toolkit.utils.github_action_helper import GithubActionHelper
from voron_toolkit.utils.logging import init_logging

PREAMBLE = """# Mods

Printer mods for Voron 3D printers
---

"""

ENV_VAR_PREFIX = "README_GENERATOR"


class ReadmeGenerator:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.input_dir: Path = Path(Path.cwd(), args.input_dir)
        self.json: bool = args.json
        self.markdown: bool = args.markdown
        self.gh_helper: GithubActionHelper = GithubActionHelper()
        self.result_items: defaultdict[ExtendedResultEnum, list[ItemResult]] = defaultdict(list)

        init_logging(verbose=args.verbose)

    def run(self: Self) -> None:
        logger.info("============ README Generator ============")
        logger.info("ReadmeGenerator starting up (markdown: '{}', json: '{}', input_dir: '{}')", self.markdown, self.json, self.input_dir.as_posix())
        yaml_list: list[Path] = FileHelper.find_files_by_name(self.input_dir, ".metadata.yml")
        schema: dict[str, Any] = json.loads(files(resources).joinpath("voronusers_metadata_schema.json").read_text())
        result: ExtendedResultEnum = ExtendedResultEnum.SUCCESS
        mods: list[dict[str, Any]] = []
        for yml_file in sorted(yaml_list):
            mod_path: str = yml_file.relative_to(self.input_dir).parent.as_posix()
            try:
                metadata: dict[str, Any] = yaml.safe_load(yml_file.read_text())
                jsonschema.validate(instance=metadata, schema=schema)
            except (yaml.YAMLError, yaml.scanner.ScannerError) as e:
                logger.error("YAML error in metadata file of mod '{}': {}", mod_path, e)
                result = ExtendedResultEnum.FAILURE
                self.result_items[ExtendedResultEnum.FAILURE].append(
                    ItemResult(
                        item=mod_path,
                        extra_info=["Error loading yaml file", ""],
                    )
                )
                mods.append(
                    {
                        "path": mod_path,
                        "title": f"{ExtendedResultEnum.FAILURE.icon} Error loading yaml file",
                        "creator": yml_file.relative_to(self.input_dir).parts[0],
                        "description": "",
                        "printer_compatibility": "",
                        "last_changed": "",
                    }
                )
                continue
            except jsonschema.ValidationError as e:
                logger.error("Validation error in metadata file of mod '{}': {}", mod_path, e.message)
                self.result_items[ExtendedResultEnum.FAILURE].append(
                    ItemResult(
                        item=mod_path,
                        extra_info=["Error validating yaml file", ""],
                    )
                )
                mods.append(
                    {
                        "path": mod_path,
                        "title": f"{ExtendedResultEnum.FAILURE.icon} Error validating yaml file",
                        "creator": yml_file.relative_to(self.input_dir).parts[0],
                        "description": "",
                        "printer_compatibility": "",
                        "last_changed": "",
                    }
                )
                result = ExtendedResultEnum.FAILURE
                continue
            logger.success("Mod '{}' OK!", mod_path)
            self.result_items[ExtendedResultEnum.SUCCESS].append(
                ItemResult(
                    item=mod_path,
                    extra_info=[
                        textwrap.shorten(metadata["description"], width=70, placeholder="..."),
                        f'{", ".join(sorted(metadata["printer_compatibility"]))}',
                    ],
                )
            )
            mods.append(
                {
                    "path": mod_path,
                    "title": metadata["title"],
                    "creator": yml_file.relative_to(self.input_dir).parts[0],
                    "description": metadata["description"],
                    "printer_compatibility": sorted(metadata["printer_compatibility"]),
                    "last_changed": GithubActionHelper.last_commit_timestamp(file_or_directory=yml_file.parent),
                }
            )

        readme_rows: list[list[str]] = []
        prev_username: str = ""
        logger.info("Generating rows for {} mods", len(mods))
        for mod in sorted(mods, key=lambda x: x["path"].lower()):
            readme_rows.append(
                [
                    mod["creator"] if mod["creator"] != prev_username else "",
                    f'[{textwrap.shorten(mod["title"], width=35, placeholder="...")}]({mod["path"]})',
                    textwrap.shorten(mod["description"], width=70, placeholder="..."),
                    f'{", ".join(mod["printer_compatibility"])}',
                    mod["last_changed"],
                ]
            )
            prev_username = mod["creator"]

        if self.json and (result == ExtendedResultEnum.SUCCESS):
            logger.info("Writing json file!")
            self.gh_helper.set_artifact(file_name="mods.json", file_contents=json.dumps(mods, indent=4))

        if self.markdown and (result == ExtendedResultEnum.SUCCESS):
            logger.info("Writing README file!")
            self.gh_helper.set_artifact(
                file_name="README.md",
                file_contents=f"{PREAMBLE}\n\n"
                + ToolSummaryTable.create_markdown_table(
                    columns=["Creator", "Mod title", "Description", "Printer compatibility", "Last Changed"], rows=readme_rows
                ),
            )

        self.gh_helper.finalize_action(
            action_result=ToolResult(
                tool_id=ToolIdentifierEnum.README_GENERATOR.tool_id,
                tool_name=ToolIdentifierEnum.README_GENERATOR.tool_name,
                extended_result=result,
                tool_ignore_warnings=False,
                tool_result_items=ToolSummaryTable(
                    extra_columns=["Description/Error", "Printer compatibility"],
                    items=self.result_items,
                ),
            )
        )


def main() -> None:
    parser: configargparse.ArgumentParser = configargparse.ArgumentParser(
        prog="VoronDesign README Generator",
        description="This tool is used to generate the readme and json overview files for VORONUsers",
    )
    parser.add_argument(
        "-i",
        "--input_dir",
        required=True,
        action="store",
        type=str,
        env_var="VORON_TOOLKIT_INPUT_DIR",
        help="Base directory to search for metadata files",
    )
    parser.add_argument(
        "-r",
        "--markdown",
        required=False,
        action="store_true",
        env_var=f"{ENV_VAR_PREFIX}_MARKDOWN",
        help="Whether to generate a readme markdown file",
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
        env_var="VORON_TOOLKIT_VERBOSE",
        help="Print debug output to stdout",
        default=False,
    )
    args: configargparse.Namespace = parser.parse_args()
    ReadmeGenerator(args=args).run()


if __name__ == "__main__":
    main()
