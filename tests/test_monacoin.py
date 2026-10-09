"""Tests for what is specific to Electrum-MONA, run with the real (shipped) chain parameters.

Most of the test suite is shared with upstream Electrum and runs with upstream's Bitcoin
parameters, see tests/upstream_params.py.
Proof-of-work and difficulty adjustment are tested in tests/test_blockchain.py and tests/test_scrypt.py.
"""
import base64
import gettext
import os
from unittest import mock

import electrum_ecc as ecc

from electrum_mona import bip21, bitcoin, constants, fee_policy, i18n, keystore, lnchannel, lnrater, lnutil, util
from electrum_mona import submarine_swaps, trampoline
from electrum_mona.bip21 import InvalidBitcoinURI
from electrum_mona.bitcoin import (address_to_script, address_to_payload, address_to_scripthash, is_address,
                                   pubkey_to_address, deserialize_privkey, serialize_privkey, OnchainOutputType,
                                   BitcoinException, COIN)
from electrum_mona.blockchain import hash_raw_header
from electrum_mona.bolt11 import decode_bolt11_invoice, encode_bolt11_invoice, BOLT11Addr, BOLT11DecodeException
from electrum_mona.payment_identifier import PaymentIdentifier
from electrum_mona.simple_config import SimpleConfig
from electrum_mona.version import PROTOCOL_VERSION_MIN

from . import ElectrumTestCase
from .upstream_params import (MonacoinParamsMixin, monacoin_params, use_monacoin_params, use_upstream_bitcoin_params,
                              upstream_relay_feerate)

# one key, in all its encodings. (derived by hand, from the base58 prefixes and bech32 HRPs of Monacoin Core)
WIF = "T8vPbnoUs5CiEBHcnne1wXuR9V5ft16vRpuvqWTH83tFxT8Uacvn"
WIF_UNCOMPRESSED = "6vT9HwnRSPhiWike7J8w8pnQbYjkFGtBkEaHjFq6TyPVK2Fudom"
PUBKEY = "02c555a1f88f30cc7651d1c8ef1639f0c3f73cc149462c209c9fa704a1300cc1d5"
ADDR_P2PKH = "MWLEbTAW61QFdrHtbaV7UdoaHaNjdPUtTj"
ADDR_P2WPKH_P2SH = "PStEWT3ZsRMuwGR47CCgsdRNrM3ERLoxGF"
ADDR_P2WPKH_P2SH_LEGACY = "3Kz5H29ANQC73bSitDYkdMp3P8A4uoJVck"  # same script, with the p2sh version byte of bitcoin
ADDR_P2WPKH = "mona1q7cgva59egg6l4eg64c285rfutmdjfw6nemf9cx"
# the same key on other chains
BITCOIN_WIF = "L368A3WJThE7TLekF9h9jBN3CdSMov62cd1fyhpjZ5i6SZaGdnqc"
BITCOIN_ADDRS = ("1PS5N2G6azESkBKZNbqBENCEpMVa6QLvE9", "bc1q7cgva59egg6l4eg64c285rfutmdjfw6nagl848")
TESTNET_WIF = "cTT7cxW9tkvNcn81dZWH6Vs6prjmUNBigfA968HF4CN6hJeQbPYT"
TESTNET_ADDR_P2PKH = "n3x2f5M5Q1fhXHoB6AoZ4HQZgM6Gx6SrwP"
TESTNET_ADDR_P2WPKH_P2SH = "pPqdZBXRtc6Ee94RdCrSwQJ9sd1iauX38g"
TESTNET_ADDR_P2WPKH_P2SH_LEGACY = "2NBYHLm5ByrhTFP5GZMAdFJoJbUNEeD1ZqK"
TESTNET_ADDR_P2WPKH = "tmona1q7cgva59egg6l4eg64c285rfutmdjfw6npqm6ju"
REGTEST_ADDR_P2WPKH = "rmona1q7cgva59egg6l4eg64c285rfutmdjfw6nlahe75"

BLOCKS_PER_DAY = 24 * 60 * 60 // 90  # one block every 1.5 minutes


def read_chain_file(net_name: str, filename: str):
    # note: not using the cached properties of constants.net: subclasses (e.g. regtest) would inherit the cache
    return constants.read_json(os.path.join("chains", net_name, filename))


class TestParamsOfTheTestSuite(ElectrumTestCase):

    def test_switching_params(self):
        self.assertEqual("bc", constants.BitcoinMainnet.SEGWIT_HRP)
        self.assertEqual(0, constants.BitcoinMainnet.BIP44_COIN_TYPE)
        with monacoin_params():
            self.assertEqual("mona", constants.BitcoinMainnet.SEGWIT_HRP)
            self.assertEqual(22, constants.BitcoinMainnet.BIP44_COIN_TYPE)
            self.assertTrue(is_address(ADDR_P2WPKH))
        self.assertEqual("bc", constants.BitcoinMainnet.SEGWIT_HRP)
        self.assertFalse(is_address(ADDR_P2WPKH))

    def test_upstream_relay_feerate(self):
        with upstream_relay_feerate():
            self.assertEqual(1000, bitcoin.relayfee())
        self.assertEqual(100000, bitcoin.relayfee())


