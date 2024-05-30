"""OpenColorIO Wrapper.

Receive OpenColorIO information and store it in JSON format for processed
that don't have access to OpenColorIO or their version of OpenColorIO is
not compatible.
"""

import json
from pathlib import Path

import click

from ayon_core.pipeline.colorspace import (
    has_compatible_ocio_package,
    get_display_view_colorspace_name,
    get_config_file_rules_colorspace_from_filepath,
    get_config_version_data,
    get_ocio_config_views,
    get_ocio_config_colorspaces,
)


def _save_output_to_json_file(output, output_path):
    json_path = Path(output_path)
    with open(json_path, "w") as stream:
        json.dump(output, stream)

    print(f"Data are saved to '{json_path}'")


@click.group()
def main():
    pass  # noqa: WPS100


@main.command(
    name="get_ocio_config_colorspaces",
    help="return all colorspaces from config file")
@click.option(
    "--config_path",
    required=True,
    help="OCIO config path to read ocio config file.",
    type=click.Path(exists=True))
@click.option(
    "--output_path",
    required=True,
    help="path where to write output json file",
    type=click.Path())
def _get_ocio_config_colorspaces(config_path, output_path):
    """Aggregate all colorspace to file.

    Args:
        config_path (str): config file path string
        output_path (str): temp json file path string

    Example of use:
    > pyton.exe ./ocio_wrapper.py config get_colorspace
        --config_path <path> --output_path <path>
    """
    _save_output_to_json_file(
        get_ocio_config_colorspaces(config_path),
        output_path
    )


@main.command(
    name="get_ocio_config_views",
    help="All viewers from config file")
@click.option(
    "--config_path",
    required=True,
    help="OCIO config path to read ocio config file.",
    type=click.Path(exists=True))
@click.option(
    "--output_path",
    required=True,
    help="path where to write output json file",
    type=click.Path())
def _get_ocio_config_views(config_path, output_path):
    """Aggregate all viewers to file.

    Args:
        config_path (str): config file path string
        output_path (str): temp json file path string

    Example of use:
    > pyton.exe ./ocio_wrapper.py config get_views \
        --config_path <path> --output <path>
    """
    _save_output_to_json_file(
        get_ocio_config_views(config_path),
        output_path
    )


@main.command(
    name="get_config_version_data",
    help="Get major and minor version from config file")
@click.option(
    "--config_path",
    required=True,
    help="OCIO config path to read ocio config file.",
    type=click.Path(exists=True))
@click.option(
    "--output_path",
    required=True,
    help="path where to write output json file",
    type=click.Path())
def _get_config_version_data(config_path, output_path):
    """Get version of config.

    Args:
        config_path (str): ocio config file path string
        output_path (str): temp json file path string

    Example of use:
    > pyton.exe ./ocio_wrapper.py config get_version \
        --config_path <path> --output_path <path>
    """
    _save_output_to_json_file(
        get_config_version_data(config_path),
        output_path
    )


@main.command(
    name="get_config_file_rules_colorspace_from_filepath",
    help="Colorspace file rules from filepath")
@click.option(
    "--config_path",
    required=True,
    help="OCIO config path to read ocio config file.",
    type=click.Path(exists=True))
@click.option(
    "--filepath",
    required=True,
    help="Path to file to get colorspace from.",
    type=click.Path())
@click.option(
    "--output_path",
    required=True,
    help="Path where to write output json file.",
    type=click.Path())
def _get_config_file_rules_colorspace_from_filepath(
    config_path, filepath, output_path
):
    """Get colorspace from file path wrapper.

    Args:
        config_path (str): config file path string
        filepath (str): path string leading to file
        output_path (str): temp json file path string

    Example of use:
    > python.exe ./ocio_wrapper.py \
        colorspace get_config_file_rules_colorspace_from_filepath \
        --config_path <path> --filepath <path> --output_path <path>
    """
    _save_output_to_json_file(
        get_config_file_rules_colorspace_from_filepath(config_path, filepath),
        output_path
    )


@main.command(
    name="get_display_view_colorspace_name",
    help=(
        "Default view colorspace name for the given display and view"
    ))
@click.option(
    "--config_path",
    required=True,
    help="path where to read ocio config file",
    type=click.Path(exists=True))
@click.option(
    "--display",
    required=True,
    help="Display name",
    type=click.STRING)
@click.option(
    "--view",
    required=True,
    help="view name",
    type=click.STRING)
@click.option(
    "--output_path",
    required=True,
    help="path where to write output json file",
    type=click.Path())
def _get_display_view_colorspace_name(
    config_path, display, view, output_path
):
    """Aggregate view colorspace name to file.

    Wrapper command for processes without access to OpenColorIO

    Args:
        config_path (str): config file path string
        output_path (str): temp json file path string
        display (str): display name e.g. "ACES"
        view (str): view name e.g. "sRGB"

    Example of use:
    > pyton.exe ./ocio_wrapper.py config \
        get_display_view_colorspace_name --config_path <path> \
        --output_path <path> --display <display> --view <view>
    """
    _save_output_to_json_file(
        get_display_view_colorspace_name(config_path, display, view),
        output_path
    )


if __name__ == "__main__":
    if not has_compatible_ocio_package():
        raise RuntimeError("OpenColorIO is not available.")
    main()
