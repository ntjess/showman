from __future__ import annotations

import ast
import json
import logging
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import typing as t
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from omegaconf import OmegaConf
from pexpect.popen_spawn import PopenSpawn
from pexpect.replwrap import REPLWrapper

from showman.common import (
    FilePath,
    OptionalFilePath,
    StrList,
    read_config,
    read_showman_config,
)


class SpawnWrapper(PopenSpawn):
    def __init__(self, cmd, *args, echo=False, encoding="utf-8", **kwargs):
        super().__init__(cmd, *args, encoding=encoding, **kwargs)
        self.echo = echo
        self.cmd = cmd
        # API compatibility to manage self as if it were a REPLWrapper
        self.child = self

    def __str__(self):
        return f"<SpawnWrapper: {self.cmd}>"

    def run_command(self, command: str, timeout=5):
        self.sendline(command)
        now = time.time()
        output = []
        while time.time() - now < timeout:
            try:
                result = self.read_nonblocking(size=100, timeout=1).strip()
                if result:
                    output.append(result)
            except Exception:
                break
        return "".join(output)


class ShellExecuter:
    def __init__(self, language: str, config: dict, timeout=5):
        self.config = config
        self.language = language
        self.timeout = config.get("timeout", timeout)

        self.repl: t.Optional[REPLWrapper | SpawnWrapper] = None
        self.build_dir: Path | None = None
        if self.config.get("repl"):
            self.repl = self._init_repl()

    def __repr__(self):
        return f"<ShellExecuter: {self.language}>"

    def _init_repl(self):
        cfg = self.config
        self.build_dir = Path(tempfile.mkdtemp())
        proc = SpawnWrapper(cfg["command"], cwd=self.build_dir)
        prompt = cfg["prompt"]
        if prompt:
            kwargs = {}
            if not isinstance(prompt, str):
                prompt, continue_prompt = prompt
                kwargs["continuation_prompt"] = continue_prompt

            proc = REPLWrapper(proc, prompt, None, **kwargs)
        if preamble := cfg.get("preamble", ""):
            proc.run_command(preamble + "\n", timeout=self.timeout)
        return proc

    def _run_standalone_command(self, code: str):
        cfg = self.config
        with tempfile.TemporaryDirectory() as build_dir:
            filename = cfg.get("filename", f"main.{self.language}")
            build_file = Path(build_dir) / Path(filename).name
            preamble = cfg.get("preamble", "")
            build_file.write_text("\n".join([preamble, code]))
            out = subprocess.check_output(
                cfg["command"], shell=True, text=True, cwd=build_dir
            )
        return out

    def __call__(self, code: str):
        code += "\n"
        if self.config.get("input-transform"):
            code = eval(self.config["input-transform"], dict(input=code))
        if self.repl is None:
            out = self._run_standalone_command(code)
        else:
            out = self.repl.run_command(code)
        if self.config.get("output-transform"):
            out = eval(self.config["output-transform"], dict(output=out, re=re))
        return out

    def cleanup(self):
        if self.repl is not None:
            self.repl.child.kill(signal.SIGINT)
            # Wait for the process to die
            self.repl.child.read_nonblocking(size=100, timeout=0.1)  # type: ignore
        if self.build_dir is not None:
            self.build_dir.rmdir()

    def __del__(self):
        self.cleanup()


class PythonExecuter:
    def exec_and_maybe_eval_last_line(self, code_string, globals_=None, locals_=None):
        """
        Execute a multi-line string of Python code. If the last line is an expression,
        return its value. Otherwise, execute the entire code and return None.

        Parameters
        ----------
        code_string
            A string containing Python code.
        globals_
            A dictionary defining the global namespace, defaults to globals().
        locals_
            (Optional) A dictionary defining the local namespace.

        Returns
        -------
        The value of the last expression, if any, else None.
        """

        def scope_exec(code):
            return exec(code, globals_, locals_)

        def scope_eval(code):
            return eval(code, globals_, locals_)

        if globals_ is None:
            globals_ = globals()
        try:
            parsed_code = ast.parse(code_string, mode="exec")

            if isinstance(parsed_code.body[-1], ast.Expr):
                *rest_of_code, last_expr = parsed_code.body
                last_expr = t.cast(ast.Expr, last_expr)
                module = ast.Module(body=rest_of_code, type_ignores=[])
                expr = ast.Expression(last_expr.value)
                scope_exec(compile(module, "<string>", "exec"))
                return scope_eval(compile(expr, "<string>", "eval"))
            else:
                scope_exec(code_string)
                return None
        except SyntaxError as se:
            return f"SyntaxError: {se}"
        except Exception as e:
            return f"Error: {e}"

    def _resolve_return_value(self, stdout, result):
        if result is None:
            return stdout
        if not stdout:
            return result
        if isinstance(result, str):
            return "\n".join([stdout, result])
        return [stdout, result]

    def __call__(self, code: str):
        with redirect_stdout(StringIO()) as f:
            result = self.exec_and_maybe_eval_last_line(code)
            printed = f.getvalue()
        if result is not None:
            # In the future (when typst supports pdf/html embeds), we can parse using
            # _repr_html_ and friends
            result = str(result)
        return self._resolve_return_value(printed, result)