class TestChainParams(MonacoinParamsMixin, ElectrumTestCase):

    def test_net_params(self):
        # base58Prefixes, bech32_hrp and BIP44 coin type (SLIP-0044) of Monacoin
        mainnet, testnet, regtest = constants.BitcoinMainnet, constants.BitcoinTestnet, constants.BitcoinRegtest
        self.assertIs(mainnet, constants.net)
        self.assertEqual((176, 50, 55, 5), (mainnet.WIF_PREFIX, mainnet.ADDRTYPE_P2PKH, mainnet.ADDRTYPE_P2SH, mainnet.ADDRTYPE_P2SH_ALT))
        self.assertEqual(("mona", "mona", 22), (mainnet.SEGWIT_HRP, mainnet.BOLT11_HRP, mainnet.BIP44_COIN_TYPE))
        for net in (testnet, regtest):
            self.assertEqual((239, 111, 117, 196), (net.WIF_PREFIX, net.ADDRTYPE_P2PKH, net.ADDRTYPE_P2SH, net.ADDRTYPE_P2SH_ALT))
            self.assertEqual(1, net.BIP44_COIN_TYPE)
            self.assertTrue(net.TESTNET)
        self.assertEqual(("tmona", "tmona"), (testnet.SEGWIT_HRP, testnet.BOLT11_HRP))
        self.assertEqual(("rmona", "rmona"), (regtest.SEGWIT_HRP, regtest.BOLT11_HRP))
        # xpub/xprv headers are the same as bitcoin's
        self.assertEqual(0x0488b21e, mainnet.XPUB_HEADERS['standard'])
        self.assertEqual(0x04b24746, mainnet.XPUB_HEADERS['p2wpkh'])
        self.assertEqual(0x043587cf, testnet.XPUB_HEADERS['standard'])
        # electrum server ports
        self.assertEqual({'t': '50001', 's': '50002'}, mainnet.DEFAULT_PORTS)
        self.assertEqual({'t': '51001', 's': '51002'}, testnet.DEFAULT_PORTS)

    def test_genesis(self):
        # genesis block headers, built from the arguments of CreateGenesisBlock() in Monacoin Core (chainparams.cpp)
        merkle_root = bytes.fromhex("35e405a8a46f4dbc1941727aaf338939323c3b955232d0317f8731fe07ac4ba6")[::-1]
        for net, timestamp, nonce, bits, genesis_hash in (
                (constants.BitcoinMainnet, 1388479472, 1234534, 0x1e0ffff0, "ff9f1c0116d19de7c9963845e129f9ed1bfc0b376eb54fd7afa42e0d418c8bb6"),
                (constants.BitcoinTestnet, 1488924140, 2122860, 0x1e0ffff0, "a2b106ceba3be0c6d097b2a6a6aacf9d638ba8258ae478158f449c321061e0b2"),
                (constants.BitcoinRegtest, 1296688602, 1, 0x207fffff, "7543a69d7c2fcdb29a5ebec2fc064c074a35253b6f3072c8a749473aa590a29c"),
        ):
            raw_header = (int.to_bytes(1, 4, "little") + bytes(32) + merkle_root
                          + int.to_bytes(timestamp, 4, "little") + int.to_bytes(bits, 4, "little") + int.to_bytes(nonce, 4, "little"))
            self.assertEqual(genesis_hash, hash_raw_header(raw_header))
            self.assertEqual(genesis_hash, net.GENESIS)
            self.assertEqual(bytes.fromhex(genesis_hash)[::-1], net.rev_genesis_bytes())

    def test_checkpoints(self):
        for net_name, net in (("mainnet", constants.BitcoinMainnet), ("testnet", constants.BitcoinTestnet)):
            checkpoints = read_chain_file(net_name, "checkpoints.json")
            self.assertGreater(len(checkpoints), 500, msg=net_name)
            for cp in checkpoints:  # (hash of the last header of the chunk, target of that header)
                block_hash, target = cp
                self.assertEqual(64, len(block_hash))
                bytes.fromhex(block_hash)
                self.assertTrue(0 < target < 2 ** 256)
                self.assertNotEqual(net.GENESIS, block_hash)
        # on mainnet, the targets are the proof-of-work targets of those headers
        checkpoints = constants.BitcoinMainnet.CHECKPOINTS
        self.assertEqual(read_chain_file("mainnet", "checkpoints.json"), checkpoints)
        self.assertEqual(len(checkpoints) * 2016 - 1, constants.BitcoinMainnet.max_checkpoint())
        self.assertGreaterEqual(len(checkpoints), 1299)
        self.assertEqual("92745bac6025d9c384da04a5b25628c647f66a446ed69c0b6c469b4b731c5d61", checkpoints[0][0])  # block 2015
        self.assertEqual("532cb5a56f4c3507cc86f32911ecd0357f84ef8c8ddb51d2ae5da04c9ee0c4e7", checkpoints[1298][0])  # block 2618783
        for block_hash, target in checkpoints:
            self.assertTrue(target <= 0x00000fffffffffffffffffffffffffffffffffffffffffffffffffffffffffff)

    def test_default_servers(self):
        for net_name, default_port in (("mainnet", "50002"), ("testnet", "51002"), ("regtest", "51002")):
            servers = read_chain_file(net_name, "servers.json")
            self.assertTrue(servers, msg=net_name)
            for host, server in servers.items():
                self.assertTrue(host and host == host.strip().lower(), msg=host)
                self.assertTrue("s" in server or "t" in server, msg=host)
                self.assertTrue(all(isinstance(v, str) for v in server.values()), msg=host)
                self.assertTrue(set(server) <= {"pruning", "s", "t", "version"}, msg=host)
                for port in (server.get("s"), server.get("t")):
                    self.assertTrue(port is None or 0 < int(port) < 65536, msg=host)
                # servers below the min protocol version would get filtered out
                self.assertTrue(util.versiontuple(server["version"]) >= util.versiontuple(PROTOCOL_VERSION_MIN))
                self.assertFalse(host.endswith((".electrum.org", ".blockstream.info")))
            self.assertTrue(any(server.get("s") == default_port for server in servers.values()), msg=net_name)
        self.assertEqual(read_chain_file("mainnet", "servers.json"), constants.BitcoinMainnet.DEFAULT_SERVERS)
        self.assertGreaterEqual(len(constants.BitcoinMainnet.DEFAULT_SERVERS), 5)

    def test_fallback_lightning_nodes(self):
        for net_name in ("mainnet", "testnet"):
            nodes = constants.create_fallback_node_list(read_chain_file(net_name, "fallback_lnnodes.json"))
            self.assertTrue(nodes, msg=net_name)
            self.assertEqual(len(nodes), len(set(node.pubkey for node in nodes)))
            for node in nodes:
                ecc.ECPubkey(node.pubkey)  # raises if not a point on the curve
                self.assertEqual(33, len(node.pubkey))
                self.assertTrue(0 < node.port < 65536)
        self.assertEqual(len(read_chain_file("mainnet", "fallback_lnnodes.json")), len(constants.BitcoinMainnet.FALLBACK_LN_NODES))

    def test_hardcoded_trampoline_nodes(self):
        nodes = trampoline.hardcoded_trampoline_nodes()
        self.assertTrue(nodes)
        self.assertIs(trampoline.TRAMPOLINE_NODES_MAINNET, nodes)
        for name, node in nodes.items():
            ecc.ECPubkey(node.pubkey)
            self.assertNotIn("electrum.org", node.host)
            self.assertNotIn("acinq", node.host)

    def test_block_explorers(self):
        config = SimpleConfig({'electrum_path': self.electrum_path})
        self.assertIn(config.BLOCK_EXPLORER, util.mainnet_block_explorers)
        txid = "00" * 32
        self.assertEqual(f"https://blockbook.electrum-mona.org/tx/{txid}", util.block_explorer_URL(config, kind='tx', item=txid))
        self.assertEqual(f"https://blockbook.electrum-mona.org/address/{ADDR_P2PKH}", util.block_explorer_URL(config, kind='addr', item=ADDR_P2PKH))
        for name, (url, parts) in list(util.mainnet_block_explorers.items()) + list(util.testnet_block_explorers.items()):
            self.assertEqual({'tx', 'addr'}, set(parts), msg=name)
            self.assertNotIn("bitcoin", url)
            self.assertNotIn("btc", url)

    def test_nostr_swap_namespace(self):
        # must not be upstream's "net:mainnet": bitcoin swap servers announce themselves there
        self.assertEqual("net:monacoin-mainnet", submarine_swaps.nostr_network_tag())
        with mock.patch.object(constants, "net", constants.BitcoinTestnet):
            self.assertEqual("net:monacoin-testnet", submarine_swaps.nostr_network_tag())
        for net in constants.NETS_LIST:
            with mock.patch.object(constants, "net", net):
                self.assertNotEqual("net:" + net.NET_NAME, submarine_swaps.nostr_network_tag())
        self.assertFalse(submarine_swaps.SUBMARINE_SWAPS_AVAILABLE)


