"""release.py - build the beta zip players download: dist\\conflict-tools-<version>.zip, holding a conflict-tools\\
folder with exactly what deploy.py ships, taken from the last commit (HEAD). Unzip it into the Morrowind folder.

Usage: python release.py [VERSION]      VERSION defaults to `git describe --tags --always` (e.g. v0.9-beta or a1b2c3d)
Python 3.9+, standard library only. Credit: dej (dejunai).
"""
import os
import subprocess
import sys

import deploy

HERE = os.path.dirname(os.path.abspath(__file__))


def git(*args):
    return subprocess.run(["git", "-C", HERE, *args], capture_output=True, text=True, check=True).stdout.strip()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    version = argv[0] if argv else git("describe", "--tags", "--always")
    ship = deploy.ship_list(deploy.tracked_files(HERE), deploy.read_manifest())
    renamed = [f"{src} => {dst}" for src, dst in ship if src != dst]
    if renamed:                                   # git archive keeps paths, so a manifest rename can't be honoured
        sys.exit("release.py can't ship renamed files yet:\n  " + "\n  ".join(renamed))
    files = [src for src, _dst in ship]
    dirty = git("status", "--porcelain", "--", *files)
    if dirty:
        print("These shipped files have uncommitted changes; the zip holds the committed versions:\n" + dirty)
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    out = os.path.join(HERE, "dist", f"conflict-tools-{version}.zip")
    # git archive writes each file as a checkout would (.gitattributes: LF, .bat files CRLF)
    subprocess.run(["git", "-C", HERE, "archive", "--format=zip", "--prefix=conflict-tools/", "-o", out, "HEAD",
                    "--", *files], check=True)
    print(f"{out}: {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
