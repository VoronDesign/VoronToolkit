import logging
import os
from http import HTTPStatus
from pathlib import Path
from typing import Self

import requests

STEP_SUMMARY_ENV_VAR = "GITHUB_STEP_SUMMARY"

logger = logging.getLogger(__name__)


class GithubActionHelper:
    @classmethod
    def create_table_header(cls: type[Self], columns: list[str]) -> str:
        column_names = "| " + " | ".join(columns) + " |"
        dividers = "| " + " | ".join(["---"] * len(columns)) + " |"
        return f"{column_names}\n{dividers}"

    @classmethod
    def create_markdown_table_rows(cls: type[Self], rows: list[tuple[str, ...]]) -> str:
        return "\n".join(["| " + " | ".join(row_elements) + " |\n" for row_elements in rows])

    @classmethod
    def print_summary_table(cls: type[Self], preamble: str, columns: list[str], rows: list[tuple[str, ...]]) -> None:
        with Path(os.environ[STEP_SUMMARY_ENV_VAR]).open(mode="w") as gh_step_summary:
            gh_step_summary.write(preamble)
            gh_step_summary.write(GithubActionHelper.create_table_header(columns=columns))
            gh_step_summary.write(GithubActionHelper.create_markdown_table_rows(rows=rows))

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
        pass