class TestAddresses(MonacoinParamsMixin, ElectrumTestCase):

    def test_wif(self):
        txin_type, secret, compressed = deserialize_privkey(WIF)
        self.assertEqual(("p2pkh", True), (txin_type, compressed))
        self.assertEqual(PUBKEY, ecc.ECPrivkey(secret).get_public_key_hex(compressed=True))
        self.assertEqual("p2pkh:" + WIF, serialize_privkey(secret, True, "p2pkh"))
        self.assertEqual(WIF, serialize_privkey(secret, True, "p2pkh", internal_use=True))
        self.assertEqual(WIF_UNCOMPRESSED, serialize_privkey(secret, False, "p2pkh", internal_use=True))
        self.assertEqual(("p2pkh", secret, False), deserialize_privkey(WIF_UNCOMPRESSED))
        self.assertEqual(("p2wpkh", secret, True), deserialize_privkey("p2wpkh:" + WIF))
        self.assertTrue(bitcoin.is_private_key(WIF))
        self.assertTrue(bitcoin.is_private_key("p2wpkh-p2sh:" + WIF))
        # keys of other chains
        for wif in (BITCOIN_WIF, TESTNET_WIF):
            self.assertFalse(bitcoin.is_private_key(wif))
            with self.assertRaises(BitcoinException):
                deserialize_privkey(wif)

    def test_address_from_key(self):
        self.assertEqual(ADDR_P2PKH, pubkey_to_address("p2pkh", PUBKEY))
        self.assertEqual(ADDR_P2WPKH_P2SH, pubkey_to_address("p2wpkh-p2sh", PUBKEY))
        self.assertEqual(ADDR_P2WPKH, pubkey_to_address("p2wpkh", PUBKEY))
        self.assertEqual(ADDR_P2PKH, bitcoin.address_from_private_key(WIF))
        self.assertEqual(ADDR_P2WPKH_P2SH, bitcoin.address_from_private_key("p2wpkh-p2sh:" + WIF))
        self.assertEqual(ADDR_P2WPKH, bitcoin.address_from_private_key("p2wpkh:" + WIF))
        for addr in (ADDR_P2PKH, ADDR_P2WPKH_P2SH, ADDR_P2WPKH):
            self.assertTrue(is_address(addr))
            self.assertEqual(addr, bitcoin.script_to_address(address_to_script(addr)))
        self.assertTrue(bitcoin.is_b58_address(ADDR_P2PKH))
        self.assertTrue(bitcoin.is_segwit_address(ADDR_P2WPKH))
        self.assertTrue(bitcoin.is_segwit_address(ADDR_P2WPKH.upper()))

    def test_key_import_vectors(self):
        # from Electrum-MONA 4.2.1. (privkey, pubkey, txin_type, address, scripthash)
        for privkey, pubkey, txin_type, address, scripthash in (
                ("T9ZV9h1ZkYfgh2E2h5CZbEzrc32nz3uK2KjhA1Amu7JzNo99YGxg",
                 "0251ce5368b2ac47b6e7fb7222c1180ea0012e4891b56cefb8d9d187bc7ad11659", "p2pkh",
                 "MN3qk8taHHcLp52tf6v9V4CyfiJuCpwz4B", "33c5367b611c9183b2eedf0a32de2fa57f399f75e6b884fdaaf95a655f706d7c"),
                ("p2wpkh-p2sh:T51dkWnz7Ay9iecN4S5TvmcasreVXBbCaYoXHJ5h6uAYXpM8MGDS",
                 "0273a3c1bd660286dc632400f8ecaaf9d782b8941e0cc5e1bc73308e658510021c", "p2wpkh-p2sh",
                 "PN7E5z6oUHf6aQQivCmmn8haFe6FtYshAJ", "8945b92543e13adc7c3d35d2be7924c00a125a25741f15fe5df8275a7c15cd42"),
                ("p2wpkh:T8a4cDwcDBCe7XnbULMWTFF2JS3ZduMPiQ7n2TafyZXN3dAqzEg5",
                 "03b9ace321eddd5037f35bc141a9f6cbd54d5064b917da1ef02e1b575f410f5e11", "p2wpkh",
                 "mona1quunc907zfyj7cyxhnp9584rj0wmdka2ec9w3af", "bdd0b86d7c9290b25b8528f01739358445cd9d050e8aef8099eb74f8e34db082"),
                ("p2pkh:6vtsDUCgu6yHGBaa92x4skmZHa2LmMz4sNuh54tUhqJFELE28eh",  # uncompressed
                 "04588d202afcc1ee4ab5254c7847ec25b9a135bbda0f2bc69ee1a714749fd77dc9f88ff2a00d7e752d44cbe16e1ebcf0890b76ec7c78886109dee76ccfc8445424", "p2pkh",
                 "MK6CkTbJa9nuqCSqaeKmAFyUmPYd1rWS6Q", "5b07ddfde826f5125ee823900749103cea37808038ecead5505a766a07c34445"),
        ):
            self.assertEqual(txin_type, deserialize_privkey(privkey)[0])
            self.assertEqual(address, bitcoin.address_from_private_key(privkey))
            self.assertEqual(address, pubkey_to_address(txin_type, pubkey))
            self.assertEqual(scripthash, address_to_scripthash(address))
            self.assertTrue(is_address(address))

    def test_address_to_script(self):
        # from Electrum-MONA 4.2.1
        # base58 P2PKH
        self.assertEqual(address_to_script('MBamfEqEFDy5dsLWwu48BCizM1zpCoKw3U').hex(), '76a91428662c67561b95c79d2257d2a93d9d151c977e9188ac')
        self.assertEqual(address_to_script('MVELZC3ks1Xk59kvKWuSN3mpByNwaxeaBJ').hex(), '76a914e9fb298e72e29ebc2b89864a5e4ae10e0b84726088ac')
        # base58 P2SH
        self.assertEqual(address_to_script('PCTzdjWauNipkYtToRZEHDMXb2adj9Evp8').hex(), 'a9142a84cf00d47f699ee7bbc1dea5ec1bdecb4ac15487')
        self.assertEqual(address_to_script('PHjTKtgYLTJ9D2Bzw2f6xBB41KBm2HeGfg').hex(), 'a9146449f568c9cd2378138f2636e1567112a184a9e887')
        # base58 P2SH, old version byte
        self.assertEqual(address_to_script('3AqJ6Tn8qS8LKMDfi41AhuZiY6JbR6mt6E').hex(), 'a9146449f568c9cd2378138f2636e1567112a184a9e887')
        # bech32 / bech32m. (the witness programs of the BIP-0173 and BIP-0350 examples)
        self.assertEqual(address_to_script('mona1qw508d6qejxtdg4y5r3zarvary0c5xw7kg5lnx5').hex(), '0014751e76e8199196d454941c45d1b3a323f1433bd6')
        self.assertEqual(address_to_script('mona1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3q37swge').hex(), '00201863143c14c5166804bd19203356da136c985678cd4d27a1b8c6329604903262')
        self.assertEqual(address_to_script('mona1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqtsd8k8').hex(), '512079be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798')
        self.assertEqual(address_to_payload('mona1p5cyxnuxmeuwuvkwfem96lqzszd02n6xdcjrs20cac6yqjjwudpxqll5kut'),
                         (OnchainOutputType.WITVER1_P2TR, bytes.fromhex('a60869f0dbcf1dc659c9cecbaf8050135ea9e8cdc487053f1dc6880949dc684c')))
        self.assertEqual(address_to_payload('MBamfEqEFDy5dsLWwu48BCizM1zpCoKw3U'),
                         (OnchainOutputType.P2PKH, bytes.fromhex('28662c67561b95c79d2257d2a93d9d151c977e91')))
        self.assertEqual(address_to_payload('PCTzdjWauNipkYtToRZEHDMXb2adj9Evp8'),
                         (OnchainOutputType.P2SH, bytes.fromhex('2a84cf00d47f699ee7bbc1dea5ec1bdecb4ac154')))

    def test_legacy_p2sh_version_byte(self):
        """Monacoin used to share the p2sh version byte (5) with bitcoin. Such addresses are still
        accepted, but we only create the new form (55)."""
        for legacy_addr, addr in ((ADDR_P2WPKH_P2SH_LEGACY, ADDR_P2WPKH_P2SH),
                                  ("3AqJ6Tn8qS8LKMDfi41AhuZiY6JbR6mt6E", "PHjTKtgYLTJ9D2Bzw2f6xBB41KBm2HeGfg")):
            version, h160 = bitcoin.b58_address_to_hash160(legacy_addr)
            self.assertEqual(5, version)
            self.assertEqual((55, h160), bitcoin.b58_address_to_hash160(addr))
            self.assertTrue(is_address(legacy_addr))
            self.assertTrue(bitcoin.is_b58_address(legacy_addr))
            self.assertEqual(address_to_script(addr), address_to_script(legacy_addr))
            self.assertEqual((OnchainOutputType.P2SH, h160), address_to_payload(legacy_addr))
            self.assertEqual(address_to_scripthash(addr), address_to_scripthash(legacy_addr))
            self.assertEqual(addr, bitcoin.script_to_address(address_to_script(legacy_addr)))
            self.assertEqual(addr, bitcoin.hash160_to_p2sh(h160))

    def test_addresses_of_other_chains_are_rejected(self):
        for addr in BITCOIN_ADDRS + (TESTNET_ADDR_P2PKH, TESTNET_ADDR_P2WPKH_P2SH, TESTNET_ADDR_P2WPKH_P2SH_LEGACY,
                                     TESTNET_ADDR_P2WPKH, REGTEST_ADDR_P2WPKH,
                                     "Lhf2dEZvfeUVzz1iYjpUWPG12ZrrCKLuUW", "ltc1q7cgva59egg6l4eg64c285rfutmdjfw6ne59rdh",  # litecoin
                                     "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4",  # BIP-0173
                                     ADDR_P2PKH[:-1] + "k", ADDR_P2WPKH[:-1] + "q"):  # bad checksums
            self.assertFalse(is_address(addr), msg=addr)
            with self.assertRaises(BitcoinException, msg=addr):
                address_to_script(addr)

    def test_bip44_derivation_paths(self):
        self.assertEqual("m/44h/22h/0h", keystore.bip44_derivation(0))
        self.assertEqual("m/49h/22h/1h", keystore.bip44_derivation(1, bip43_purpose=49))
        self.assertEqual("m/84h/22h/0h", keystore.bip44_derivation(0, bip43_purpose=84))
        self.assertEqual("m/48h/22h/0h/2h", keystore.purpose48_derivation(0, xtype='p2wsh'))
        self.assertEqual("m/48h/22h/3h/1h", keystore.purpose48_derivation(3, xtype='p2wsh-p2sh'))

    def test_bip39_seed_vectors(self):
        # from Electrum-MONA 4.2.1. (seed, purpose, xpub, first receiving address, first change address)
        for seed_words, purpose, xpub, receiving_addr, change_addr in (
                ("treat dwarf wealth gasp brass outside high rent blood crowd make initial", 44,
                 "xpub6DUwZjQbaHiStmZ3Ej2trwkFuGgdyKkH652CiKo9bwVnWkssPCdspefzgJtxsZd9TnxUHnrADeNMhx22G9io7DwnMh3HdEWSxt6jAbaH5Zp",
                 "MS5xvLi9MztCEBdct5TaGWBxgbxkbdKioY", "MU8uE2nH1pkVt7outQMjki68do5Pp6gzK7"),
                ("treat dwarf wealth gasp brass outside high rent blood crowd make initial", 49,
                 "ypub6XD1EFz3nkRq9x2Zw9P6cFeHqHFx63vfiocG2BEzVSSDnfgx2BEWFLSfPy6qxQAESUApw5zQejoSPorqxzoV4y2rDnrVzuR93GcUxar2BBf",
                 "PNh2J16Tz4pcKfiJ7MBjD2b7o5kvPdSYcd", "PFiGomM32uDKXXcEs1LM57GpasTorJnb7J"),
                ("abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about", 84,
                 "zpub6qYRea3CaywxYtfvnmEck21cWJH1fR1NLZVUm1YGnhjL87kr9aLnHSGGumibCJWR9SswtGCuK15Z57WC18oJzkAhZXCTcWTcdHJMfbydrok",
                 "mona1qpgmk2vdx5ve6xm93rplw9d6uszpe4am5my7x72", "mona1q7t5p3u22skphsflmxnta7tjw8kspf7s35q793e"),
        ):
            root_seed = keystore.bip39_to_seed(seed_words, passphrase='')
            ks = keystore.from_bip43_rootseed(root_seed, derivation=keystore.bip44_derivation(0, bip43_purpose=purpose))
            txin_type = {44: 'p2pkh', 49: 'p2wpkh-p2sh', 84: 'p2wpkh'}[purpose]
            self.assertEqual(xpub, ks.xpub)
            self.assertEqual(receiving_addr, pubkey_to_address(txin_type, ks.derive_pubkey(0, 0).hex()))
            self.assertEqual(change_addr, pubkey_to_address(txin_type, ks.derive_pubkey(1, 0).hex()))


