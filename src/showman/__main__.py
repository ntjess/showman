from showman.converter import to_markdown
from showman.packager import create_package
from showman.executer import execute


def main():
    import fire

    return fire.Fire(
        dict(package=create_package, md=to_markdown, execute=execute), name="showman"
    )


if __name__ == "__main__":
    main()
