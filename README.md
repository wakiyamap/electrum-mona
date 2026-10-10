# Electrum-mona - Lightweight Monacoin client

```
Licence: MIT Licence
Author: Thomas Voegtlin
Port Maintainer: WakiyamaP (Electrum-mona)
Language: Python (>= 3.10)
Homepage: https://electrum-mona.org/
```

[![Test Status](https://github.com/wakiyamap/electrum-mona/actions/workflows/tests.yml/badge.svg?branch=master)](https://github.com/wakiyamap/electrum-mona/actions/workflows/tests.yml)
[![Build Status](https://github.com/wakiyamap/electrum-mona/actions/workflows/builds.yml/badge.svg?branch=master)](https://github.com/wakiyamap/electrum-mona/actions/workflows/builds.yml)
[![Test coverage statistics](https://coveralls.io/repos/github/wakiyamap/electrum-mona/badge.svg?branch=master)](https://coveralls.io/github/wakiyamap/electrum-mona?branch=master)


## Getting started

_(If you've come here looking to simply run Electrum-mona,
[you may download it here](https://electrum-mona.org/).)_

Electrum itself is pure Python, and so are most of the required dependencies,
but not everything. The following sections describe how to run from source, but here
is a TL;DR:

```
$ sudo apt-get install libsecp256k1-dev build-essential python3-dev
$ CFLAGS="-fno-strict-aliasing -DPY_SSIZE_T_CLEAN" ELECTRUM_ECC_DONT_COMPILE=1 python3 -m pip install --user ".[gui,crypto]"
```
(the `CFLAGS` are needed to compile `lyra2re2_hash` correctly, see below)

### Not pure-python dependencies

#### Qt GUI

If you want to use the Qt interface, install the Qt dependencies:
```
$ sudo apt-get install python3-pyqt6
```

#### libsecp256k1

For elliptic curve operations,
[libsecp256k1](https://github.com/bitcoin-core/secp256k1)
is a required dependency.

If you "pip install" Electrum, by default libsecp will get compiled locally,
as part of the `electrum-ecc` dependency. This can be opted-out of,
by setting the `ELECTRUM_ECC_DONT_COMPILE=1` environment variable.
For the compilation to work, besides a C compiler, you need at least:
```
$ sudo apt-get install automake libtool
```
If you opt out of the compilation, you need to provide libsecp in another way, e.g.:
```
$ sudo apt-get install libsecp256k1-dev
```

#### lyra2re2_hash

For the Lyra2REv2 proof-of-work of Monacoin,
[lyra2re2_hash](https://pypi.org/project/lyra2re2-hash/)
is a required dependency.

This is a C extension that gets compiled locally when you "pip install" it,
so you need a C compiler and the Python headers.
Its sources must be compiled with `-fno-strict-aliasing` (recent compilers miscompile
them otherwise, and it then returns wrong hashes), and with `-DPY_SSIZE_T_CLEAN`
(needed for Python older than 3.13):
```
$ sudo apt-get install build-essential python3-dev
$ CFLAGS="-fno-strict-aliasing -DPY_SSIZE_T_CLEAN" python3 -m pip install --user --no-binary lyra2re2_hash lyra2re2_hash
```
If it is already installed but was built without these flags,
add `--force-reinstall --no-cache-dir` to rebuild it.

#### cryptography

Due to the need for fast symmetric ciphers,
[cryptography](https://github.com/pyca/cryptography) is required.
Install from your package manager (or from pip):
```
$ sudo apt-get install python3-cryptography
```

#### hardware-wallet support

If you would like hardware wallet support,
[see this](https://github.com/spesmilo/electrum-docs/blob/master/hardware-linux.rst).


### Running from tar.gz

If you downloaded the official package (tar.gz), you can run
Electrum-mona from its root directory without installing it on your
system; all the pure python dependencies are included in the 'packages'
directory (`lyra2re2_hash` is not pure python: install it as described above).
To run Electrum from its root directory, just do:
```
$ ./run_electrum
```

You can also install Electrum-mona on your system, by running this command:
```
$ sudo apt-get install python3-setuptools python3-pip
$ CFLAGS="-fno-strict-aliasing -DPY_SSIZE_T_CLEAN" python3 -m pip install --user .
```

This will download and install the Python dependencies used by
Electrum-mona instead of using the 'packages' directory.
It will also place an executable named `electrum-mona` in `~/.local/bin`,
so make sure that is on your `PATH` variable.


### Development version (git clone)

_(For OS-specific instructions, see [here for Windows](contrib/build-wine/README_windows.md),
and [for macOS](contrib/osx/README_macos.md))_

Check out the code from GitHub:
```
$ git clone https://github.com/wakiyamap/electrum-mona.git
$ cd electrum-mona
$ git submodule update --init
```

Run install (this should install dependencies, including `lyra2re2_hash`, hence the `CFLAGS`):
```
$ CFLAGS="-fno-strict-aliasing -DPY_SSIZE_T_CLEAN" python3 -m pip install --user -e .
```

Create translations (optional):
```
$ sudo apt-get install gettext
$ ./contrib/locale/build_locale.sh electrum_mona/locale/locale electrum_mona/locale/locale
```

Finally, to start Electrum:
```
$ ./run_electrum
```

### Run tests

Run unit tests with `pytest`:
```
$ pytest tests -v
```
(can be parallelized with `-n auto` option, using [`pytest-xdist`](https://github.com/pytest-dev/pytest-xdist) plugin)

To run a single file, specify it directly like this:
```
$ pytest tests/test_bitcoin.py -v
```

## Verifying downloads

Each release file comes with a detached GPG signature (`<file>.asc`), made with
the key in [`pubkeys/wakiyamap.asc`](pubkeys/wakiyamap.asc)
(fingerprint `3155 25E8 11D5 E586 F3CA  C032 9C74 0BEC 897C E499`):

```
$ gpg --import pubkeys/wakiyamap.asc
$ gpg --verify Electrum-MONA-x.y.z.tar.gz.asc Electrum-MONA-x.y.z.tar.gz
```

`Good signature from "wakiyamap ..."` and the fingerprint above mean the file is
the one that was released. (gpg also warns that the key is not certified with a
trusted signature unless you have marked it as trusted; that is expected.)


## Creating Binaries

- [Linux (tarball)](contrib/build-linux/sdist/README.md)
- [Linux (AppImage)](contrib/build-linux/appimage/README.md)
- [macOS](contrib/osx/README.md)
- [Windows](contrib/build-wine/README.md)
- [Android](contrib/android/Readme.md)


## Contributing

Any help testing the software, reporting or fixing bugs, reviewing pull requests
and recent changes, writing tests, or helping with outstanding issues is very welcome.
Implementing new features, or improving/refactoring the codebase, is of course
also welcome, but to avoid wasted effort, especially for larger changes,
we encourage discussing these on the issue tracker or IRC first.

Besides [GitHub](https://github.com/spesmilo/electrum),
most communication about Electrum development happens on IRC, in the
`#electrum` channel on Libera Chat. The easiest way to participate on IRC is
with the web client, [web.libera.chat](https://web.libera.chat/#electrum).

Please improve translations on [Crowdin](https://crowdin.com/project/electrum).
