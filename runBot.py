import os
from pathlib import Path


def main():
    # IDEs often use the workspace root as the working directory. The project
    # stores its configuration and runtime data next to this script, so make
    # all existing relative paths deterministic.
    os.chdir(Path(__file__).resolve().parent)

    import bot

    bot.mainLoop()


if __name__ == "__main__":
    main()
