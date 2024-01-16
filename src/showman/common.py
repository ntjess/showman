from __future__ import annotations

import typing as t
from pathlib import Path

from omegaconf import OmegaConf
import tomli
from yaml import safe_load

FilePath = str | Path
OptionalFilePath = FilePath | None
StrList = list[str] | str
OptionalStrList = StrList | None

CONFIG_READERS = dict(
    toml=tomli.load,
    yaml=safe_load,
)


def read_config(file_or_config: FilePath | dict | None):
    if file_or_config is None:
        file_or_config = {}
    if isinstance(file_or_config, (str, Path)):
        file = Path(file_or_config)
        suffix = file.suffix.strip(".")
        if suffix not in CONFIG_READERS:
            raise ValueError(f"Unknown config file type: {file}")
        with open(file, "rb") as ifile:
            config = CONFIG_READERS[suffix](ifile)
    else:
        config = file_or_config
    return OmegaConf.create(config)


def read_showman_config():
    return read_config(Path(__file__).resolve().parent / "showman.toml")
