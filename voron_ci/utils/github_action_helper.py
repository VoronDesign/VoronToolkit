import datetime
import logging
import os
import sys
import zipfile
from dataclasses import dataclass
from http import HTTPStatus
from io import BytesIO, StringIO
from pathlib import Path
from typing import Self

import requests
from git import Repo

from voron_ci.constants import EXTENDED_OUTCOME, ReturnStatus
from voron_ci.utils.action_summary import ActionSummary

STEP_SUMMARY_ENV_VAR = "GITHUB_STEP_SUMMARY"
OUTPUT_ENV_VAR = "GITHUB_OUTPUT"

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    action_id: str
    action_name: str
    outcome: ReturnStatus
    summary: ActionSummary


class GithubActionHelper:
    def __init__(self: Self, *, output_path: Path | str | None = None, do_gh_step_summary: bool = False, ignore_warnings: bool = False) -> None:
        self.output_path: Path | None = Path(output_path) if output_path else None
        self.artifacts: dict[str, str | bytes] = {}
        self.github_output: StringIO = StringIO()
        self.do_gh_step_summary: bool = do_gh_step_summary
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
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as gh_output:
            gh_output.write(self.github_output.getvalue())

    def write_outputs(self: Self) -> None:
        self._write_outputs()

    def _write_step_summary(self: Self, action_result: ActionResult) -> None:
        if self.do_gh_step_summary:
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as gh_step_summary:
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
                f.write(str(action_result.outcome))

    def postprocess_action(self: Self, action_result: ActionResult) -> None:
        self.set_output(output={"extended-outcome": EXTENDED_OUTCOME[action_result.outcome]})
        self._write_outputs()
        self._write_step_summary(action_result=action_result)
        self._write_artifacts(action_result=action_result)

        result_ok = ReturnStatus.WARNING if self.ignore_warnings else ReturnStatus.SUCCESS
        if action_result.outcome > result_ok:
            logger.error("Error detected while performing action '%s' (result: '%s' > '%s')!", action_result.action_name, action_result.outcome, result_ok)
            sys.exit(255)

    @classmethod
    def get_job_id(cls: type[Self], github_repository: str, github_run_id: str, job_name: str) -> str:
        github_api_url = f"https://api.github.com/repos/{github_repository}/actions/runs/{github_run_id}/jobs"

        headers = {
            "Authorization": f"token {os.environ['INPUT_GITHUB_TOKEN']}",
            "Accept": "application/vnd.github.v3+json",
        }

        response = requests.get(github_api_url, headers=headers, timeout=10)

        if response.status_code < HTTPStatus.MULTIPLE_CHOICES:
            data = response.json()
            matching_jobs = [job for job in data["jobs"] if job["name"] == job_name]

            if matching_jobs:
                job = matching_jobs[0]
                return job["id"]
            logger.warning("No job found with name '%s'", job_name)
            return ""
        logger.warning("Failed to retrieve jobs. Status code: %d", response.status_code)
        return ""

    @classmethod
    def last_commit_timestamp(cls: type[Self], file_or_directory: Path) -> str:
        try:
            # Open the Git repository
            repo = Repo(path=file_or_directory.as_posix(), search_parent_directories=True)

            # Iterate through the commits in reverse order
            for commit in repo.iter_commits(paths=file_or_directory, max_count=1):
                return commit.authored_datetime.astimezone(datetime.UTC).isoformat()

        except Exception:
            logger.exception("An error occurred while querying last_changed timestamp for '%s'", file_or_directory.as_posix())
        return ""

    @classmethod
    def download_artifact(cls: type[Self], repo: str, workflow_run_id: str, artifact_name: str, target_directory: Path) -> None:
        # GitHub API endpoint to get the artifact information
        api_url = f"https://api.github.com/repos/{repo}/actions/runs/{workflow_run_id}/artifacts"

        # Make a GET request to fetch artifact details
        response = requests.get(api_url, timeout=20)
        if response.status_code >= HTTPStatus.MULTIPLE_CHOICES:
            logger.error("Failed to fetch artifacts. Status code: %d", response.status_code)
            return

        artifacts = response.json().get("artifacts", [])
        artifact_id = None

        # Find the artifact by name
        for artifact in artifacts:
            if artifact["name"] == artifact_name:
                artifact_id = artifact["id"]
                break

        if artifact_id is None:
            logger.error("Artifact '%s' not found in the workflow run %s", artifact_name, workflow_run_id)
            return

        # Download artifact zip file
        download_url = f"https://api.github.com/repos/{repo}/actions/artifacts/{artifact_id}/zip"
        headers = {"Accept": "application/vnd.github.v3+json"}
        download_response = requests.get(download_url, headers=headers, timeout=20)

        if download_response.status_code >= HTTPStatus.MULTIPLE_CHOICES:
            logger.error("Failed to download artifact '%s'. Status code: %d", artifact_name, download_response.status_code)
            return

        # Read the zip file content into memory
        zip_content = BytesIO(download_response.content)

        # Unzip artifact contents into target directory
        with zipfile.ZipFile(zip_content, "r") as zip_ref:
            # Create target directory if it doesn't exist
            target_path = Path(target_directory)
            target_path.mkdir(parents=True, exist_ok=True)

            # Extract files into the target directory
            zip_ref.extractall(target_path)

        logger.info("Artifact '%s' downloaded and extracted to '%s' successfully.", artifact_name, target_directory.as_posix())

    @classmethod
    def set_labels_on_pull_request(cls: type[Self], repo: str, pull_request_number: int, labels: list[str]) -> None:
        api_url: str = f"https://api.github.com/repos/{repo}/issues/{pull_request_number}/labels"
        headers: dict[str, str] = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {os.environ['INPUT_GITHUB_TOKEN']}",
        }
        try:
            response: requests.Response = requests.put(api_url, headers=headers, json={"labels": labels}, timeout=10)
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            logger.exception("Failed to set labels on pull request %d", pull_request_number)
        except Exception:
            logger.exception("Failed to set labels on pull request %d", pull_request_number)

    @classmethod
    def sanitize_file_list(cls: type[Self]) -> None:
        file_list: list[str] = os.environ.get("FILE_LIST_SANITIZE_INPUT", "").splitlines()
        output_file_list: list[str] = [input_file.replace("[", "\\[").replace("]", "\\]") for input_file in file_list]
        gh_helper: GithubActionHelper = GithubActionHelper()
        gh_helper.set_output_multiline(output={"FILE_LIST_SANITIZE_OUTPUT": output_file_list})
        gh_helper.write_outputs()
