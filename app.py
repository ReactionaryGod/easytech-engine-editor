"""WC4 Engine Editor - visual editor for libworld-conqueror-4.so (World Conqueror 4 1.30.0).

usage: python app.py [mod package folder]   (both games are listed in the top bar)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    from wc4engine import projects
    reg = projects.ensure_defaults(projects.load())
    if len(sys.argv) > 1:                                  # open a specific package
        pkg = os.path.abspath(sys.argv[1])
        if not os.path.isdir(pkg):
            sys.exit("package folder not found: %s" % pkg)
        projects.add(reg, projects.game_of(pkg), pkg)
        index = next(i for i, p in enumerate(reg["projects"]) if os.path.abspath(p["package"]) == pkg)
    else:
        index = 0
    if not reg["projects"]:
        sys.exit("no mod package found; pass a package folder as the first argument")
    projects.save(reg)
    from wc4engine.ui.shell import run
    run(reg, index)


if __name__ == "__main__":
    main()
