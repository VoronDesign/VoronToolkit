from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Self
from urllib.parse import urlparse

import configargparse
import requests
from loguru import logger
from markdown_it import MarkdownIt
from markdown_it.token import Token
from requests import HTTPError

from voron_toolkit.constants import ExtendedResultEnum, ItemResult, ToolIdentifierEnum, ToolResult, ToolSummaryTable
from voron_toolkit.utils.file_helper import FileHelper
from voron_toolkit.utils.github_action_helper import GithubActionHelper
from voron_toolkit.utils.logging import init_logging

ENV_VAR_PREFIX = "MARKDOWN_LINK_CHECKER"


class MarkdownLinkChecker:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.input_dir: Path = Path(Path.cwd(), args.input_dir)
        self.gh_helper: GithubActionHelper = GithubActionHelper()
        self.ignore_warnings = args.ignore_warnings
        self.return_status: ExtendedResultEnum = ExtendedResultEnum.SUCCESS
        self.all_results: list[ExtendedResultEnum] = []
        self.result_items: defaultdict[ExtendedResultEnum, list[ItemResult]] = defaultdict(list)

        init_logging(verbose=args.verbose)

    def _check_link(self: Self, link: str, markdown_file_relative: str) -> ExtendedResultEnum:
        markdown_file_folder_absolute: Path = Path(self.input_dir, markdown_file_relative).parent
        if link.startswith(".."):
            # The link is a relative path that points to a file outside of the current folder
            logger.warning(
                (
                    "Link '{}' in markdown file '{}' points to a file outside of the current folder."
                    "The validity cannot be checked, please check if the file exists manually."
                ),
                link,
                markdown_file_relative,
            )
            self.result_items[ExtendedResultEnum.WARNING].append(
                ItemResult(
                    item=markdown_file_relative,
                    extra_info=[f"Relative link '{link}' points to a file outside of the current folder! lease check this link manually!"],
                )
            )
            return ExtendedResultEnum.WARNING

        parsed_url = urlparse(link)
        if parsed_url.scheme in ["http", "https"] and parsed_url.netloc != "":
            # The link is a website url
            try:
                response = requests.head(link, timeout=5)
                response.raise_for_status()
            except HTTPError as e:
                logger.error("Link '{}' is invalid: {}, {}", link, e.response.status_code, e.response.reason)
                self.result_items[ExtendedResultEnum.FAILURE].append(ItemResult(item=markdown_file_relative, extra_info=[f"Link '{link}' is invalid: {e}"]))
                return ExtendedResultEnum.FAILURE
            self.result_items[ExtendedResultEnum.SUCCESS].append(ItemResult(item=markdown_file_relative, extra_info=[f"Link '{link}' is valid!"]))
            return ExtendedResultEnum.SUCCESS

        # The link is a relative path, check if the file exists
        if Path(markdown_file_folder_absolute, link).exists():
            self.result_items[ExtendedResultEnum.SUCCESS].append(ItemResult(item=markdown_file_relative, extra_info=[f"Relative link '{link}' is valid!"]))
            return ExtendedResultEnum.SUCCESS

        self.result_items[ExtendedResultEnum.FAILURE].append(ItemResult(item=markdown_file_relative, extra_info=[f"Relative link '{link}' is invalid!"]))
        logger.error("Relative link '{}' is invalid!", Path(markdown_file_folder_absolute, link))
        return ExtendedResultEnum.FAILURE

    def _check_markdown(self: Self, markdown_file: Path) -> ExtendedResultEnum:
        markdown_content: str = markdown_file.read_text()
        markdown_file_relative: str = markdown_file.relative_to(self.input_dir).as_posix()

        # Since we're only interested in links we can use the more secure 'js-default' flavor
        markdown_parser = MarkdownIt("js-default")

        file_results: list[ExtendedResultEnum] = [
            self._check_link(link=link, markdown_file_relative=markdown_file_relative)
            for link in self._get_links_from_tokens(markdown_parser.parse(markdown_content))
        ]

        final_result: ExtendedResultEnum = max(*file_results, ExtendedResultEnum.SUCCESS)

        if final_result == ExtendedResultEnum.SUCCESS:
            logger.success("Markdown file '{}' OK!", markdown_file_relative)
        elif final_result == ExtendedResultEnum.WARNING:
            logger.warning("Markdown file '{}' has warnings!", markdown_file_relative)
        else:
            logger.error("Markdown file '{}' has errors!", markdown_file_relative)
        return final_result

    def _get_links_from_tokens(self: Self, tokens: list[Token]) -> Iterator[str]:
        for token in tokens:
            if token.type == "image":
                yield str(token.attrGet("src"))
            elif token.type == "link_open":
                yield str(token.attrGet("href"))
            if token.children:
                yield from self._get_links_from_tokens(tokens=token.children)

    def run(self: Self) -> None:
        logger.info("============ Markdown Link Checker ============")
        logger.info("Starting files check in '{}'", str(self.input_dir))

        markdown_files: list[Path] = FileHelper.find_files_by_extension(directory=self.input_dir, extension="md", max_files=40)

        return_statuses: list[ExtendedResultEnum] = [self._check_markdown(markdown_file=markdown_file) for markdown_file in markdown_files]

        if return_statuses:
            self.return_status = max(*return_statuses, self.return_status)
        else:
            self.return_status = ExtendedResultEnum.SUCCESS

        self.gh_helper.finalize_action(
            action_result=ToolResult(
                tool_id=ToolIdentifierEnum.MARKDOWN_LINK_CHECK.tool_id,
                tool_name=ToolIdentifierEnum.MARKDOWN_LINK_CHECK.tool_name,
                extended_result=self.return_status,
                tool_ignore_warnings=self.ignore_warnings,
                tool_result_items=ToolSummaryTable(
                    extra_columns=["Reason"],
                    items=self.result_items,
                ),
            )
        )


def main() -> None:
    parser: configargparse.ArgumentParser = configargparse.ArgumentParser(
        prog="VoronDesign Markdown link Checker",
        description="This tool is used to check whether links within a markdown file are valid.",
    )
    parser.add_argument(
        "-i",
        "--input_dir",
        required=True,
        action="store",
        type=str,
        env_var="VORON_TOOLKIT_INPUT_DIR",
        help="Directory containing Mods to be checked",
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
    parser.add_argument(
        "-f",
        "--ignore_warnings",
        required=False,
        action="store_true",
        env_var=f"{ENV_VAR_PREFIX}_IGNORE_WARNINGS",
        help="Whether to return an error exit code if a warning was triggered",
        default=False,
    )
    args: configargparse.Namespace = parser.parse_args()
    MarkdownLinkChecker(args=args).run()


if __name__ == "__main__":
    main()
