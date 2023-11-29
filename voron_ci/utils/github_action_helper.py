import contextlib
import datetime
import logging
import os
import zipfile
from collections.abc import Generator
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from typing import Self

import requests
from git import Repo

STEP_SUMMARY_ENV_VAR = "GITHUB_STEP_SUMMARY"
OUTPUT_ENV_VAR = "GITHUB_OUTPUT"

logger = logging.getLogger(__name__)


class GithubActionHelper:
    @classmethod
    @contextlib.contextmanager
    def expandable_section(cls: type[Self], title: str, *, default_open: bool) -> Generator[None, None, None]:
        with Path(os.environ[STEP_SUMMARY_ENV_VAR]).open(mode="a") as gh_step_summary:
            try:
                gh_step_summary.write(f"<details{' open' if default_open else ''}>\n")
                gh_step_summary.write(f"<summary>{title}</summary>\n\n")
                gh_step_summary.flush()
                yield
            finally:
                gh_step_summary.write("</details>\n")

    @classmethod
    def _create_table_header(cls: type[Self], columns: list[str]) -> str:
        column_names = "| " + " | ".join(columns) + " |"
        dividers = "| " + " | ".join(["---"] * len(columns)) + " |"
        return f"{column_names}\n{dividers}"

    @classmethod
    def _create_markdown_table_rows(cls: type[Self], rows: list[tuple[str, ...]]) -> str:
        return "\n".join(["| " + " | ".join(row_elements) + " |" for row_elements in rows])

    @classmethod
    def create_markdown_table(cls: type[Self], preamble: str, columns: list[str], rows: list[tuple[str, ...]]) -> str:
        return "\n".join([preamble, GithubActionHelper._create_table_header(columns=columns), GithubActionHelper._create_markdown_table_rows(rows=rows)])

    @classmethod
    def print_summary_table(cls: type[Self], columns: list[str], rows: list[tuple[str, ...]]) -> None:
        with Path(os.environ[STEP_SUMMARY_ENV_VAR]).open(mode="a") as gh_step_summary:
            gh_step_summary.write(f"{GithubActionHelper._create_table_header(columns=columns)}\n{GithubActionHelper._create_markdown_table_rows(rows=rows)}\n")

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
    def write_output(cls: type[Self], output: dict[str, str]) -> None:
        with Path(os.environ[OUTPUT_ENV_VAR]).open(mode="a") as gh_output:
            for key, value in output.items():
                gh_output.write(f"{key}={value}\n")

    @classmethod
    def write_output_multiline(cls: type[Self], output: dict[str, list[str]]) -> None:
        with Path(os.environ[OUTPUT_ENV_VAR]).open(mode="a") as gh_output:
            for key, value in output.items():
                gh_output.write(f"{key}<<GH_EOF\n")
                for line in value:
                    gh_output.write(f"{line}\n")
                gh_output.write("GH_EOF\n")

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
