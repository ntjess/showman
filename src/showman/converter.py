import atexit
import inspect
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import typing as t
from pathlib import Path

import pypandoc

from showman.common import FilePath, OptionalFilePath, OptionalStrList

here = Path(__file__).parent.resolve()
showman_typst_dir = here
if not showman_typst_dir.joinpath("formatter.typ").exists():
    # Maybe we're in an sdist-installed environment
    # Backtrack from src/showman/ to src/formatter.typ
    showman_typst_dir = here.parent
if not showman_typst_dir.joinpath("formatter.typ").exists():
    raise FileNotFoundError(
        f"Can't find `showman` typst directory, checked {here} and {showman_typst_dir}"
    )


def repo_url_to_raw(url):
    match_expr = (
        r"https://www.(?P<site>.*)/(?P<user>.*)/(?P<repo>.*)/(?P<branch_or_tag>.*)/"
    )
    pieces = re.match(match_expr, url)
    if pieces is None:
        raise ValueError(f"Could not parse url {url}. Must be of form {match_expr}")
    # Shorten for access brevity
    m = pieces.groupdict()
    return f'https://www.{m["site"]}/{m["user"]}/{m["repo"]}/raw/{m["branch_or_tag"]}'
    return url


def _template(
    rel_typst_file: str,
    showable_labels: OptionalStrList,
):
    convert_dict = {}
    if showable_labels is not None:
        convert_dict["showable-labels"] = showable_labels
    # Typst format looks different than python literals, but has a json decoder.
    # So instead of using if-statements to build the string, just use json
    dict_args = f'json.decode("{json.dumps(convert_dict)}")'
    return inspect.cleandoc(
        f"""
        #import "formatter.typ"
        #formatter._content-printer("{rel_typst_file}", ..{dict_args})
        """
    )


def run_cmd_and_raise_errs(cmd, **kwargs):
    try:
        out = subprocess.check_output(cmd, text=True, shell=True, **kwargs)
    except subprocess.CalledProcessError as e:
        out = e.output
        raise RuntimeError(out)
    return out


class DummyTemporaryDirectory:
    """
    A noop context manager compatible with TemporaryDirectory usage
    """

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def cleanup(self):
        pass


