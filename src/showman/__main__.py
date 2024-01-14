import functools

from showman.converter import to_markdown
from showman.packager import create_package
from showman.executer import execute


@functools.wraps(create_package)
def create_package_wrapper(*args, **kwargs):
    """
    ``Fire`` double-prints a function's return value, which causes unnecessary outputs
    for any return value other than ``None``. So, simply wrap the ``create_package``
    function to return ``None``.
    """
    create_package(*args, **kwargs)


def main():
    import fire

    return fire.Fire(
        dict(package=create_package_wrapper, md=to_markdown, execute=execute),
        name="showman",
    )


if __name__ == "__main__":
    main()
