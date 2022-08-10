"""Generate Release Notes

This script utilizes Crucible's YAML var files and the Release Notes
generator provided by GitHub in order to create customized Release Notes
combining output from both sources.

The CLI program requires the following input arguments:
- Path to the root directory of the Crucible repository/project
- Access Token to GitHub's API for auto-generating Release Notes from
  data about merged Pull Requests
- Target version of the new release that is being created
"""

import argparse
import logging
from pathlib import Path
from typing import Optional

import yaml

from common import get_github_access_token, get_github_generated_release_notes

FILE_CONTAINS_VARS = {
    'roles/get_image_hash/defaults/main.yml': ['ai_version'],
    'roles/validate_inventory/defaults/main.yml': ['supported_ocp_versions'],
}

FORMAT_STRINGS = {
    'details_section_heading': "What's Included",
    'openshift_heading': "OpenShift",
    'openshift_body': "This release provides support for the following versions of OpenShift Container Platform: {versions}.",
    'assisted_installer_heading': "Assisted Installer",
    'assisted_installer_body': "If enabled in the inventory, Crucible will deploy Assisted Installer version **{ai_version}**.",
}

logger = logging.getLogger(__name__)


def load_required_vars(root_dir: Path, files_to_vars: dict) -> dict:
    parsed_required_vars = {}

    for file_name, expected_vars in files_to_vars.items():
        file_path = root_dir.joinpath(file_name)
        with open(file_path) as file_obj:
            loaded_yaml_object = yaml.safe_load(file_obj)

            for var_name in expected_vars:
                if var_name in loaded_yaml_object:
                    parsed_required_vars[var_name] = loaded_yaml_object[var_name]
                else:
                    logger.warning(
                        f"Variable '{var_name}' could not be found in file '{file_path}'."
                    )

    return parsed_required_vars


def get_ai_version(parsed_required_vars: dict) -> Optional[str]:
    return parsed_required_vars.get('ai_version')


def get_supported_ocp_versions(parsed_required_vars: dict) -> Optional[list[str]]:
    return parsed_required_vars.get('supported_ocp_versions')


def generate_section_whats_included(parsed_required_vars: dict) -> str:
    """Generates section listing supported OCP versions and the version
    of Assisted Installer included in the release."""

    output_str = ""

    supported_ocp_versions = get_supported_ocp_versions(parsed_required_vars=parsed_required_vars)
    if isinstance(supported_ocp_versions, list):
        # List OCP versions in descending order
        supported_ocp_versions.reverse()
        supported_ocp_versions_in_bold = map(lambda v: f"**{v}**", supported_ocp_versions)
        versions = ", ".join(supported_ocp_versions_in_bold)
        output_str += "\n### " + FORMAT_STRINGS['openshift_heading'] + "\n"
        output_str += "\n" + FORMAT_STRINGS['openshift_body'].format(versions=versions) + "\n"

    ai_version = get_ai_version(parsed_required_vars=parsed_required_vars)
    if ai_version is not None:
        output_str += "\n### " + FORMAT_STRINGS['assisted_installer_heading'] + "\n"
        output_str += (
            "\n" + FORMAT_STRINGS['assisted_installer_body'].format(ai_version=ai_version) + "\n"
        )

    # Add heading if at least one of {ai_version, supported_ocp_versions} was added
    if output_str:
        output_str = f"## {FORMAT_STRINGS['details_section_heading']}\n" + output_str

    return output_str


def generate_release_notes():
    """Generates Release Notes by extending GitHub-generated Release Notes
    with Crucible-specific information."""
    parser = argparse.ArgumentParser(description="Generate Crucible Release Notes")
    parser.add_argument(
        '-r',
        '--root-directory',
        type=Path,
        required=True,
        help="Path to root directory of the Crucible repository",
    )
    # parser.add_argument('-gh', '--github-access-token', type=str, required=True, help="GitHub API Access Token")
    parser.add_argument(
        '-t',
        '--target-version',
        type=str,
        required=True,
        help="Version of the release being created",
    )
    parser.add_argument(
        '-p',
        '--previous-version',
        type=str,
        default=None,
        help="Previous version for comparing changes",
    )
    parser.add_argument(
        '-s',
        '--source-branch',
        type=str,
        default="main",
        help="Branch from which the release will be created",
    )
    args = parser.parse_args()

    parsed_required_vars = load_required_vars(
        root_dir=args.root_directory,
        files_to_vars=FILE_CONTAINS_VARS,
    )

    github_access_token = get_github_access_token()

    version_details_section = generate_section_whats_included(
        parsed_required_vars=parsed_required_vars
    )
    if version_details_section:
        print(version_details_section)

    github_generated_release_notes = get_github_generated_release_notes(
        github_access_token=github_access_token,
        target_version=args.target_version,
        previous_version=args.previous_version,
        source_branch=args.source_branch,
    )
    if github_generated_release_notes:
        print(github_generated_release_notes)


if __name__ == "__main__":
    generate_release_notes()