class TestAddressesTestnet(MonacoinParamsMixin, ElectrumTestCase):
    TESTNET = True

    def test_addresses(self):
        self.assertEqual(("p2pkh", True), deserialize_privkey(TESTNET_WIF)[0::2])
        self.assertEqual(deserialize_privkey(TESTNET_WIF)[1].hex(), "af1f1aa9ce6a9a8d60fb27883fce28bd12773f1ac3d6179b54f56cc6d09c4b4d")
        self.assertEqual(TESTNET_ADDR_P2PKH, pubkey_to_address("p2pkh", PUBKEY))
        self.assertEqual(TESTNET_ADDR_P2WPKH_P2SH, pubkey_to_address("p2wpkh-p2sh", PUBKEY))
        self.assertEqual(TESTNET_ADDR_P2WPKH, pubkey_to_address("p2wpkh", PUBKEY))
        # legacy p2sh version byte (196)
        self.assertTrue(is_address(TESTNET_ADDR_P2WPKH_P2SH_LEGACY))
        self.assertEqual(address_to_script(TESTNET_ADDR_P2WPKH_P2SH), address_to_script(TESTNET_ADDR_P2WPKH_P2SH_LEGACY))
        self.assertEqual(TESTNET_ADDR_P2WPKH_P2SH, bitcoin.script_to_address(address_to_script(TESTNET_ADDR_P2WPKH_P2SH_LEGACY)))
        for addr in (ADDR_P2PKH, ADDR_P2WPKH_P2SH, ADDR_P2WPKH_P2SH_LEGACY, ADDR_P2WPKH, REGTEST_ADDR_P2WPKH,
                     "tb1q7cgva59egg6l4eg64c285rfutmdjfw6nhwy5w5"):
            self.assertFalse(is_address(addr), msg=addr)
        with self.assertRaises(BitcoinException):
            deserialize_privkey(WIF)

    def test_address_to_script(self):
        # from Electrum-MONA 4.2.1
        self.assertEqual(address_to_script('mutXcGt1CJdkRvXuN2xoz2quAAQYQ59bRX').hex(), '76a9149da64e300c5e4eb4aaffc9c2fd465348d5618ad488ac')
        self.assertEqual(address_to_script('pFdo9GVwppdH2Rc22XiNgk7WKb5Qgihit9').hex(), 'a9146eae23d8c4a941316017946fc761a7a6c85561fb87')
        self.assertEqual(address_to_script('tmona1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3qwlyd0j').hex(), '00201863143c14c5166804bd19203356da136c985678cd4d27a1b8c6329604903262')

    def test_bip44_derivation_paths(self):
        self.assertEqual("m/44h/1h/0h", keystore.bip44_derivation(0))
        self.assertEqual("m/84h/1h/0h", keystore.bip44_derivation(0, bip43_purpose=84))


