import os
import sys
import tempfile
from pathlib import Path
from typing import Self

import configargparse
from loguru import logger

from voron_ci.constants import SUCCESS_LABEL, VORONUSERS_PR_COMMENT_SECTIONS, StepResult
from voron_ci.utils.github_action_helper import GithubActionHelper
from voron_ci.utils.logging import init_logging

ENV_VAR_PREFIX = "PR_HELPER"

PREAMBLE = """ Hi, thank you for submitting your PR.
Please find below the results of the automated PR checker:

"""

CLOSING_SUCCESS = """

Congratulations, all checks have completed successfully! Your PR is now ready for review!

"""

CLOSING_FAILURE = """

Unfortunately, some checks have failed. Please fix the issues and update your PR.

"""

CLOSING_BOT_NOTICE = """

I am a 🤖, this comment was generated automatically!

"""


class PrHelper:
    def __init__(self: Self, args: configargparse.Namespace) -> None:
        self.artifact_name: str = args.artifact_name
        self.workflow_run_id: str = args.workflow_run_id
        self.github_repository: str = args.github_repository
        self.tmp_path: Path = Path()

        self.pr_number: int = -1
        self.summaries: str = ""
        self.labels: list[str] = []

        init_logging(verbose=args.verbose)

    def _parse_artifact(self: Self) -> None:
        logger.info("Preparing PR comment ...")
        if not Path(self.tmp_path, "pr_number.txt").exists():
            logger.error("Artifact is missing pr_number.txt file!")
            sys.exit(255)
        self.pr_number = int(Path(self.tmp_path, "pr_number.txt").read_text())
        for pr_step_identifier in VORONUSERS_PR_COMMENT_SECTIONS:
            if not (
                Path(self.tmp_path, pr_step_identifier.step_id, "summary.md").exists()
                and Path(self.tmp_path, pr_step_identifier.step_id, "outcome.txt").exists()
            ):
                logger.warning(
                    "Section '{}' is missing or incomplete in artifact! folder: {}, summary: {}, outcome: {}",
                    pr_step_identifier,
                    Path(self.tmp_path, pr_step_identifier.step_id).exists(),
                    Path(self.tmp_path, pr_step_identifier.step_id, "summary.md").exists(),
                    Path(self.tmp_path, pr_step_identifier.step_id, "outcome.txt").exists(),
                )
                continue
            self.summaries += Path(self.tmp_path, pr_step_identifier.step_id, "summary.md").read_text()
            self.summaries += "\n\n"
            outcome: StepResult = StepResult[Path(self.tmp_path, pr_step_identifier.step_id, "outcome.txt").read_text()]
            if outcome > StepResult.SUCCESS:
                self.labels.append(pr_step_identifier.step_pr_label)
        if not self.labels:
            self.labels.append(SUCCESS_LABEL)

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

            self._parse_artifact()
            if self.pr_number > 0:
                GithubActionHelper.set_labels_on_pull_request(repo=self.github_repository, pull_request_number=self.pr_number, labels=self.labels)
                GithubActionHelper.update_or_create_pr_comment(repo=self.github_repository, pull_request_number=self.pr_number, comment_body=self.summaries)


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
        env_var=f"{ENV_VAR_PREFIX}_VERBOSE",
        help="Print debug output to stdout",
        default=False,
    )
    args: configargparse.Namespace = parser.parse_args()
    PrHelper(args=args).run()


if __name__ == "__main__":
    main()
