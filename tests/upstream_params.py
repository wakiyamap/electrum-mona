"""Chain parameters of upstream Electrum (Bitcoin), for the test suite.

Almost all test vectors in this directory come from upstream Electrum and are
Bitcoin vectors (addresses, xpubs, transactions, wallet files, ...). They test
logic that Electrum-MONA shares with upstream, so instead of regenerating
thousands of vectors on every release, the test suite runs with the upstream
chain parameters by default (see tests/__init__.py).

What is specific to Monacoin is tested with the real parameters, in
tests/test_monacoin.py, using `monacoin_params()`.

This only covers the chain parameters (electrum_mona/constants.py). Electrum-MONA also
changes constants that upstream tests depend on. Those tests are adapted as follows:
- BIP21 URI scheme: 'bitcoin:' -> 'monacoin:'  (test_util.py, test_payment_identifier.py)
- magic of signed messages: expected signatures  (test_bitcoin.py, test_commands.py)
- proof-of-work, difficulty: Monacoin header in TestVerifyHeader  (test_blockchain.py)
- lightning block counts, e.g. MIN_FINAL_CLTV_DELTA_ACCEPTED: cltv values  (test_lnpeer.py)
- lightning min feerate: the feerates the tests use  (test_lnchannel.py, test_lnwallet.py)
- min relay feerate: tests with vectors that have upstream's feerate baked in run with
  `upstream_relay_feerate()`  (test_wallet_vertical.py, test_fee_policy.py)
"""
import contextlib
from unittest import mock

from electrum_mona import constants
from electrum_mona import fee_policy

_UPSTREAM = {
    constants.BitcoinMainnet: dict(
        WIF_PREFIX=0x80,
        ADDRTYPE_P2PKH=0,
        ADDRTYPE_P2SH=5,
        ADDRTYPE_P2SH_ALT=5,
        SEGWIT_HRP="bc",
        BOLT11_HRP="bc",
        GENESIS="000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
        BLOCK_HEIGHT_FIRST_LIGHTNING_CHANNELS=497000,
        BIP44_COIN_TYPE=0,
    ),
    constants.BitcoinTestnet: dict(
        ADDRTYPE_P2SH=196,
        ADDRTYPE_P2SH_ALT=196,
        SEGWIT_HRP="tb",
        BOLT11_HRP="tb",
        GENESIS="000000000933ea01ad0ee984209779baaec3ced90fa3f408719526f8d77f4943",
    ),
    constants.BitcoinRegtest: dict(
        SEGWIT_HRP="bcrt",
        BOLT11_HRP="bcrt",
        GENESIS="0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206",
    ),
    constants.BitcoinSimnet: dict(
        SEGWIT_HRP="sb",
        BOLT11_HRP="sb",
    ),
    constants.BitcoinSignet: dict(
        BOLT11_HRP="tbs",
    ),
}

_MISSING = object()
# the values the classes have in the shipped code
_MONACOIN = {
    net: {name: net.__dict__.get(name, _MISSING) for name in params}
    for net, params in _UPSTREAM.items()
}


def _apply(table) -> None:
    for net, params in table.items():
        for name, value in params.items():
            if value is _MISSING:
                if name in net.__dict__:
                    delattr(net, name)
            else:
                setattr(net, name, value)


def use_upstream_bitcoin_params() -> None:
    _apply(_UPSTREAM)


def use_monacoin_params() -> None:
    _apply(_MONACOIN)


@contextlib.contextmanager
def monacoin_params():
    """Run a block of test code with the real (shipped) chain parameters."""
    use_monacoin_params()
    try:
        yield
    finally:
        use_upstream_bitcoin_params()


class MonacoinParamsMixin:
    """Mixin for test cases that run with the real (shipped) chain parameters:
        class TestFoo(MonacoinParamsMixin, ElectrumTestCase): ...
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        use_monacoin_params()

    @classmethod
    def tearDownClass(cls):
        use_upstream_bitcoin_params()
        super().tearDownClass()


def upstream_relay_feerate():
    """Decorator / context manager to run a test with the default min relay feerate of upstream.

    For tests of logic we share with upstream (fee bumping, mempool histogram), whose
    vectors (e.g. signed transactions) have that feerate baked in.
    The Monacoin fee constants are tested in tests/test_monacoin.py.
    """
    return mock.patch.object(fee_policy, "FEERATE_DEFAULT_RELAY", 1000)
