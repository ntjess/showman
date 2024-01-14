import os
import logging
import shutil
import typing as t
from pathlib import Path
import sys

import tomli
from packaging.version import InvalidVersion
from packaging.version import Version as PkgVersion

from showman.common import FilePath

# See https://github.com/typst/packages?tab=readme-ov-file#local-packages for path specs
if sys.platform == "win32":
    TYPST_DATA_DIR = os.environ["APPDATA"]
elif sys.platform == "darwin":
    TYPST_DATA_DIR = os.path.expanduser("~/Library/Application Support")
else:
    TYPST_DATA_DIR = os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
TYPST_LOCAL_PACKAGES_DIR = Path(TYPST_DATA_DIR) / "typst" / "packages"


def _parse_toml(toml_file: FilePath):
    toml_file = Path(toml_file).resolve()
    with open(toml_file, "rb") as ifile:
        toml_text = tomli.load(ifile)  # type: ignore
    version = toml_text["package"]["version"]
    package_name = toml_text["package"]["name"]
    package_paths = toml_text.get("tool", {}).get("packager", {}).get("paths", None)
    if package_paths is None:
        raise ValueError(
            "No package files specified in typst.toml (tool.packager.paths)"
        )
    if not isinstance(package_paths, list):
        raise TypeError(f"Expected list of paths in typst.toml, got {package_paths}")
    try:
        PkgVersion(version)
    except InvalidVersion:
        raise ValueError(f"{version} is not a valid version")

    return version, package_name, package_paths


def _copy_entry(
    entry: FilePath | dict[str, str],
    source_folder: Path,
    dest_folder: Path,
    symlink=False,
):
    if isinstance(entry, str):
        source = source_folder.joinpath(entry)
        dest = dest_folder.joinpath(entry)
    elif isinstance(entry, dict):
        source = source_folder.joinpath(entry["from"])
        dest = dest_folder.joinpath(entry["to"])
    else:
        msg = f"Invalid entry: {entry}, must be str or dict(from=..., to=...))"
        raise TypeError(msg)
    if not source.exists():
        raise FileNotFoundError(f"{source} does not exist")
    if symlink:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(source, target_is_directory=source.is_dir())
    elif source.is_dir():
        shutil.copytree(source, dest, dirs_exist_ok=True)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, dest)


def create_package(
    toml_file: FilePath,
    typst_packages_folder: FilePath | None = None,
    package_paths: list[str | FilePath | dict[str, str]] | None = None,
    namespace="local",
    overwrite=False,
    symlink=False,
):
    """
    Create a package from a typst.toml file.

    Parameters
    ----------
    toml_file:
        The path to the typst.toml file.
    typst_packages_folder:
        The path to the folder where packages will be stored. This can either be a local
        typst folder or a git clone of the packages repo. The latter is useful when
        publishing your package to the official registry. See
        "https://github.com/typst/packages/?tab=readme-ov-file#local-packages" for which
        path is read by typst depending on your system. If ``None``, Typst's local
        package folder will be used unless the ``TYPST_PACKAGES_FOLDER`` environment
        variable is set.
    package_paths:
        The paths to the files and folders to include in the package. If None,
        then the paths in the `paths` key of the `packager` table in the
        typst.toml file will be used.
    namespace:
        The namespace of the package. Can be set to "preview" when ready to publish
    overwrite:
        Whether to overwrite the package if it already exists.
    symlink:
        Whether to symlink the package instead of copying it. This is useful when
        developing a package locally, as it allows you to edit the package and see the
        changes reflected in the preview without having to re-create the package.
        *Important note*: On windows, setting ``symlink=True`` requires running the
        script as an administrator or enabling developer mode. See
        "https://learn.microsoft.com/en-us/windows/apps/get-started/enable-your-device-for-development"
        for more information.

    Returns
    -------
    folder:
        The path to the folder containing the package.

    """
    if typst_packages_folder is None:
        typst_packages_folder = os.environ.get(
            "TYPST_PACKAGES_FOLDER", TYPST_LOCAL_PACKAGES_DIR
        )
    assert typst_packages_folder is not None
    if not overwrite and symlink:
        raise ValueError("Cannot set both `overwrite=False` and `symlink` to True")

    logging.basicConfig(level=logging.INFO)

    toml_file = Path(toml_file).resolve()
    source_folder = toml_file.parent

    version, package_name, package_paths = _parse_toml(toml_file)
    if toml_file.name not in package_paths:
        package_paths.append(toml_file.name)

    upload_folder = Path(typst_packages_folder) / namespace / package_name / version
    if upload_folder.exists() and not overwrite:
        raise FileExistsError(f"{upload_folder} already exists")
    elif upload_folder.exists():
        shutil.rmtree(upload_folder)
    upload_folder.mkdir(parents=True)

    src = Path(source_folder)
    for entry in package_paths:
        _copy_entry(entry, src, upload_folder, symlink=symlink)
    logging.info(f"Created package at {upload_folder}")
    return upload_folder
