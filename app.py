import sys

from texttests import script_runner


def run(input_text: str) -> None:
    script_runner.run(input_text)


if __name__ == '__main__':  # pragma: no cover
    try:
        run(sys.stdin.read())
    except ValueError as e:
        print(e)