class CodeRunner:
    language_executer_map: t.Dict[str, t.Callable] = dict(python=PythonExecuter())

    def __init__(self, workspace_dir: FilePath, config: dict | None = None):
        self.config = config or {}
        self.workspace_dir = Path(workspace_dir).resolve()
        self.logger = logging.getLogger(__name__)

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

    def exec_blocks_and_capture_outputs(self, blocks: list[str], lang: str):
        """
        Evaluates a list of python code blocks in a single python session. stdout from each
        block evaluation is separately captured.

        Parameters
        ----------
        blocks:
            A list of python code blocks to be evaluated
        lang:
            The language of the blocks to be evaluated

        Returns
        -------
        A list of stdout outputs from each block evaluation
        """
        if lang not in self.language_executer_map and lang not in self.config:
            raise ValueError(f"Language `{lang}` not supported")
        elif lang not in self.language_executer_map:
            self.language_executer_map[lang] = ShellExecuter(lang, self.config[lang])
        outputs = []
        for block in blocks:
            self.logger.debug(f"Executing block:\n{block}")
            out = self.language_executer_map[lang](block)
            self.logger.debug(f"Block output: {out}")
            outputs.append(out)
        return outputs

    def run(self, typst_file: FilePath, langs: StrList, save_cache=True):
        if isinstance(langs, str):
            langs = [langs]
        for lang in langs:
            blocks = self.get_labeled_blocks(typst_file, label=lang)
            if not blocks:
                continue
            outputs = self.exec_blocks_and_capture_outputs(blocks, lang=lang)
            self.update_cache(typst_file, lang, outputs)
        if save_cache:
            self.save_cache()


def execute(
    file: FilePath,
    root_dir: OptionalFilePath = None,
    langs: StrList | None = None,
    config: str | dict | None = None,
    dotlist: str | None = None,
):
    """
    Executes external code in a typst file based on the code block labels.

    Parameters
    ----------
    file:
        The typst file to be queried
    root_dir:
        The root directory of the workspace. Defaults to the current working directory.
    langs:
        The language or languages of the blocks to be retrieved. If an executer is
        registered for a given block language, the block will be run and its output will
        be saved to the cache. If not specified, every language with a registered
        executer will be run. Note that several languages can be specified as a
        space-separated string.
    config:
        The path to a config file for the executer. If not specified, the default config
        will be used. Optionally, a dictionary can be passed in directly.
    dotlist:
        Can be provided alongside config to modify specific values. If multiple values are
        provided, they must be separated with a double semicolon. For instance, to change
        executer commands both for R and add a preamble to javascript blocks, you could
        provide
        ``dotlist="r.command='Rscript --my-flags';; js.preamble='let x = 5'"``. You
        can view more information on dotlist syntax at
        https://omegaconf.readthedocs.io/en/latest/usage.html
    """
    user_config = OmegaConf.merge(
        read_showman_config()["executer"], read_config(config)
    )
    if dotlist is not None:
        dotlist_fmt = [line.strip() for line in dotlist.split(";;")]
        user_config = OmegaConf.merge(user_config, OmegaConf.from_dotlist(dotlist_fmt))
    config = t.cast(dict, user_config)

    runner = CodeRunner(root_dir or os.getcwd(), config=config)
    if langs is None:
        langs = sorted(set(list(runner.language_executer_map) + list(runner.config)))
    if isinstance(langs, str):
        langs = langs.split()
    # runner.logger.setLevel("DEBUG")
    runner.logger.addHandler(logging.StreamHandler(sys.stdout))
    runner.run(file, langs=langs)


if __name__ == "__main__":
    out = execute(
        "examples/external-code.typ",
        langs=["r"],
        dotlist="r.command=R --ess --no-echo --no-save --interactive",
    )
    x = out
