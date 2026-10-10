#!/usr/bin/env python3
"""Extend electrum_mona/chains/<net>/checkpoints.json from locally synced headers.

Checkpoints let a new wallet skip downloading and verifying old headers. For
Monacoin each entry is (hash, target) of the LAST header of a 2016-header chunk.

Usage:
  1. Run Electrum-MONA until it is synchronized, then close it.
  2. contrib/mona/make_checkpoints.py [--testnet] [--dir DATADIR]
  3. Review and commit the changed checkpoints.json.

The existing checkpoints are kept as they are and only new ones are appended.
The headers used here were verified (proof-of-work and difficulty) by the wallet
when it downloaded them, but they all came from the servers it was connected to:
compare the last new hash with a node or block explorer you trust before committing.
"""
import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from electrum_mona import constants  # noqa: E402
from electrum_mona.blockchain import BlockchainManager, CHUNK_SIZE  # noqa: E402
from electrum_mona.simple_config import SimpleConfig  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--testnet", action="store_true")
    parser.add_argument("--dir", dest="electrum_path", default=None, help="electrum-mona data directory")
    parser.add_argument("--keep-recent", type=int, default=1, metavar="N",
                        help="do not checkpoint the N most recent complete chunks (default: 1)")
    args = parser.parse_args()

    options = {}
    if args.electrum_path:
        options["electrum_path"] = args.electrum_path
    if args.testnet:
        options["testnet"] = True
        constants.BitcoinTestnet.set_as_network()
    config = SimpleConfig(options)
    net = constants.net

    old = [tuple(cp) for cp in net.CHECKPOINTS]
    chain = BlockchainManager.from_config(config).get_best_chain()
    height = chain.height()
    num_complete_chunks = (height + 1) // CHUNK_SIZE
    num_new = num_complete_chunks - args.keep_recent - len(old)
    print(f"{net.NET_NAME}: local height {height}, {len(old)} checkpoints (up to height {net.max_checkpoint()})")
    if num_new <= 0:
        print("nothing to add. (are the headers synchronized?)")
        return 0

    checkpoints = list(old)
    for index in range(len(old), len(old) + num_new):
        last_height = (index + 1) * CHUNK_SIZE - 1
        header = chain.read_header(last_height)
        if header is None:
            print(f"error: header {last_height} is missing in the local headers file", file=sys.stderr)
            return 1
        checkpoints.append((chain.get_hash(last_height), chain.bits_to_target(header["bits"])))

    path = os.path.join(PROJECT_ROOT, "electrum_mona", "chains", net.NET_NAME, "checkpoints.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(checkpoints, indent=4, sort_keys=True) + "\n")
    last_height = len(checkpoints) * CHUNK_SIZE - 1
    print(f"added {num_new} checkpoints, now up to height {last_height}")
    print(f"last hash, please compare with a trusted source: {checkpoints[-1][0]}")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
