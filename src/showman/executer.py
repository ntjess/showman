from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from showman.common import FilePath, OptionalFilePath, StrList


def python_executor(block: str):
    with redirect_stdout(StringIO()) as f:
        exec(block, globals())
        out = f.getvalue()
    return out


def bash_executor(block: str):
    out = subprocess.check_output(block, shell=True, text=True)
    return out


def cpp_executor(block: str, compiler="g++"):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        cpp_file = tmpdir / "main.cpp"
        cpp_file.write_text(block)
        out = subprocess.check_output(
            f"{compiler} {cpp_file} -o {tmpdir}/main && {tmpdir}/main",
            shell=True,
            text=True,
        )
    return out


class CodeRunner:
    def __init__(self, workspace_dir: FilePath):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.logger = logging.getLogger(__name__)
        self.language_executor_map = dict(
            python=python_executor,
            cpp=cpp_executor,
        )
        if sys.platform != "win32":
            self.language_executor_map["bash"] = bash_executor

        self.cache_file = cache_file = self.workspace_dir / ".coderunner.json"
        if not cache_file.exists():
            self.workspace_cache = {}
            self.cache_file.write_text("{}")
        else:
            with open(cache_file, "r") as f:
                self.workspace_cache = json.load(f)

    def get_cache_key(self, file: FilePath):
        file = Path(file).resolve()
        if self.workspace_dir not in file.parents:
            raise ValueError(f"File {file} is not in workspace {self.workspace_dir}")
        return file.relative_to(self.workspace_dir).as_posix()

    def get_cache_value(self, file: FilePath, return_key=False):
        rel_file = self.get_cache_key(file)
        if rel_file not in self.workspace_cache:
            self.workspace_cache[rel_file] = {}
        out = self.workspace_cache[rel_file].copy()
        if return_key:
            return out, rel_file
        return out

    def update_cache(self, file: FilePath, label: str, outputs: list[str]):
        file_cache, key = self.get_cache_value(file, return_key=True)
        file_cache[label] = outputs

        self.workspace_cache[key][label] = outputs

    def save_cache(self):
        with open(self.cache_file, "w") as f:
            json.dump(self.workspace_cache, f)

    def get_labeled_blocks(self, file: FilePath, label: str):
        """
        Retrieves code blocks from a typ file requested to be run based on their label.

        Parameters
        ----------
        file:
            The typst file to be queried
        label:
            The label or labels of the blocks to be retrieved
        concatenate:
            Whether to concatenate the blocks into a single python runnable string. Otherwise,
            returns an array of individual code blocks found in the file.
        """
        selector = f"<{label}>"
        workspace_dir = os.getcwd()
        cmd = (
            f"typst query"
            f' "{Path(file).resolve()}"'
            f' "{selector}"'
            f" --field value"
            f" --format json"
            f" --root {workspace_dir}"
        )
        self.logger.debug(f"Running command: {cmd}")
        workspace_dir = os.getcwd()
        result = json.loads(subprocess.check_output(cmd, shell=True, text=True))
        return result

    def exec_blocks_and_capture_outputs(self, blocks: list[str], language: str):
        """
        Evaluates a list of python code blocks in a single python session. stdout from each
        block evaluation is separately captured.

        Parameters
        ----------
        blocks:
            A list of python code blocks to be evaluated

        Returns
        -------
        A list of stdout outputs from each block evaluation
        """
        if language not in self.language_executor_map:
            raise ValueError(f"Language `{language}` not supported")
        outputs = []
        for block in blocks:
            self.logger.debug(f"Executing block:\n{block}")
            out = self.language_executor_map[language](block)
            self.logger.debug(f"Block output: {out}")
            outputs.append(out)
        return outputs

    def run(self, typst_file: FilePath, labels: StrList, save_cache=True):
        if isinstance(labels, str):
            labels = [labels]
        for label in labels:
            blocks = self.get_labeled_blocks(typst_file, label=label)
            outputs = self.exec_blocks_and_capture_outputs(blocks, language=label)
            self.update_cache(typst_file, label, outputs)
        if save_cache:
            self.save_cache()


def execute(
    file: FilePath,
    root_dir: OptionalFilePath = None,
    labels: StrList | None = None,
):
    """
    Executes external code in a typst file based on the code block labels.

    Parameters
    ----------
    file:
        The typst file to be queried
    root_dir:
        The root directory of the workspace. Defaults to the current working directory.
    label:
        The label or labels of the blocks to be retrieved. If an executor is registered
        for a given block language, the block will be run and its output will be saved
        to the cache. If not specified, every language with a registered executor
        will be run.
    """
    runner = CodeRunner(root_dir or os.getcwd())
    if labels is None:
        labels = list(runner.language_executor_map)
    # runner.logger.setLevel("DEBUG")
    runner.logger.addHandler(logging.StreamHandler(sys.stdout))
    runner.run(file, labels=labels)