class TestAddressesRegtest(MonacoinParamsMixin, ElectrumTestCase):
    REGTEST = True

    def test_addresses(self):
        self.assertEqual(REGTEST_ADDR_P2WPKH, pubkey_to_address("p2wpkh", PUBKEY))
        self.assertEqual(TESTNET_ADDR_P2PKH, pubkey_to_address("p2pkh", PUBKEY))
        self.assertEqual(TESTNET_ADDR_P2WPKH_P2SH, pubkey_to_address("p2wpkh-p2sh", PUBKEY))
        self.assertFalse(is_address(TESTNET_ADDR_P2WPKH))
        self.assertFalse(is_address(ADDR_P2WPKH))
        self.assertFalse(is_address("bcrt1q7cgva59egg6l4eg64c285rfutmdjfw6n48aeea"))


class TestSignedMessages(MonacoinParamsMixin, ElectrumTestCase):

    @staticmethod
    def sign_message_with_wif_privkey(wif_privkey: str, msg: bytes) -> bytes:
        txin_type, privkey, compressed = deserialize_privkey(wif_privkey)
        return bitcoin.ecdsa_sign_usermessage(ecc.ECPrivkey(privkey), msg, is_compressed=compressed)

    def test_magic(self):
        # strMessageMagic of Monacoin Core, as a varstr
        self.assertEqual(b"\x19Monacoin Signed Message:\n" + b"\x05hello", bitcoin.usermessage_magic(b"hello"))
        self.assertEqual(0x19, len("Monacoin Signed Message:\n"))

    def test_vectors(self):
        # from Electrum-MONA 4.2.1. (wif, message, address, signature)
        for wif, msg, addr, sig_b64 in (
                ("T8UqLXgii9iBbQAoypL8Yz7Zta7w8QTt2qq66ViLSGXGQCGbo7rv", b"wakiyama tamami chan", "MRHx4jW2KAQeEDMuK7pGLUGWvPRQT1Epmj",
                 b"IDldTozCVViZ/m/gzvSf6EmZZ3ItDdM+RsI4PAxZdsb6ZQUmv3IgaJK+U4naOExaoTIVn0IY3Hoky0MWFAO6ac4="),
                ("T3o9vVd82bASRouYDpSHo2KyFR82LB7FezpZAFDpLcbNd7AGuEJQ", b"tottemo kawaii", "MLBCmvG4A7AqCD6MMYjf7YdV96YK5teZ5N",
                 b"IC6PcfKrJQUOZwh6Sju7KAskJKwy4DOnzS3z7A9LjGVrCjd+eZBpXnGbdi+FyyrrFJUEr0MX02QJ1ItpQz7CFvw="),
                ("p2wpkh-p2sh:TAt5frgGHxMZiYKviCxi37CdSrjLbuGVBTgTGnwMnVoFMKoizj4H", b"Electrum", "PXikqAhHK3Ydns9LopVn2pb7Bk892QRWeR",
                 b"IAH8arEFZYY4HmtZRGV3XsLS8epctDsXqPW0jzPXYJmBP0vMoh1ygPolVyNpiPtzgPwHAydMla40bER/7dkmfEY="),
                ("p2wpkh:TAt5frgGHxMZiYKviCxi37CdSrjLbuGVBTgTGnwMnVoFMKoizj4H", b"Electrum", "mona1q9pkhef4x27qkemkmjrhvk7h73umpmgu5tgkszz",
                 b"IAH8arEFZYY4HmtZRGV3XsLS8epctDsXqPW0jzPXYJmBP0vMoh1ygPolVyNpiPtzgPwHAydMla40bER/7dkmfEY="),
        ):
            sig = self.sign_message_with_wif_privkey(wif, msg)
            self.assertEqual(sig_b64, base64.b64encode(sig))
            self.assertEqual(addr, bitcoin.address_from_private_key(wif))
            self.assertTrue(bitcoin.verify_usermessage_with_address(addr, sig, msg))
            self.assertFalse(bitcoin.verify_usermessage_with_address(addr, sig, msg + b"!"))
            self.assertFalse(bitcoin.verify_usermessage_with_address(ADDR_P2PKH, sig, msg))

    def test_signature_with_the_bitcoin_magic_is_rejected(self):
        # vector from upstream Electrum: same key and message, signed with "Bitcoin Signed Message:\n"
        wif_bitcoin = "L1TnU2zbNaAqMoVh65Cyvmcjzbrj41Gs9iTLcWbpJCMynXuap6UN"
        msg = b"Chancellor on brink of second bailout for banks"
        sig_bitcoin = base64.b64decode(b"Hzsu0U/THAsPz/MSuXGBKSULz2dTfmrg1NsAhFp+wH5aKfmX4Db7ExLGa7FGn0m6Mf43KsbEOWpvUUUBTM3Uusw=")
        with mock.patch.object(constants.net, "WIF_PREFIX", 0x80):
            _, privkey, compressed = deserialize_privkey(wif_bitcoin)
        addr = pubkey_to_address("p2pkh", ecc.ECPrivkey(privkey).get_public_key_hex(compressed=compressed))
        self.assertFalse(bitcoin.verify_usermessage_with_address(addr, sig_bitcoin, msg))
        sig = bitcoin.ecdsa_sign_usermessage(ecc.ECPrivkey(privkey), msg, is_compressed=compressed)
        self.assertTrue(bitcoin.verify_usermessage_with_address(addr, sig, msg))
        self.assertNotEqual(sig_bitcoin, sig)


