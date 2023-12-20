from showman.converter import to_markdown
from showman.packager import create_package


def main():
    import fire

    return fire.Fire(dict(package=create_package, md=to_markdown), name="showman")


if __name__ == "__main__":
    main()
