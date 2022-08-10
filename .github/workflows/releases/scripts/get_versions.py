import argparse
import enum
import json
import logging
import re
from pathlib import Path
from typing import Tuple

import yaml

from common import (
    get_github_access_token,
    get_github_generated_release_notes,
    get_github_repository_latest_release,
)

OPTION_SET_VERSION_AUTOMATICALLY = 'auto'
BREAKING_CHANGES_LABEL_PATTERN = 'breaking-changes'

# https://semver.org/#is-there-a-suggested-regular-expression-regex-to-check-a-semver-string
# The suggested pattern was prepended with 'v?' to match versions with syntax 'v1.2.3'
SEMANTIC_VERSIONING_PATTERN = '^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'

logger = logging.getLogger(__name__)


class VersionIncrementType(enum.Enum):
    MAJOR = enum.auto()
    MINOR = enum.auto()
    PATCH = enum.auto()


def load_github_release_notes_configuration(github_release_notes_config: Path):
    """Loads the release.yml file storing GitHub Release Notes generator
    configuration."""

    with open(github_release_notes_config) as file_object:
        return yaml.safe_load(file_object)


def get_release_notes_section_heading(release_notes_config: dict, label_pattern: str) -> str:
    if 'changelog' in release_notes_config and 'categories' in release_notes_config['changelog']:
        release_notes_config_categories = release_notes_config['changelog']['categories']
        assert isinstance(release_notes_config_categories, list)

        for category_definition in release_notes_config_categories:
            if 'labels' in category_definition and 'title' in category_definition:
                for label_name in category_definition['labels']:
                    if re.match(label_pattern, label_name):
                        section_heading = category_definition['title']
                        logger.info(
                            f"Label '{label_name}' matched using pattern '{label_pattern}' in section '{section_heading}'."
                        )
                        return section_heading

    raise Exception(f"Label '{label_name}' in release config file could not be found.")


def is_pattern_in_release_notes(pattern: str, generated_release_notes: str) -> bool:
    lines = generated_release_notes.split('\n')
    for line in lines:
        if re.match(pattern, line):
            return True
    return False


# Version incrementation type classifiers


def is_major_increment_required() -> bool:
    # Currently, major version updates have to be done manually.
    return False


def is_minor_increment_required(release_notes_config: dict, generated_release_notes: str) -> bool:
    breaking_changes_section_heading_text = get_release_notes_section_heading(
        release_notes_config=release_notes_config,
        label_pattern=BREAKING_CHANGES_LABEL_PATTERN,
    )
    breaking_changes_section_heading_pattern = f"## {breaking_changes_section_heading_text}"

    return is_pattern_in_release_notes(
        pattern=breaking_changes_section_heading_pattern,
        generated_release_notes=generated_release_notes,
    )


def is_patch_increment_required():
    # Catch-all for all kinds of changes.
    return True


def get_version_increment_type(
    github_access_token: str,
    github_release_config: Path,
    target_version: str,
    previous_version: str,
    source_branch: str,
) -> VersionIncrementType:
    release_notes_config = load_github_release_notes_configuration(
        github_release_notes_config=github_release_config,
    )

    generated_release_notes = get_github_generated_release_notes(
        github_access_token=github_access_token,
        target_version=target_version,
        previous_version=previous_version,
        source_branch=source_branch,
    )

    if generated_release_notes:
        if is_major_increment_required():
            return VersionIncrementType.MAJOR
        elif is_minor_increment_required(
            release_notes_config=release_notes_config,
            generated_release_notes=generated_release_notes,
        ):
            return VersionIncrementType.MINOR
        else:
            return VersionIncrementType.PATCH
    else:
        raise Exception(
            "Release Notes could not be generated. Is the Access Token and diff range valid?"
        )


def is_valid_version_string(version: str) -> bool:
    return re.search(SEMANTIC_VERSIONING_PATTERN, version) is not None