class TestPaymentURIs(MonacoinParamsMixin, ElectrumTestCase):

    def test_bip21_roundtrip(self):
        uri = bip21.create_bip21_uri(ADDR_P2PKH, 150_000_000, "tea time")
        self.assertEqual(f"monacoin:{ADDR_P2PKH}?amount=1.5&message=tea%20time", uri)
        self.assertEqual({'address': ADDR_P2PKH, 'amount': 150_000_000, 'message': 'tea time', 'memo': 'tea time'},
                         bip21.parse_bip21_URI(uri))
        self.assertEqual(f"monacoin:{ADDR_P2WPKH}", bip21.create_bip21_uri(ADDR_P2WPKH, None, None))
        self.assertEqual({'address': ADDR_P2WPKH}, bip21.parse_bip21_URI(f"MONACOIN:{ADDR_P2WPKH}"))
        self.assertEqual({'address': ADDR_P2WPKH_P2SH_LEGACY}, bip21.parse_bip21_URI(f"monacoin:{ADDR_P2WPKH_P2SH_LEGACY}"))
        self.assertEqual({'address': ADDR_P2PKH}, bip21.parse_bip21_URI(ADDR_P2PKH))
        self.assertEqual("", bip21.create_bip21_uri(BITCOIN_ADDRS[0], None, None))

    def test_bip21_rejects_bitcoin(self):
        for uri in (f"bitcoin:{ADDR_P2PKH}", f"bitcoin:{BITCOIN_ADDRS[0]}", f"monacoin:{BITCOIN_ADDRS[0]}",
                    f"monacoin:{BITCOIN_ADDRS[1]}", f"mona:{ADDR_P2PKH}", BITCOIN_ADDRS[0]):
            with self.assertRaises(InvalidBitcoinURI, msg=uri):
                bip21.parse_bip21_URI(uri)

    def test_bip21_amount_is_limited_by_the_coin_supply(self):
        self.assertEqual(105_120_000, bitcoin.TOTAL_COIN_SUPPLY_LIMIT_IN_BTC)
        self.assertEqual(105_120_000 * COIN, bip21.parse_bip21_URI(f"monacoin:{ADDR_P2PKH}?amount=105120000")['amount'])
        with self.assertRaises(InvalidBitcoinURI):
            bip21.parse_bip21_URI(f"monacoin:{ADDR_P2PKH}?amount=105120000.00000001")

    def test_payment_identifier(self):
        pi = PaymentIdentifier(None, f"monacoin:{ADDR_P2WPKH}?amount=0.5&message=unit_test")
        self.assertTrue(pi.is_valid())
        self.assertTrue(pi.is_onchain())
        self.assertEqual(ADDR_P2WPKH, pi.bip21['address'])
        self.assertTrue(PaymentIdentifier(None, ADDR_P2WPKH_P2SH).is_valid())
        for text in (f"bitcoin:{ADDR_P2WPKH}", f"bitcoin:{BITCOIN_ADDRS[1]}", BITCOIN_ADDRS[0]):
            self.assertFalse(PaymentIdentifier(None, text).is_valid(), msg=text)

    def test_bolt11_hrp(self):
        payment_hash, payment_secret = bytes(range(32)), bytes(32)
        node_key = bytes.fromhex("e126f68f7eafcc8b74f54d269fe206be715000f94dac067d1c04a8ca3b2db734")  # from BOLT-11
        for net, prefix in ((constants.BitcoinMainnet, "lnmona"), (constants.BitcoinTestnet, "lntmona"),
                            (constants.BitcoinRegtest, "lnrmona"), (constants.BitcoinSignet, "lntmonas")):
            lnaddr = BOLT11Addr(paymenthash=payment_hash, amount=None, net=net, date=1700000000, payment_secret=payment_secret,
                                tags=[('d', 'coffee beans'), ('9', lnutil.LnFeatures.PAYMENT_SECRET_OPT)])
            invoice = encode_bolt11_invoice(lnaddr, node_key)
            self.assertTrue(invoice.startswith(prefix + "1"), msg=invoice)
            decoded = decode_bolt11_invoice(invoice, net=net)
            self.assertIs(net, decoded.net)
            self.assertEqual(payment_hash, decoded.paymenthash)
        # an invoice of another network
        with self.assertRaises(BOLT11DecodeException):
            decode_bolt11_invoice(invoice, net=constants.BitcoinMainnet)

    def test_bolt11_decode(self):
        # from Electrum-MONA 4.2.1. (a BOLT-11 example, re-encoded for "lnmona")
        invoice = ("lnmona25m1pvjluezpp5qqqsyqcyq5rqwzqfqqqsyqcyq5rqwzqfqqqsyqcyq5rqwzqfqypqdq5vdhkven9v5sxyetpdees9qzszsp5zyg3zyg3zy"
                   "g3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zygsw78e7nnjh75hssadjykhm85834l3q4juymunsryzewwhy43kaaeprmxnn4w8uvmpem"
                   "60flrcpxr4sey558yrh2lwgdhv4z5a4lculqgqm5ng34")
        lnaddr = decode_bolt11_invoice(invoice)
        self.assertIs(constants.BitcoinMainnet, lnaddr.net)
        self.assertEqual(2_500_000, lnaddr.get_amount_sat())
        self.assertEqual("coffee beans", lnaddr.get_description())
        self.assertEqual("0001020304050607080900010203040506070809000102030405060708090102", lnaddr.paymenthash.hex())
        self.assertEqual("03e7156ae33b0a208d0744199163177e909e80176e55d97a2f221ede0f934dd9ad", lnaddr.pubkey.serialize().hex())
        # an invoice for bitcoin. (from tests/test_bolt11.py)
        invoice = ("lnbc25m1pvjluezpp5qqqsyqcyq5rqwzqfqqqsyqcyq5rqwzqfqqqsyqcyq5rqwzqfqypqsp5zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zy"
                   "g3zygsdq5vdhkven9v5sxyetpdees9qypqsztrz5v3jfnxskfv7g8chmyzyrfhf2vupcavuq5rce96kyt6g0zh337h206awccwp335zarqrud4wc"
                   "cgdn39vur44d8um4hmgv06aj0sgpdrv73z")
        with self.assertRaisesRegex(BOLT11DecodeException, "Wrong Lightning invoice HRP bc25m, should be mona"):
            decode_bolt11_invoice(invoice)
        use_upstream_bitcoin_params()
        try:
            self.assertEqual(2_500_000, decode_bolt11_invoice(invoice).get_amount_sat())
        finally:
            use_monacoin_params()


