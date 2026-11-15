#!/usr/bin/env python3
"""Rename the python package of an upstream Electrum tree: electrum -> electrum_mona.

Run it from the root of a checkout whose tree is exactly an upstream release
(see README.md in this directory). It moves the package directory, edits the
tracked text files and stages the result; it does not commit.

The rules below are textual. They are checked against the previous release
(the script has to reproduce the previous "rename package" commit exactly), so
after a run, look at the warnings and at
    git diff --cached -M | grep '^[-+]' | grep -w electrum
for new upstream lines that none of the rules knows about.
"""
import os
import re
import subprocess
import sys

OLD = "electrum"
NEW = "electrum_mona"

# "electrum.<x>" where <x> is not a submodule of the package
NOT_A_MODULE = "org|png|ico|icns|svg|po|mo|pot|desktop|nsi|exe|dat|conf|sh|py|html|log|json|path"
# "electrum/<x>" where electrum is a checkout directory or a plain name, not the package
NOT_IN_PACKAGE = r"contrib|dist\b|www|localized|\.buildozer|\d|ln_multisig|plugins_key|\{| also|` folder"
# data files: never edited
SKIP = re.compile(r"^(electrum_mona/chains/|electrum_mona/wordlist/|tests/test_storage_upgrade/)")

# (regex, replacement), applied in this order to every tracked text file
RULES = [
    # python imports
    (r"\bfrom electrum(?=\.[a-zA-Z_]| import\b)", "from " + NEW),
    (r"\bimport electrum(?=[ .;,\n]|$)", "import " + NEW),
    # attribute access and dotted module paths: electrum.util, electrum.gui.qt, ...
    (r"(?<![\w./@-])electrum\.(?=(?!(?:" + NOT_A_MODULE + r")\b|version\")[A-Za-z_])", NEW + "."),
    (r"(?<=startswith\(\")electrum\.(?=\")", NEW + "."),
    (r"(?<=prefix = \")electrum\.(?=\")", NEW + "."),
    (r"(?<=\(')electrum\.(?='\+pkg\))", NEW + "."),
    # paths: electrum/gui/..., $PROJECT_ROOT/electrum/...
    (r"(?<![\w.-])(?<!spesmilo/)(?<!drive_c/)(?<!\.git/)(?<!submodule \")electrum/(?!" + NOT_IN_PACKAGE + ")",
     NEW + "/"),
    (r"(?<= )electrum\\/(?=gui)", NEW + r"\\/"),
    (r"\\electrum\\(?=gui)", r"\\" + NEW + r"\\"),
    (r"(?<=\$PROJECT_ROOT/)electrum(?=\")", NEW),
    # the package name as a string, where it is a directory or a module name
    (r"(?<=_root, )\"electrum\"", '"' + NEW + '"'),
    (r"(?<=_ROOT, )\"electrum\"", '"' + NEW + '"'),
    (r"(?<=_path, )\"electrum\"", '"' + NEW + '"'),
    (r"(?<=os\.path\.dirname\(__file__\), )'electrum'", "'" + NEW + "'"),
    (r"(?<=PYPKG=)([\"'])electrum\1", r"\1" + NEW + r"\1"),
    (r"(?<=fromlist=\[)'electrum'", "'" + NEW + "'"),
    (r"(?<=packages=\(\[)'electrum'", "'" + NEW + "'"),
    (r"(?<=find_packages\()'electrum'", "'" + NEW + "'"),
    (r"'electrum': 'electrum'", f"'{NEW}': '{NEW}'"),
    (r"'electrum': electrum,", f"'electrum': {NEW},"),
    (r"'electrum' folder", f"'{NEW}' folder"),
    (r"^(graft |          coverage run --source=)electrum(?= \\$|$)", r"\1" + NEW),
]
RULES = [(re.compile(regex, re.M), repl) for regex, repl in RULES]

# (file, old, new): lines that need an exact edit. A warning is printed if one
# of them does not apply any more.
FIXUPS = [
    # len("electrum.")
    ("electrum_mona/logging.py", "record.name = record.name[9:]", f'record.name = record.name[len("{NEW}."):]'),
    # the launcher inside the package, see MOVES
    ("setup.py", "scripts=['electrum_mona/electrum'],", "scripts=['electrum_mona/electrum-mona'],"),
]

# (old, new): renamed after the package directory has been moved
MOVES = [
    ("electrum_mona/electrum", "electrum_mona/electrum-mona"),
]


def tracked_files():
    out = subprocess.check_output(["git", "ls-files", "-s", "-z"]).decode()
    for entry in out.split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        if meta.split()[0] in ("100644", "100755"):  # no symlinks, no submodules
            yield path


def main():
    if not os.path.isdir(OLD) or os.path.exists(NEW):
        sys.exit(f"expected ./{OLD} and no ./{NEW}: run this on an upstream tree")
    warnings = 0
    subprocess.check_call(["git", "mv", OLD, NEW])
    for old, new in MOVES:
        if os.path.lexists(old):
            subprocess.check_call(["git", "mv", old, new])
        else:
            print(f"warning: {old} not found, not renamed to {new}")
            warnings += 1
    fixups = {}
    for path, old, new in FIXUPS:
        fixups.setdefault(path, []).append((old, new))
    for path in tracked_files():
        if SKIP.match(path):
            continue
        with open(path, "rb") as f:
            raw = f.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        new_text = text
        for regex, repl in RULES:
            new_text = regex.sub(repl, new_text)
        for old, new in fixups.pop(path, []):
            if old not in new_text:
                print(f"warning: {path}: fixup does not apply: {old!r}")
                warnings += 1
            new_text = new_text.replace(old, new)
        if new_text != text:
            with open(path, "wb") as f:
                f.write(new_text.encode("utf-8"))
    for path in fixups:
        print(f"warning: {path}: file not found, fixups not applied")
        warnings += 1
    subprocess.check_call(["git", "add", "-A"])
    print(f"done, {warnings} warning(s)")


if __name__ == "__main__":
    main()
