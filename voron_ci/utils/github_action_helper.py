import datetime
import os
import sys
import zipfile
from dataclasses import dataclass
from io import BytesIO, StringIO
from pathlib import Path
from typing import Self

import requests
from git import InvalidGitRepositoryError, NoSuchPathError, Repo
from githubkit import GitHub, Response
from loguru import logger

from voron_ci.constants import PR_COMMENT_TAG, StepResult
from voron_ci.utils.action_summary import ActionSummary

STEP_SUMMARY_ENV_VAR = "GITHUB_STEP_SUMMARY"
OUTPUT_ENV_VAR = "GITHUB_OUTPUT"
VORON_CI_OUTPUT_ENV_VAR = "VORON_CI_OUTPUT"
VORON_CI_STEP_SUMMARY_ENV_VAR = "VORON_CI_STEP_SUMMARY"
VORON_CI_GITHUB_TOKEN_ENV_VAR = "VORON_CI_GITHUB_TOKEN"  # noqa: S105


@dataclass
class ActionResult:
    action_id: str
    action_name: str
    outcome: StepResult
    summary: ActionSummary


class GithubActionHelper:
    def __init__(self: Self, *, ignore_warnings: bool = False) -> None:
        output_path_var: str | None = os.environ.get(VORON_CI_OUTPUT_ENV_VAR, None)
        github_step_summary: str | None = os.environ.get(VORON_CI_STEP_SUMMARY_ENV_VAR, "False")
        self.output_path: Path | None = Path(output_path_var) if output_path_var else None
        self.artifacts: dict[str, str | bytes] = {}
        self.github_output: StringIO = StringIO()
        self.do_gh_step_summary: bool = bool(github_step_summary)
        self.ignore_warnings: bool = ignore_warnings

    def set_output(self: Self, output: dict[str, str]) -> None:
        for key, value in output.items():
            self.github_output.write(f"{key}={value}\n")

    def set_output_multiline(self: Self, output: dict[str, list[str]]) -> None:
        for key, value in output.items():
            self.github_output.write(f"{key}<<GH_EOF\n")
            for line in value:
                self.github_output.write(f"{line}\n")
            self.github_output.write("GH_EOF\n")

    def set_artifact(self: Self, file_name: str, file_contents: str | bytes) -> None:
        self.artifacts[file_name] = file_contents

    def _write_outputs(self: Self) -> None:
        with Path(os.environ.get("GITHUB_OUTPUT", "/dev/null")).open("a") as gh_output:
            gh_output.write(self.github_output.getvalue())

    def write_outputs(self: Self) -> None:
        self._write_outputs()

    def _write_step_summary(self: Self, action_result: ActionResult) -> None:
        if self.do_gh_step_summary:
            with Path(os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null")).open("a") as gh_step_summary:
                gh_step_summary.write(action_result.summary.to_markdown())

    def _write_artifacts(self: Self, action_result: ActionResult) -> None:
        if self.output_path:
            Path.mkdir(Path(self.output_path, action_result.action_id), parents=True, exist_ok=True)
            for artifact_path, artifact_contents in self.artifacts.items():
                Path.mkdir(Path(self.output_path, action_result.action_id, artifact_path).parent, parents=True, exist_ok=True)
                with Path(self.output_path, action_result.action_id, artifact_path).open(mode="wb" if isinstance(artifact_contents, bytes) else "w") as f:
                    f.write(artifact_contents)
            with Path(self.output_path, action_result.action_id, "summary.md").open("w") as f:
                f.write(action_result.summary.to_markdown())
            with Path(self.output_path, action_result.action_id, "outcome.txt").open("w") as f:
                f.write(action_result.outcome.result_str)

    def finalize_action(self: Self, action_result: ActionResult) -> None:
        self._write_outputs()
        self._write_step_summary(action_result=action_result)
        self._write_artifacts(action_result=action_result)

        result_ok = StepResult.WARNING if self.ignore_warnings else StepResult.SUCCESS
        if action_result.outcome > result_ok:
            logger.error("Error detected while performing action '{}' (result: '{}' > '{}')!", action_result.action_name, action_result.outcome, result_ok)
            sys.exit(255)

    @classmethod
    def get_job_id(cls: type[Self], github_repository: str, github_run_id: str, job_name: str) -> str:
        github_api_url = f"https://api.github.com/repos/{github_repository}/actions/runs/{github_run_id}/jobs"

        headers = {
            "Authorization": f"token {os.environ['VORON_CI_GITHUB_TOKEN']}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            response = requests.get(github_api_url, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.HTTPError:
            logger.exception("Failed to retrieve jobs. Status code: {}", response.status_code)
            return ""

        data = response.json()
        matching_jobs = [job for job in data["jobs"] if job["name"] == job_name]

        if matching_jobs:
            job = matching_jobs[0]
            return job["id"]
        logger.warning("No job found with name '{}'", job_name)
        return ""

    @classmethod
    def last_commit_timestamp(cls: type[Self], file_or_directory: Path) -> str:
        try:
            # Open the Git repository
            repo = Repo(path=file_or_directory.as_posix(), search_parent_directories=True)

            # Iterate through the commits in reverse order
            for commit in repo.iter_commits(paths=file_or_directory, max_count=1):
                return commit.authored_datetime.astimezone(datetime.UTC).isoformat()

        except (InvalidGitRepositoryError, NoSuchPathError):
            logger.exception("An error occurred while querying last_changed timestamp for '{}'", file_or_directory.as_posix())
        return ""

    @classmethod
    def set_labels_on_pull_request(cls: type[Self], repo: str, pull_request_number: int, labels: list[str]) -> None:
        github = GitHub(os.environ["VORON_CI_GITHUB_TOKEN"])
        github.rest.issues.set_labels(owner=repo.split("/")[0], repo=repo.split("/")[1], issue_number=pull_request_number, labels=labels)

    @classmethod
    def download_artifact(cls: type[Self], repo: str, workflow_run_id: str, artifact_name: str, target_directory: Path) -> None:
        github: GitHub = GitHub(os.environ["VORON_CI_GITHUB_TOKEN"])
        response: Response = github.rest.actions.list_workflow_run_artifacts(owner=repo.split("/")[0], repo=repo.split("/")[1], run_id=int(workflow_run_id))

        artifacts: list[dict[str, str]] = response.json().get("artifacts", [])
        artifact_id: int = -1

        # Find the artifact by name
        for artifact in artifacts:
            if artifact["name"] == artifact_name:
                artifact_id = int(artifact["id"])
                break

        if artifact_id == -1:
            logger.error("Artifact '{}' not found in the workflow run {}", artifact_name, workflow_run_id)
            return

        # Download artifact zip file
        response_download: Response = github.rest.actions.download_artifact(
            owner=repo.split("/")[0], repo=repo.split("/")[1], artifact_id=artifact_id, archive_format="zip"
        )

        # Read the zip file content into memory
        zip_content: BytesIO = BytesIO(response_download.content)

        # Unzip artifact contents into target directory
        with zipfile.ZipFile(zip_content, "r") as zip_ref:
            # Create target directory if it doesn't exist
            target_path = Path(target_directory)
            target_path.mkdir(parents=True, exist_ok=True)

            # Extract files into the target directory
            zip_ref.extractall(target_path)

        logger.info("Artifact '{}' downloaded and extracted to '{}' successfully.", artifact_name, target_directory.as_posix())

    @classmethod
    def update_or_create_pr_comment(cls: type[Self], repo: str, pull_request_number: int, comment_body: str) -> None:
        github: GitHub = GitHub(os.environ["VORON_CI_GITHUB_TOKEN"])
        response: Response = github.rest.issues.list_comments(owner=repo.split("/")[0], repo=repo.split("/")[1], issue_number=pull_request_number)

        existing_comments: list[dict[str, str]] = response.json()
        comment_id: int = -1

        # Find the comment by the author
        for existing_comment in existing_comments:
            if PR_COMMENT_TAG in existing_comment["body"]:
                comment_id = int(existing_comment["id"])
                break

        full_comment = f"{comment_body}\n\n{PR_COMMENT_TAG}\n"

        if comment_id == -1:
            # Create a new comment
            github.rest.issues.create_comment(owner=repo.split("/")[0], repo=repo.split("/")[1], issue_number=pull_request_number, body=full_comment)
        else:
            # Update existing comment
            github.rest.issues.update_comment(owner=repo.split("/")[0], repo=repo.split("/")[1], comment_id=comment_id, body=full_comment)
