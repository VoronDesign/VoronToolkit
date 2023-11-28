import os


def print_container_info() -> None:
    print("## Debugging environment variables:\n")
    print(f'\tGITHUB_OUTPUT={os.environ.get("GITHUB_OUTPUT", "")}')
    print(f'\tGITHUB_STEP_SUMMARY={os.environ.get("GITHUB_STEP_SUMMARY", "")}')
    print(f'\tGITHUB_REF={os.environ.get("GITHUB_REF", "")}')
    print(f'\tGITHUB_REPOSITORY={os.environ.get("GITHUB_REPOSITORY", "")}')
    print(f'\tGITHUB_TOKEN={os.environ.get("GITHUB_TOKEN", "")}')