class TestUnits(MonacoinParamsMixin, ElectrumTestCase):

    def test_base_units(self):
        self.assertEqual({'MONA': 8, 'mMona': 5, 'bits': 2, 'sat': 0}, util.base_units)
        self.assertEqual(['MONA', 'mMona', 'bits', 'sat'], util.base_units_list)
        self.assertEqual(8, util.DECIMAL_POINT_DEFAULT)
        self.assertEqual("MONA", util.decimal_point_to_base_unit_name(8))
        self.assertEqual(5, util.base_unit_name_to_decimal_point("mMona"))
        with self.assertRaises(util.UnknownBaseUnit):
            util.base_unit_name_to_decimal_point("BTC")
        with self.assertRaises(util.UnknownBaseUnit):
            util.base_unit_name_to_decimal_point("mBTC")

    def test_config_defaults(self):
        config = SimpleConfig({'electrum_path': self.electrum_path})
        self.assertEqual("MONA", config.get_base_unit())
        self.assertEqual(8, config.BTC_AMOUNTS_DECIMAL_POINT)
        self.assertEqual("1.23456789 MONA", config.format_amount_and_units(123456789))
        config.set_base_unit("mMona")
        self.assertEqual("1234.56789 mMona", config.format_amount_and_units(123456789))
        self.assertEqual("JPY", config.FX_CURRENCY)

    def test_user_dir(self):
        with mock.patch.dict(os.environ, {"HOME": "/home/user"}), mock.patch.object(os, "name", "posix"):
            os.environ.pop("ELECTRUMDIR", None)
            os.environ.pop("ANDROID_DATA", None)
            self.assertEqual("/home/user/.electrum-mona", util.user_dir())