def increment_version(version: str, version_increment_type: VersionIncrementType) -> str:
    """Increments a given version string according to a provided
    incrementation type.

    This function does not persist prerelease and build metadata info
    in version strings between increments.
    """

    def explode_version_string(version: str):
        version_regex_search = re.search(SEMANTIC_VERSIONING_PATTERN, version)

        if version_regex_search is not None:
            return version_regex_search.groups()
        else:
            logger.error(f"Version '{version}' could not be matched and split into groups.")

    def reconstruct_version_string(
        major: int,
        minor: int,
        patch: int,
        prerelease: str = None,
        build_metadata: str = None,
    ):
        new_version_string = f"v{major}.{minor}.{patch}"

        if prerelease is not None:
            new_version_string += f"-{prerelease}"

        if build_metadata is not None:
            new_version_string += f"+{build_metadata}"

        return new_version_string

    cast_numeric_group_to_int_lambda = lambda g: int(g) if g is not None and g.isnumeric() else g
    version_string_groups = map(cast_numeric_group_to_int_lambda, explode_version_string(version))
    major, minor, patch, _, _ = version_string_groups

    if version_increment_type == VersionIncrementType.MAJOR:
        major, minor, patch = major + 1, 0, 0
    elif version_increment_type == VersionIncrementType.MINOR:
        major, minor, patch = major, minor + 1, 0
    elif version_increment_type == VersionIncrementType.PATCH:
        major, minor, patch = major, minor, patch + 1

    incremented_version = reconstruct_version_string(major, minor, patch)

    return incremented_version


def get_processed_versions(
    github_access_token: str,
    github_release_config: Path,
    target_version: str,
    previous_version: str,
    default_version: str,
    source_branch: str,
) -> Tuple[str, str]:
    """Processes versions given as input to the program.

    If previous version is set to 'auto', the script will ask the GitHub
    API about the latest release and use the tag name of that release
    as the value of the previous version.

    If target version is set to 'auto', the script will determine the
    increment type based on predefined conditions (certain labels applied
    to merged PRs) and increment the previous version to get the new
    target version automatically.
    """
    target_version = target_version.lower()
    previous_version = previous_version.lower()

    # Process the 'previous version' input setting.

    if previous_version == OPTION_SET_VERSION_AUTOMATICALLY:
        try:
            github_api_response_body = get_github_repository_latest_release(
                github_access_token=github_access_token
            )
            previous_version_processed = github_api_response_body['tag_name']
        except Exception as e:
            logger.error(e)
            previous_version_processed = ''
    else:
        # The previous version was specified by the user.
        previous_version_processed = previous_version

    # Process the 'target version' input setting.

    if target_version == OPTION_SET_VERSION_AUTOMATICALLY:
        if previous_version_processed:
            # Previous version was given, increment the version automatically.
            if not is_valid_version_string(previous_version_processed):
                raise Exception(
                    f"Previous version '{previous_version_processed}' is not a valid semantic version and could not be automatically incremented. "
                    "Set the target version with the -t/--target-version option."
                )

            version_increment_type = get_version_increment_type(
                github_access_token=github_access_token,
                github_release_config=github_release_config,
                target_version='__fake_tag_name_auto_versioning',
                previous_version=previous_version_processed,
                source_branch=source_branch,
            )

            target_version_processed = increment_version(
                version=previous_version_processed,
                version_increment_type=version_increment_type,
            )
        else:
            # The previous version was not given. Assume that it is the
            # initial release being created (e.g. v1.0.0).
            target_version_processed = default_version
    else:
        # The target version was specified by the user.
        target_version_processed = target_version

    return (target_version_processed, previous_version_processed)


def main():
    parser = argparse.ArgumentParser(description="Get version increment type")
    parser.add_argument(
        '-c',
        '--config',
        type=Path,
        required=True,
        help="Path to GitHub Release Notes configuration file",
    )
    parser.add_argument(
        '-t',
        '--target-version',
        type=str,
        default=OPTION_SET_VERSION_AUTOMATICALLY,
        help="Version of the release being created",
    )
    parser.add_argument(
        '-p',
        '--previous-version',
        type=str,
        default=OPTION_SET_VERSION_AUTOMATICALLY,
        help="Previous version for comparing changes",
    )
    parser.add_argument(
        '-d',
        '--default-version',
        type=str,
        default='v1.0.0',
        help="Default version to use when it's the very first release being created",
    )
    parser.add_argument(
        '-s',
        '--source-branch',
        type=str,
        default="main",
        help="Branch from which the release will be created",
    )
    args = parser.parse_args()

    github_access_token = get_github_access_token()

    target_version_processed, previous_version_processed = get_processed_versions(
        github_access_token=github_access_token,
        github_release_config=args.config,
        target_version=args.target_version,
        previous_version=args.previous_version,
        default_version=args.default_version,
        source_branch=args.source_branch,
    )

    output = {
        'target_version': target_version_processed,
        'previous_version': previous_version_processed,
        'source_branch': args.source_branch,
    }

    print(json.dumps(output))


if __name__ == "__main__":
    main()
