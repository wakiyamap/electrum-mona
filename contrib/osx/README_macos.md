# Running Electrum from source on macOS (development version)

## Prerequisites

- [brew](https://brew.sh/)
- python3
- git

## Main steps

### 1. Check out the code from GitHub:
```
$ git clone https://github.com/wakiyamap/electrum-mona.git
$ cd electrum-mona
$ git submodule update --init
```

### 2. Prepare for compiling libsecp256k1

To be able to build the `electrum-ecc` package from source
(which is pulled in when installing Electrum in the next step),
you need:
```
$ brew install autoconf automake libtool coreutils
```

### 3. Install Electrum

Run install (this should install the dependencies):
```
$ CFLAGS="-fno-strict-aliasing -DPY_SSIZE_T_CLEAN" python3 -m pip install --user -e ".[gui,crypto]"
```
(the `CFLAGS` are needed to compile the `lyra2re2_hash` dependency correctly, see the main README)

### 4. Run electrum:
```
$ ./run_electrum
```
