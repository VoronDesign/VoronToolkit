import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Self

import configargparse
from loguru import logger

from voron_toolkit.constants import (
    LABEL_CI_ISSUES_FOUND,
    LABEL_CI_PASSED,
    LABEL_READY_FOR_CI,
    LABELS_CI_ALL,
    ExtendedResultEnum,
    ItemResult,
    PrAction,
    StatusCheck,
    ToolIdentifierEnum,
    ToolResult,
    ToolSummaryTable,
)
from voron_toolkit.utils.github_action_helper import GithubActionHelper
from voron_toolkit.utils.logging import init_logging

ENV_VAR_PREFIX = "PR_HELPER"

PREAMBLE = """ Hi, thank you for submitting your PR.
Please find below the results of the automated PR checker:

"""

CLOSING_BOT_NOTICE = """

I am a 🤖, this comment was generated automatically!

*Made with ❤️ by the VoronDesign GitHub Team*
"""


class PrHelper:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.artifact_name: str = args.artifact_name
        self.workflow_run_id: str = args.workflow_run_id
        self.github_repository: str = args.github_repository
        self.tmp_path: Path = Path()
        self.tool_results: dict[ToolIdentifierEnum, ToolResult] = {}

        init_logging(verbose=args.verbose)

    def _generate_pr_comment(self: Self) -> str:
        self.items_by_result: defaultdict[ExtendedResultEnum, dict[ToolIdentifierEnum, list[ItemResult]]] = defaultdict(dict)
        comment_body = PREAMBLE

        if ToolIdentifierEnum.README_GENERATOR in self.tool_results:
            comment_body += "### Added/Changed mods detected in this PR:\n\n"
            comment_body += self.tool_results[ToolIdentifierEnum.README_GENERATOR].tool_result_items.to_markdown()
            comment_body += "\n---\n\n"

        comment_body += "### Tool check results overview:\n\n"
        comment_body += self._tool_overview()
        comment_body += "\n---\n\n"

        comment_body += "### Tool check results details:\n\n"
        for extended_result in ExtendedResultEnum:
            comment_body += self._result_details_for_extended_result(extended_result=extended_result)

        comment_body += "\n---\n\n"
        comment_body += CLOSING_BOT_NOTICE
        return comment_body

    def _tool_overview(self: Self) -> str:
        tool_overview: str = ""
        self.overview_table_contents: list[list[str]] = []

        for tool_identifier, tool_result in self.tool_results.items():
            self.overview_table_contents.append(
                [
                    tool_identifier.tool_name,
                    *[
                        str(len(tool_result.tool_result_items.items[extended_result]))
                        # Leave the cell blank if the result is 0
                        if len(tool_result.tool_result_items.items[extended_result]) > 0
                        else " "
                        for extended_result in ExtendedResultEnum
                    ],
                ]
            )

        tool_overview += ToolSummaryTable.create_markdown_table(
            columns=["Tool", *[enum_item.icon for enum_item in ExtendedResultEnum]], rows=self.overview_table_contents
        )
        return tool_overview

    def _result_details_for_extended_result(self: Self, extended_result: ExtendedResultEnum) -> str:
        # Determine whether the result has any items, if not, we can skip it
        extended_result_has_items: bool = False

        result_details = ""
        # Expand the lists (except the SUCCESS one)
        if extended_result != ExtendedResultEnum.SUCCESS:
            result_details += "<details open>\n"
        else:
            result_details += "<details>\n"
        result_details += f"<summary>{extended_result.name}: {extended_result.icon}</summary>\n\n"

        for pr_step_identifier in self.tool_results:
            if not self.tool_results[pr_step_identifier]:
                continue
            filtered_markdown_table = self.tool_results[pr_step_identifier].tool_result_items.to_markdown(filter_result=extended_result)
            if not filtered_markdown_table:
                continue
            # If we reached here, we have contents in the table, so we set the flag
            extended_result_has_items = True
            result_details += f"#### {pr_step_identifier.tool_name}\n\n"
            result_details += filtered_markdown_table
            result_details += "\n---\n\n"
        result_details += "\n</details>\n"
        return result_details if extended_result_has_items else ""

    def _parse_artifact_and_get_labels(self: Self) -> None:
        logger.info("Parsing Artifact ...")

        for directory in [item for item in self.tmp_path.iterdir() if item.is_dir()]:
            try:
                pr_step_identifier = ToolIdentifierEnum[directory.name.upper()]
            except ValueError:
                logger.warning("Skipping unknown directory {}", directory.name)
                continue
            if not (Path(directory, "tool_result.json").exists()):
                logger.warning(
                    "Section '{}' is incomplete in artifact! json: {}",
                    pr_step_identifier,
                    Path(directory, "tool_result.json").exists(),
                )
                continue
            ci_step_result = ToolResult.from_json(Path(directory, "tool_result.json").read_text())
            logger.success(
                "Parsed result for tool {}: Result: {}, Ignore Warnings: {}",
                pr_step_identifier,
                ci_step_result.extended_result,
                ci_step_result.tool_ignore_warnings,
            )
            self.tool_results[pr_step_identifier] = ci_step_result

    def _update_labels_on_pull_request(self: Self, pr_number: int) -> None:
        label: str = LABEL_CI_PASSED
        for ci_step_result in self.tool_results.values():
            result_ok = ExtendedResultEnum.WARNING if ci_step_result.tool_ignore_warnings else ExtendedResultEnum.SUCCESS
            if ci_step_result.extended_result > result_ok:
                label = LABEL_CI_ISSUES_FOUND
        if label == LABEL_CI_PASSED:
            logger.success("All CI checks executed without errors!")

        labels_on_pr: list[str] = GithubActionHelper.get_labels_on_pull_request(
            repo=self.github_repository,
            pull_request_number=pr_number,
        )
        labels_to_preserve: list[str] = [label for label in labels_on_pr if label not in LABELS_CI_ALL]

        updated_labels: list[str] = [label, *labels_to_preserve]
        logger.info("Labels: {}", updated_labels)
        GithubActionHelper.set_labels_on_pull_request(
            repo=self.github_repository,
            pull_request_number=pr_number,
            labels=updated_labels,
        )

    def _update_pr_comment(self: Self, pr_number: int) -> None:
        pr_comment: str = self._generate_pr_comment()
        GithubActionHelper.update_or_create_pr_comment(
            repo=self.github_repository,
            pull_request_number=pr_number,
            comment_body=pr_comment,
        )

    def _update_status_checks(self: Self, commit_sha: str) -> None:
        failed: bool = False
        for ci_step_result in self.tool_results.values():
            result_ok = ExtendedResultEnum.WARNING if ci_step_result.tool_ignore_warnings else ExtendedResultEnum.SUCCESS
            if ci_step_result.extended_result > result_ok:
                failed = True
                GithubActionHelper.set_commit_status(
                    repo=self.github_repository,
                    commit_sha=commit_sha,
                    status=StatusCheck(
                        status="failure",
                        description=f"{ci_step_result.tool_name} found issues!",
                        context=f"VoronCI/{ci_step_result.tool_id}",
                    ),
                )
            else:
                GithubActionHelper.set_commit_status(
                    repo=self.github_repository,
                    commit_sha=commit_sha,
                    status=StatusCheck(
                        status="success",
                        description=f"{ci_step_result.tool_name} found no issues!",
                        context=f"VoronCI/{ci_step_result.tool_id}",
                    ),
                )
        if failed:
            GithubActionHelper.set_commit_status(
                repo=self.github_repository,
                commit_sha=commit_sha,
                status=StatusCheck(
                    status="failure",
                    description="Issues found, please check the PR comment!",
                    context="VoronCI/run",
                ),
            )
        else:
            GithubActionHelper.set_commit_status(
                repo=self.github_repository,
                commit_sha=commit_sha,
                status=StatusCheck(
                    status="success",
                    description="No issues found by CI!",
                    context="VoronCI/run",
                ),
            )

    def _post_process_pr(self: Self, pr_number: int, pr_action: str, commit_sha: str) -> None:
        logger.info("Post Processing PR #{}, action: {}", pr_number, pr_action)
        self._parse_artifact_and_get_labels()

        self._update_pr_comment(pr_number=pr_number)
        self._update_labels_on_pull_request(pr_number=pr_number)
        self._update_status_checks(commit_sha=commit_sha)

    def _dismiss_labels(self: Self, pr_number: int, commit_sha: str) -> None:
        logger.info("PR #{} has new changes. Dismissing all CI labels!", pr_number)
        GithubActionHelper.set_labels_on_pull_request(
            repo=self.github_repository,
            pull_request_number=pr_number,
            labels=[
                label
                for label in GithubActionHelper.get_labels_on_pull_request(
                    repo=self.github_repository,
                    pull_request_number=pr_number,
                )
                if label not in LABELS_CI_ALL
            ],
        )
        GithubActionHelper.set_commit_status(
            repo=self.github_repository,
            commit_sha=commit_sha,
            status=StatusCheck(
                status="pending",
                description="Please run the Voron PR CI to get the CI results!",
                context="VoronCI/run",
            ),
        )

    def run(self: Self) -> None:
        logger.info("Downloading artifact '{}' from workflow '{}'", self.artifact_name, self.workflow_run_id)
        with tempfile.TemporaryDirectory() as tmpdir:
            logger.info("Created temporary directory '{}'", tmpdir)
            self.tmp_path = Path(tmpdir)

            GithubActionHelper.download_artifact(
                repo=self.github_repository,
                workflow_run_id=self.workflow_run_id,
                artifact_name=self.artifact_name,
                target_directory=self.tmp_path,
            )

            # Check if the artifact directory is empty, this might happen when the parent workflow did not execute any checks
            if not any(self.tmp_path.iterdir()):
                logger.warning(
                    "Result folder {} for run_id {} is empty! This may be due to a missing artifact!",
                    self.artifact_name,
                    self.workflow_run_id,
                )
                return

            try:
                event_payload: dict[str, Any] = json.loads(Path(self.tmp_path, "event.json").read_text())
                pr_number: int = int(event_payload["pull_request"]["number"])
                pr_action: str = event_payload["action"]
                pr_labels: list[str] = [label["name"] for label in event_payload["pull_request"]["labels"]]
                pr_commit_sha: str = event_payload["pull_request"]["head"]["sha"]
            except (FileNotFoundError, KeyError) as e:
                logger.error("Failed to parse event.json: {}", e)
                return

            if LABEL_READY_FOR_CI in pr_labels and pr_action == PrAction.labeled:
                self._post_process_pr(pr_number=pr_number, pr_action=pr_action, commit_sha=pr_commit_sha)
            elif pr_action != PrAction.labeled:
                self._dismiss_labels(pr_number=pr_number, commit_sha=pr_commit_sha)
            else:
                logger.info("Skipping post processing of PR #{}!", pr_number)
                GithubActionHelper.set_commit_status(
                    repo=self.github_repository,
                    commit_sha=pr_commit_sha,
                    status=StatusCheck(
                        status="pending",
                        description="Please run the Voron PR CI to get the CI results!",
                        context="VoronCI/run",
                    ),
                )


def main() -> None:
    parser: configargparse.ArgumentParser = configargparse.ArgumentParser(
        prog="VoronDesign PR Preparer",
        description="This tool updates the PR comment and attaches labels for a VoronDesign PR",
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
        "-g",
        "--github_repository",
        required=False,
        action="store",
        type=str,
        env_var=f"{ENV_VAR_PREFIX}_GITHUB_REPOSITORY",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="Repository from which to download the artifact",
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
    PrHelper(args=args).run()


if __name__ == "__main__":
    main()
