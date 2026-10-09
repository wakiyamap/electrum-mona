#!/usr/bin/env python3
"""Mechanically rename the python package `electrum` to `electrum_mona`.

Electrum-MONA ships its package as `electrum_mona` so that it can be installed
next to upstream Electrum. Doing that rename by hand on every upstream release
is tedious and makes merges conflict on thousands of import lines, so this
script does the purely mechanical part:

  1. `git mv electrum electrum_mona`
     and `electrum_mona/electrum` -> `electrum_mona/electrum-mona`
  2. rewrite python-level references to the package
     (`from electrum.x import y`, `import electrum`, `'electrum.plugins'`, ...)
  3. rewrite filesystem references to the package directory
     (`electrum/gui/icons/...`, `electrum\\gui\\icons\\...`, ...)

Everything that is *branding* (data dir name, window titles, URLs, binary
names, android package id, ...) is deliberately left alone: those are separate,
hand-written commits on top.

Intended workflow when catching up with a new upstream release:

    git merge -s ours --no-commit <upstream-tag>
    git read-tree --reset -u <upstream-tag>     # take the upstream tree as-is
    git commit
    # the upstream tree does not contain this script, so take it from our branch:
    git show master:contrib/mona/rename_package.py > /tmp/rename_package.py
    python3 /tmp/rename_package.py
    git commit -m "rename package: electrum -> electrum_mona"
    # ...then re-apply the Monacoin commits

The generic rules cover almost everything. A handful of places need an exact
edit (FIXUPS below); if upstream changes one of those lines the script prints a
warning so that it can be looked at by hand.

Run from anywhere inside the git checkout. Refuses to run twice.
"""
import os
import re
import subprocess
import sys

OLD = "electrum"
NEW = "electrum_mona"
OLD_SCRIPT = "electrum"       # electrum/electrum (symlink to ../run_electrum)
NEW_SCRIPT = "electrum-mona"

# Files we never touch: data files, third-party code, prose about upstream.
SKIP_PREFIXES = (
    ".gitmodules",  # updated by `git mv` itself
    "RELEASE-NOTES",
    "AUTHORS",
    "LICENCE",
    "pubkeys/",
    "fastlane/",
    "contrib/mona/",
    f"{OLD}/wordlist/",
    f"{OLD}/_vendor/",
    f"{OLD}/lnwire/",
    f"{OLD}/chains/",
    "tests/test_storage_upgrade/",
    "tests/fiat_fx_data/",
)
SKIP_SUFFIXES = (
    ".svg", ".png", ".jpg", ".gif", ".ico", ".icns", ".ttf", ".otf", ".pdn",
    ".asc", ".csv", ".json", ".patch", ".diff",
)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True,
    ).stdout


def package_entries() -> list[str]:
    """Names directly inside the package dir: `util`, `gui`, `version.py`, ..."""
    names = set()
    for path in git("ls-files", "-z", "--", f"{OLD}/").split("\0"):
        if not path:
            continue
        first = path.split("/")[1]
        names.add(first)
    return sorted(names)


def build_rules(entries: list[str]):
    modules = sorted({e[:-3] if e.endswith(".py") else e for e in entries
                      if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.py)?", e)},
                     key=len, reverse=True)
    mod_alt = "|".join(re.escape(m) for m in modules)
    # the launcher script `electrum/electrum` is handled by its own rule
    entry_alt = "|".join(re.escape(e) for e in sorted(entries, key=len, reverse=True)
                         if e != OLD_SCRIPT)
    # not preceded by something that makes it part of a longer name/path/host,
    # e.g. `self.electrum.x`, `org.electrum.x`, `download.electrum.org`
    not_in_name = r"(?<![\w.\-/\\$])"
    return [
        # --- python-level references -------------------------------------
        # from electrum import x / from electrum.util import y
        (re.compile(rf"(?<![\w.])from {OLD}(?=\.| import\b)"), f"from {NEW}"),
        # import electrum / import electrum.util as u
        (re.compile(rf"(?<![\w.])import {OLD}(?=[.\s,;]|$)", re.M), f"import {NEW}"),
        # electrum.util.foo, 'electrum.plugins', mock.patch("electrum.wallet...")
        (re.compile(rf"{not_in_name}{OLD}\.(?=(?:{mod_alt})\b)"), f"{NEW}."),
        # electrum.SimpleConfig, electrum.ELECTRUM_VERSION, electrum.__file__
        (re.compile(rf"{not_in_name}{OLD}\.(?=[A-Z][A-Za-z]*[a-z_]\w*\b(?!\.)|__\w+__)"), f"{NEW}."),
        # os.path.join(project_root, "electrum", "version.py")
        (re.compile(rf"""(os\.path\.join\([^\n]*?,\s*)(["']){OLD}\2(?=\s*[,)])"""), rf"\1\2{NEW}\2"),
        # --- filesystem references ---------------------------------------
        # the launcher: electrum/electrum -> electrum_mona/electrum-mona
        (re.compile(rf"(?<![\w.\-]){OLD}/{OLD_SCRIPT}(?![\w.\-/])"), f"{NEW}/{NEW_SCRIPT}"),
        # <checkout dir>/electrum/ where the checkout itself is also called electrum
        (re.compile(rf"(?<=/{OLD}/){OLD}/(?![\w.\-])"), f"{NEW}/"),
        # electrum/gui/..., "$ROOT/electrum/locale", electrum/*.so, electrum/libsecp256k1.so.*
        (re.compile(rf"(?<![\w.\-]){OLD}/(?=(?:{entry_alt})(?![\w-])|lib\w+[.\-]|\*|\$)"), f"{NEW}/"),
        # same, with sed-escaped slashes
        (re.compile(rf"(?<![\w.\-]){OLD}\\/(?=(?:{entry_alt})(?![\w-]))"), f"{NEW}\\\\/"),
        # windows-style paths in the NSIS script / pyinstaller specs
        (re.compile(rf"(?<![\w.\-]){OLD}\\(?=(?:{entry_alt})(?![\w-]))"), f"{NEW}\\\\"),
        # "$PROJECT_ROOT/electrum" and "$PROJECT_ROOT/electrum/" as a copy destination
        (re.compile(rf"(?<=PROJECT_ROOT/){OLD}(?=/?\")"), NEW),
        # PYPKG="electrum" in the pyinstaller specs
        (re.compile(rf"""(?<=PYPKG=)(["']){OLD}\1"""), rf"\1{NEW}\1"),
        # "... has been placed in the inner 'electrum' folder."
        (re.compile(rf"(?<='){OLD}(?=' folder)"), NEW),
    ]


