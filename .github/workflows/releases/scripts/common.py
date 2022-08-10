import json
import logging
import os
from typing import Optional

import requests

REPOSITORY_OWNER = 'mkochanowski'
REPOSITORY_NAME = 'crucible'

GITHUB_ACCESS_TOKEN_ENV_NAME = 'GITHUB_TOKEN'

logger = logging.getLogger(__name__)


def get_github_access_token(env_variable_name=GITHUB_ACCESS_TOKEN_ENV_NAME):
    github_access_token = os.getenv(env_variable_name)

    if github_access_token is None:
        raise Exception(
            "Github Access Token could not be found. "
            f"Are you sure '{env_variable_name}' environment variable is set?"
        )

    return github_access_token


def get_github_repository_latest_release(github_access_token: str) -> dict:
    """Fetches the latest release of a specified repository on GitHub."""

    headers = {
        'Accept': 'application/vnd.github+json',
        'Authorization': f"token {github_access_token}",
    }

    api_endpoint_url = (
        f'https://api.github.com/repos/{REPOSITORY_OWNER}/{REPOSITORY_NAME}/releases/latest'
    )
    response = requests.get(api_endpoint_url, headers=headers)

    if response.status_code == 200:
        response_data = response.json()

        if 'tag_name' in response_data:
            return response_data
        else:
            logger.error(f"GitHub API returned an invalid response. {response.raw}")
    else:
        logger.error(
            f"Latest release could not be obtained from GitHub's API. API returned status code {response.status_code}. {response.reason}"
        )

    raise Exception("Latest release could not be obtained from GitHub's API.")


def get_github_generated_release_notes(
    github_access_token: str,
    target_version: str,
    previous_version: Optional[str],
    source_branch: str,
) -> str:
    """Retrieves auto-generated Release Notes from GitHub's API."""

    payload = {
        'tag_name': target_version,
        'target_commitish': source_branch,
    }

    headers = {
        'Accept': 'application/vnd.github+json',
        'Authorization': f"token {github_access_token}",
    }

    if previous_version is not None:
        payload['previous_tag_name'] = previous_version

    api_endpoint_url = f'https://api.github.com/repos/{REPOSITORY_OWNER}/{REPOSITORY_NAME}/releases/generate-notes'
    response = requests.post(api_endpoint_url, data=json.dumps(payload), headers=headers)

    if response.status_code == 200:
        response_data = response.json()

        if 'body' in response_data:
            return response_data['body']
        else:
            logger.error(f"GitHub API returned an invalid response. {response.raw}")
    else:
        logger.error(
            f"Release Notes could not be obtained from GitHub's API. API returned status code {response.status_code}. {response.reason}"
        )

    raise Exception("Release Notes could not be obtained from GitHub's API.")
