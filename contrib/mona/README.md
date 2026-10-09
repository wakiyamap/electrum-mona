# Electrum-MONA maintenance notes

Electrum-MONA is upstream [Electrum](https://github.com/spesmilo/electrum) plus a
small set of Monacoin changes. This directory has the tools to keep it that way.

## Catching up with a new upstream release

The python package is called `electrum_mona` (upstream: `electrum`). Merging
upstream directly would conflict on thousands of import lines, so the rename is
done by a script and the history is kept in layers:

1. `Merge tag 'X.Y.Z'`: the tree of this commit is exactly the upstream tree.
2. `rename package: electrum -> electrum_mona`: the output of `rename_package.py`,
   nothing else.
3. The Monacoin commits, re-applied on top.

```
git fetch https://github.com/spesmilo/electrum '+refs/tags/*:refs/upstream-tags/*' --no-tags
git checkout -b main-X.Y.Z master
git merge -s ours --no-commit refs/upstream-tags/X.Y.Z
git read-tree --reset -u refs/upstream-tags/X.Y.Z
git commit                                   # "Merge tag 'X.Y.Z'"
git show master:contrib/mona/rename_package.py > /tmp/rename_package.py
python3 /tmp/rename_package.py
git commit -m "rename package: electrum -> electrum_mona"
git cherry-pick <the Monacoin commits of the previous release>
```

(Upstream tags are fetched into `refs/upstream-tags/` because this repository has
its own tags with the same names.)

If `rename_package.py` prints warnings, upstream changed one of the few lines
that need an exact edit: fix it by hand and update `FIXUPS` in the script.

## Tests

The test vectors shared with upstream are Bitcoin vectors. The test suite runs
with the upstream chain parameters (`tests/upstream_params.py`); what is specific
to Monacoin is tested with the real parameters in `tests/test_monacoin.py`,
`tests/test_scrypt.py` and the Monacoin part of `tests/test_blockchain.py`.

## Checkpoints

`make_checkpoints.py` extends `electrum_mona/chains/<net>/checkpoints.json` from
the headers of a synchronized wallet. See the docstring of the script.

## lyra2re2_hash

The Lyra2REv2 proof-of-work comes from the `lyra2re2_hash` C extension, which has
to be compiled with `CFLAGS="-fno-strict-aliasing -DPY_SSIZE_T_CLEAN"`:

- without `-fno-strict-aliasing`, recent gcc miscompiles it at -O2 and it returns
  wrong hashes;
- without `-DPY_SSIZE_T_CLEAN`, it raises `SystemError` on python 3.10 - 3.12.

`electrum_mona/blockchain.py` checks this at import. The build scripts take the
flags from `contrib/build_tools_util.sh`.

## Releases

The binaries are built by the `builds` workflow (GitHub Actions), which is only
started by hand. The file names come from `git describe`, so tag first:

```
git tag -s X.Y.Z && git push origin X.Y.Z
gh workflow run builds.yml --ref X.Y.Z -f target=all
gh run list --workflow builds.yml          # wait for the run, note its id
```

Then, on the machine that holds the release key (`pubkeys/wakiyamap.asc`):

```
contrib/mona/sign_release.sh --run <run id>
gh release create X.Y.Z --draft --title X.Y.Z dist-release/<run id>/*
```

`sign_release.sh` downloads the artifacts of the run and writes a detached GPG
signature `<file>.asc` next to each file. It can also sign the files of a
directory (`sign_release.sh <directory>`).

The GPG signature covers the file as it is, so it has to be the last step: once
the Windows binaries are Authenticode-signed, the dmg is signed and notarized,
or the APK is signed with the release keystore, sign those files and not the
unsigned ones from the workflow.