# Exact edits for the few places the generic rules cannot express.
# (path before the move, old text, new text)
FIXUPS = [
    # logger names are derived from module names: strip the new package prefix
    (f"{OLD}/logging.py",
     'if record.name.startswith("electrum."):\n        record.name = record.name[9:]',
     f'if record.name.startswith("{NEW}."):\n        record.name = record.name[len("{NEW}."):]'),
    (f"{OLD}/logging.py", 'prefix = "electrum."', f'prefix = "{NEW}."'),
    # the Qt console exposes the package as `electrum`
    (f"{OLD}/gui/qt/main_window.py", "'electrum': electrum,", f"'electrum': {NEW},"),
    # a key of the `getinfo` output, not a module path
    (f"{OLD}/commands.py", f'"{NEW}.version": ELECTRUM_VERSION', '"electrum.version": ELECTRUM_VERSION'),
    (f"{OLD}/daemon.py", "fromlist=['electrum']", f"fromlist=['{NEW}']"),
    ("run_electrum", "fromlist=['electrum']", f"fromlist=['{NEW}']"),
    ("setup.py", "packages=(['electrum',]", f"packages=(['{NEW}',]"),
    ("setup.py", "[('electrum.'+pkg) for pkg in", f"[('{NEW}.'+pkg) for pkg in"),
    ("setup.py", "find_packages('electrum', exclude", f"find_packages('{NEW}', exclude"),
    ("setup.py", "'electrum': 'electrum'", f"'{NEW}': '{NEW}'"),
    ("MANIFEST.in", "graft electrum\n", f"graft {NEW}\n"),
    (".github/workflows/tests.yml", "--source=electrum ", f"--source={NEW} "),
]


def is_text_candidate(path: str) -> bool:
    if path.startswith(SKIP_PREFIXES) or path.endswith(SKIP_SUFFIXES):
        return False
    if os.path.islink(path) or not os.path.isfile(path):
        return False  # symlinks and submodules
    return True


def main() -> int:
    os.chdir(git("rev-parse", "--show-toplevel").strip())
    if os.path.exists(NEW):
        print(f"error: '{NEW}/' already exists; the rename was already applied.", file=sys.stderr)
        return 1
    if not os.path.isdir(OLD):
        print(f"error: '{OLD}/' not found.", file=sys.stderr)
        return 1

    entries = package_entries()
    rules = build_rules(entries)

    # 1. rewrite file contents (before moving, so SKIP_PREFIXES can use OLD)
    n_files = n_subs = 0
    for path in git("ls-files", "-z").split("\0"):
        if not path or not is_text_candidate(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                text = f.read()
        except UnicodeDecodeError:
            continue  # binary
        new_text, count = text, 0
        for pattern, repl in rules:
            new_text, k = pattern.subn(repl, new_text)
            count += k
        if count:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(new_text)
            n_files += 1
            n_subs += count

    # 1b. exact edits
    for path, old, new in FIXUPS:
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                text = f.read()
        except FileNotFoundError:
            text = ""
        if text.count(old) != 1:
            print(f"warning: fixup not applied, please check by hand: {path}: {old!r}", file=sys.stderr)
            continue
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text.replace(old, new))
        n_subs += 1

    # 2. move the package dir and the launcher script
    #    (staging first: `git mv` wants a clean .gitmodules and updates the
    #    submodule paths in it by itself)
    git("add", "-u")
    git("mv", OLD, NEW)
    git("mv", f"{NEW}/{OLD_SCRIPT}", f"{NEW}/{NEW_SCRIPT}")

    git("add", "-u")
    print(f"renamed {OLD}/ -> {NEW}/, rewrote {n_subs} references in {n_files} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