class Converter:
    def __init__(
        self,
        typst_file: FilePath,
        assets_dir: OptionalFilePath,
        root_dir: OptionalFilePath = None,
        image_name="example-{n}.png",
        showable_labels: OptionalStrList = None,
        log_level="INFO",
    ):
        typst_file = Path(typst_file).resolve()
        if not typst_file.exists():
            raise FileNotFoundError(str(typst_file))
        if root_dir is None:
            root_dir = typst_file.parent
        root_dir = Path(root_dir).resolve()

        if isinstance(showable_labels, str):
            showable_labels = [showable_labels]

        if root_dir not in typst_file.parents:
            raise ValueError(f"File {typst_file} is not in root path {root_dir}")
        if assets_dir is None:
            assets_dir = typst_file.parent / f"{typst_file.stem}-assets"
        assets_dir = Path(assets_dir).resolve()
        assets_dir.mkdir(exist_ok=True)
        self.typst_file = typst_file
        self.root_dir = root_dir
        self.assets_dir = assets_dir
        self.image_name = image_name
        self.showable_labels = showable_labels
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)
        debug = self.logger.level <= logging.DEBUG
        if debug:
            handler = logging.StreamHandler()
            self.logger.addHandler(handler)

        self.build_dir, self.build_file = self._setup_build_folder(persist=debug)

        runnable_langs = self._get_runnable_langs()
        tags_combined = "|".join(runnable_langs)
        self.languages_regex = re.compile(rf"\s*```.*\b{tags_combined}.*\b")

    def _get_runnable_langs(self):
        assert self.build_dir is not None
        cmd = (
            f'typst query "{self.build_file}" "<runnable-lang>"'
            f' --root "{self.root_dir}"'
            f" --field value"
        )
        self.logger.debug(f"Getting runnable lang tags: {cmd}")
        out = run_cmd_and_raise_errs(cmd)
        return sorted(set(json.loads(out)))

    def _setup_build_folder(self, persist=False):
        file = self.typst_file
        if persist:
            td_path = self.typst_file.parent / f"{self.typst_file.stem}-showman"
            td_path.mkdir(exist_ok=True)
            # Just a dummy context manager
            td = DummyTemporaryDirectory()

        else:
            td = tempfile.TemporaryDirectory(dir=file.parent, prefix=file.stem)
            td_path = Path(td.name)
            atexit.register(td.cleanup)

        for to_copy in "formatter.typ", "runner.typ":
            shutil.copy(showman_typst_dir / to_copy, td_path)

        to_compile = td_path / file.name
        # td is inside the compiled file's folder, so add a "../" to the typst file
        # relative to `to_compile`'s world
        template_str = _template(f"../{file.name}", self.showable_labels)
        with open(to_compile, "w") as f:
            f.write(template_str)
        return td, to_compile

    def __del__(self):
        if hasattr(self, "build_dir"):
            self.build_dir.cleanup()

    def generate_images(self, force=True):
        existing_files = self.get_exported_images()
        if not force and len(existing_files) > 1:
            return existing_files
        for file in existing_files:
            file.unlink()

        output_name = f"{self.assets_dir}/{self.image_name}"
        cmd = f'typst c "{self.build_file}" "{output_name}" --root "{self.root_dir}"'
        self.logger.debug(f"Generating images: {cmd}")
        with self.build_dir:
            run_cmd_and_raise_errs(cmd)
        return self._delete_first_image()

    def _delete_first_image(self):
        """
        Typst doesn't allow exporting just a subset of pages, and the first page contains
        meaningless information (a blank page possessing hidden content). So we have to
        delete this page and renumber the rest of the exports manually.
        """
        existing = self.get_exported_images()
        if len(existing) == 0:
            return
        existing.pop(0).unlink()
        max_pad = len(str(len(existing)))
        for ii, file in enumerate(existing, start=1):
            file.rename(file.parent / self.image_name.format(n=f"{ii:0{max_pad}d}"))

    def get_exported_images(self):
        files = sorted(self.assets_dir.glob(self.image_name.format(n="*")))
        return files

    def get_markdown_with_injected_images(self, output_dir: OptionalFilePath = None):
        old_cwd = os.getcwd()
        try:
            os.chdir(self.root_dir)
            contents = pypandoc.convert_file(
                self.typst_file.relative_to(self.root_dir),
                to="gfm",
                format="typst",
            )
        finally:
            os.chdir(old_cwd)
        lines = contents.splitlines()
        out_lines = []
        example_number = 0
        lines_iter = iter(lines)

        if output_dir is None:
            parent = self.assets_dir.name
        else:
            output_as_path = Path(output_dir).resolve()
            output_and_parents = (output_as_path, *output_as_path.parents)
            if output_as_path.exists() and self.root_dir in output_and_parents:
                # Use "os.path.relpath" instead of "Path.relative_to" because the latter
                # only works if the path is a subpath of the current directory. This is
                # not always the case, for example if assets are in ./root/assets and
                # the export is in ./root/dir/subdir
                parent = os.path.relpath(self.assets_dir, start=output_dir)
            else:
                # Can be nonrelated directory, url, etc.
                parent = str(output_dir)

        def graceful_next(iterable):
            try:
                return next(iterable)
            except StopIteration:
                return None

        def eat_code_block(first_line, lines_iter, out_lines):
            # Replace this language with "typst", find the end of the block
            line = re.sub(self.languages_regex, "``` typst", first_line)
            out_lines.append(line)
            while (line := graceful_next(lines_iter)) is not None and not re.match(
                r"```", line
            ):
                out_lines.append(line)
            if line is not None:
                out_lines.append(line)

        max_pad = len(str(len(self.get_exported_images())))

        for line in lines_iter:
            if re.match(self.languages_regex, line):
                example_number += 1
                eat_code_block(line, lines_iter, out_lines)
                n = f"{example_number:0{max_pad}d}"
                cur_asset = f"{parent}/{self.image_name.format(n=n)}"
                out_lines.append(f"![Example {example_number}]({cur_asset})")
            else:
                out_lines.append(line)
        return "\n".join(out_lines)

    def save(self, out_path: FilePath, remote_url: str | None = None, force=True):
        self.generate_images(force=force)
        out_dir = Path(out_path).resolve().parent
        if remote_url is not None:
            out_dir = repo_url_to_raw(remote_url)
            rel_assets = os.path.relpath(self.assets_dir, start=self.root_dir)
            out_dir = f"{out_dir}/{rel_assets}"
        out_text = self.get_markdown_with_injected_images(out_dir)
        with open(out_path, "wb") as f:
            f.write(bytes(out_text, encoding="utf-8"))


def to_markdown(
    typst_file: FilePath,
    output: OptionalFilePath = None,
    *,
    root_dir: OptionalFilePath = None,
    assets_dir: OptionalFilePath = None,
    image_name="example-{n}.png",
    showable_labels: OptionalStrList = None,
    git_url: str | None = None,
    log_level="INFO",
    force=True,
):
    """
    Convert a typst file to markdown, rendering the output from executable typst code
    blocks as images.

    Parameters
    ----------
    typst_file:
        The typst file to convert
    output:
        The markdown file to save. If unspecified, it will be the same as ``typst_file``
        but with a .md extension
    root_dir:
        The directory to run typst from If unspecified, it will be the parent directory
        of ``typst_file``
    assets_dir:
        The directory to save the images to. If unspecified, it will be a "<file>-assets" folder
        in the same directory as ``typst_file``
    image_name:
        Name given to generated images. Per typst documentation, the string "{n}" is
        required and will be replaced with the image number.
    showable_labels:
        The labels attached to any content that should be captured as an example output.
        If using default showman properties, this doesn't need to be set manually.
    git_url:
        The git url to the repo, by default None. If set, images are still generated
        to the specified local assets folder, but the readme will link images relative
        to this url. It is useful in the common typst paradigm where packages submitted
        to the official registry don't include the assets folder, but the readme does
        include the images.
    log_level:
        If "DEBUG", the template for saving output examples will be saved alongside the
        typst file.
    force:
        Whether to force save the images. If false, and images already exist in the
        assets folder, they will not be regenerated.
    """
    if output is None:
        output = Path(typst_file).with_suffix(".md")
    converter = Converter(
        typst_file,
        assets_dir,
        root_dir,
        image_name,
        showable_labels,
        log_level,
    )
    converter.save(output, remote_url=git_url, force=force)