class TestFeeRates(MonacoinParamsMixin, ElectrumTestCase):

    def test_relay_feerate(self):
        # sat/kvB. The min relay feerate we assume is 0.001 MONA/kvB, 100x upstream's.
        self.assertEqual(100_000, fee_policy.FEERATE_DEFAULT_RELAY)
        self.assertEqual(100_000, bitcoin.relayfee())
        # what the server says is only trusted within limits
        network = mock.Mock()
        for server_feerate, feerate in ((None, 100_000), (1000, 1000), (200_000, 200_000), (1, 100), (10 ** 9, 500_000)):
            network.relay_fee = server_feerate
            self.assertEqual(feerate, bitcoin.relayfee(network))
        # lightning: sat/kw
        self.assertEqual(25_300, fee_policy.FEERATE_PER_KW_MIN_RELAY_LIGHTNING)
        self.assertGreaterEqual(fee_policy.FEERATE_PER_KW_MIN_RELAY_LIGHTNING * 4, fee_policy.FEERATE_DEFAULT_RELAY)

    def test_feerate_constants_are_consistent(self):
        self.assertTrue(fee_policy.FEERATE_MIN_RELAY <= fee_policy.FEERATE_DEFAULT_RELAY <= fee_policy.FEERATE_MAX_RELAY)
        self.assertTrue(fee_policy.FEERATE_DEFAULT_RELAY < fee_policy.FEERATE_FALLBACK_STATIC_FEE <= fee_policy.FEERATE_MAX_DYNAMIC)
        self.assertEqual(sorted(set(fee_policy.FEERATE_STATIC_VALUES)), fee_policy.FEERATE_STATIC_VALUES)
        self.assertIn(fee_policy.FEERATE_DEFAULT_RELAY, fee_policy.FEERATE_STATIC_VALUES)
        self.assertLessEqual(fee_policy.FEERATE_STATIC_VALUES[-1], fee_policy.FEERATE_MAX_DYNAMIC)

    def test_dynamic_feerates_are_clamped(self):
        mempool_fees = fee_policy.FeeHistogram()
        # as in Electrum-MONA 4.2.1: a mempool that only has "cheap" txs. (the histogram is in sat/vB)
        mempool_fees.set_data([[49, 100110], [10, 121301], [6, 153731], [5, 125872], [1, 36488810]])
        for depth in (1000000, 500000, 250000, 200000, 100000):
            self.assertEqual(100 * 1000, mempool_fees.depth_target_to_fee(depth))
        mempool_fees.set_data([])
        self.assertEqual(100 * 1000, mempool_fees.depth_target_to_fee(10 ** 5))
        # feerates between the limits are used as they are (+ 1 sat/vB)
        mempool_fees.set_data([[250, 10 ** 7]])
        self.assertEqual(251 * 1000, mempool_fees.depth_target_to_fee(10 ** 5))
        mempool_fees.set_data([[5000, 10 ** 7]])
        self.assertEqual(fee_policy.FEERATE_MAX_DYNAMIC, mempool_fees.depth_target_to_fee(10 ** 5))
        self.assertEqual(1_000_000, fee_policy.FEERATE_MAX_DYNAMIC)
        # eta estimates, as sent by servers
        estimates = fee_policy.FeeTimeEstimates()
        estimates.set_data(2, 2000)
        estimates.set_data(5, 300_000)
        estimates.set_data(10, 50_000_000)
        self.assertEqual(100_000, estimates.eta_target_to_fee(2))
        self.assertEqual(300_000, estimates.eta_target_to_fee(5))
        self.assertEqual(1_000_000, estimates.eta_target_to_fee(10))


class TestLightningParams(MonacoinParamsMixin, ElectrumTestCase):

    def test_block_counts_are_scaled_to_the_block_interval(self):
        """Upstream's constants assume 144 blocks per day. Monacoin has 960."""
        self.assertEqual(960, BLOCKS_PER_DAY)
        self.assertEqual(1 * BLOCKS_PER_DAY, lnutil.MIN_FINAL_CLTV_DELTA_ACCEPTED)
        self.assertEqual(BLOCKS_PER_DAY // 2, lnutil.NBLOCK_DEADLINE_DELTA_BEFORE_EXPIRY_FOR_RECEIVED_HTLCS)
        self.assertEqual(28 * BLOCKS_PER_DAY, lnutil.NBLOCK_CLTV_DELTA_TOO_FAR_INTO_FUTURE)
        self.assertEqual(14 * BLOCKS_PER_DAY, lnutil.MAXIMUM_REMOTE_TO_SELF_DELAY_ACCEPTED)
        self.assertEqual(14 * BLOCKS_PER_DAY, lnutil.CHANNEL_OPENING_TIMEOUT_BLOCKS)
        self.assertEqual(lnutil.CHANNEL_OPENING_TIMEOUT_SEC, lnutil.CHANNEL_OPENING_TIMEOUT_BLOCKS * 90)
        self.assertEqual(1 * BLOCKS_PER_DAY, lnchannel.Channel.forwarding_cltv_delta)
        self.assertEqual(30 * BLOCKS_PER_DAY, lnrater.MONTH_IN_BLOCKS)
        # an htlc we just accepted must not be close to the deadline for going on-chain already
        self.assertLess(lnutil.NBLOCK_DEADLINE_DELTA_BEFORE_EXPIRY_FOR_RECEIVED_HTLCS, lnutil.MIN_FINAL_CLTV_DELTA_ACCEPTED)
        self.assertLess(lnutil.MIN_FINAL_CLTV_DELTA_ACCEPTED, lnutil.NBLOCK_CLTV_DELTA_TOO_FAR_INTO_FUTURE)

    def test_no_legacy_funding_limit(self):
        # 2^24 - 1 sat would only be ~0.17 MONA
        self.assertEqual(105_120_000 * COIN, lnutil.LN_MAX_FUNDING_SAT_LEGACY)


class FakeTranslations(gettext.NullTranslations):
    """A catalogue of upstream Electrum: the msgids, and the translations, say "Bitcoin"."""
    CATALOGUE = {
        "Bitcoin address": "Bitcoin-Adresse",
        "Pay to many": "An viele zahlen",
        "Send {} to a bitcoin address": "{} an eine bitcoin-Adresse senden",
        "Fee rate": "Rate (mBTC/kB)",
    }

    def gettext(self, message):
        return self.CATALOGUE.get(message, message)


class TestCoinNameInTranslations(MonacoinParamsMixin, ElectrumTestCase):

    def test_untranslated_strings(self):
        self.assertEqual("Monacoin address", i18n._("Bitcoin address"))
        self.assertEqual("Monacoin address", i18n._("Monacoin address"))
        self.assertEqual("Not a monacoin URI", i18n._("Not a bitcoin URI"))
        self.assertEqual("Send {} to a monacoin address", i18n._("Send {} to a bitcoin address"))
        self.assertEqual("Send 5 to a monacoin address", i18n._("Send {} to a bitcoin address").format(5))
        self.assertEqual("Electrum-MONA", i18n._("Electrum-MONA"))
        self.assertEqual("", i18n._(""))
        for msg in ("Lightning", "bits", "Pay to many", "BTC"):
            self.assertEqual(msg, i18n._(msg))

    def test_translated_strings(self):
        with mock.patch.object(i18n, "_language", FakeTranslations()):
            # the catalogue is looked up with upstream's string, whichever name the source code uses
            self.assertEqual("Monacoin-Adresse", i18n._("Bitcoin address"))
            self.assertEqual("Monacoin-Adresse", i18n._("Monacoin address"))
            self.assertEqual("An viele zahlen", i18n._("Pay to many"))
            self.assertEqual("5 an eine monacoin-Adresse senden", i18n._("Send {} to a monacoin address").format(5))
            self.assertEqual("Rate (mMONA/kB)", i18n._("Fee rate"))
            self.assertEqual("Not in the catalogue: Monacoin", i18n._("Not in the catalogue: Bitcoin"))
