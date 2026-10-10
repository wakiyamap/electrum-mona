#!/usr/bin/env python3
import json
import asyncio

from electrum_mona.simple_config import SimpleConfig
from electrum_mona.network import filter_version, Network
from electrum_mona.util import create_and_start_event_loop, log_exceptions
from electrum_mona import constants

# testnet?
config = SimpleConfig({'testnet': False})
config.get_selected_chain().set_as_network()

loop, stopping_fut, loop_thread = create_and_start_event_loop()
network = Network(config)
network.start()

@log_exceptions
async def f():
    try:
        peers = await network.get_peers()
        peers = filter_version(peers)
        print(json.dumps(peers, sort_keys=True, indent=4))
    finally:
        stopping_fut.set_result(1)

asyncio.run_coroutine_threadsafe(f(), loop)
while loop_thread.is_alive():
    loop_thread.join(1)
