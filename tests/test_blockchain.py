from pathlib import Path
import hashlib
import json
import os
from unittest import mock

from electrum_mona import constants
from electrum_mona.simple_config import SimpleConfig
from electrum_mona.blockchain import Blockchain, deserialize_header, hash_header, InvalidHeader, BlockchainManager
from electrum_mona.blockchain import (serialize_header, pow_hash_header, MissingHeader, HEADER_SIZE, CHUNK_SIZE,
                                      MAX_TARGET, LYRA2REV2_FORK_HEIGHT, DGWV3_PAST_BLOCKS, DGWV3_TARGET_SPACING)
from electrum_mona.bitcoin import hash_encode
from electrum_mona.scrypt import scrypt_1024_1_1_80
from electrum_mona.util import bfh

from . import ElectrumTestCase
from .upstream_params import MonacoinParamsMixin


def pin_mainnet_checkpoints(test_case: ElectrumTestCase, num_chunks: int = 1299) -> None:
    """The Monacoin header vectors below were made when the checkpoints covered 1299 chunks.
    Stick to those, so that the tests keep working when checkpoints.json gets extended.
    """
    checkpoints = constants.BitcoinMainnet.CHECKPOINTS
    assert len(checkpoints) >= num_chunks, len(checkpoints)
    patcher = mock.patch.object(constants.BitcoinMainnet, "_cached_checkpoints", checkpoints[:num_chunks])
    patcher.start()
    test_case.addCleanup(patcher.stop)


class TestBlockchain(ElectrumTestCase):

    HEADERS = {
        'A': deserialize_header(bfh("0100000000000000000000000000000000000000000000000000000000000000000000003ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4adae5494dffff7f2002000000"), 0),
        'B': deserialize_header(bfh("0000002006226e46111a0b59caaf126043eb5bbf28c34f3a5e332a1fc7b2b73cf188910f186c8dfd970a4545f79916bc1d75c9d00432f57c89209bf3bb115b7612848f509c25f45bffff7f2000000000"), 1),
        'C': deserialize_header(bfh("00000020686bdfc6a3db73d5d93e8c9663a720a26ecb1ef20eb05af11b36cdbc57c19f7ebf2cbf153013a1c54abaf70e95198fcef2f3059cc6b4d0f7e876808e7d24d11cc825f45bffff7f2000000000"), 2),
        'D': deserialize_header(bfh("00000020122baa14f3ef54985ae546d1611559e3f487bd2a0f46e8dbb52fbacc9e237972e71019d7feecd9b8596eca9a67032c5f4641b23b5d731dc393e37de7f9c2f299e725f45bffff7f2000000000"), 3),
        'E': deserialize_header(bfh("00000020f8016f7ef3a17d557afe05d4ea7ab6bde1b2247b7643896c1b63d43a1598b747a3586da94c71753f27c075f57f44faf913c31177a0957bbda42e7699e3a2141aed25f45bffff7f2001000000"), 4),
        'F': deserialize_header(bfh("000000201d589c6643c1d121d73b0573e5ee58ab575b8fdf16d507e7e915c5fbfbbfd05e7aee1d692d1615c3bdf52c291032144ce9e3b258a473c17c745047f3431ff8e2ee25f45bffff7f2000000000"), 5),
        'O': deserialize_header(bfh("00000020b833ed46eea01d4c980f59feee44a66aa1162748b6801029565d1466790c405c3a141ce635cbb1cd2b3a4fcdd0a3380517845ba41736c82a79cab535d31128066526f45bffff7f2001000000"), 6),
        'P': deserialize_header(bfh("00000020abe8e119d1877c9dc0dc502d1a253fb9a67967c57732d2f71ee0280e8381ff0a9690c2fe7c1a4450c74dc908fe94dd96c3b0637d51475e9e06a78e944a0c7fe28126f45bffff7f2000000000"), 7),
        'Q': deserialize_header(bfh("000000202ce41d94eb70e1518bc1f72523f84a903f9705d967481e324876e1f8cf4d3452148be228a4c3f2061bafe7efdfc4a8d5a94759464b9b5c619994d45dfcaf49e1a126f45bffff7f2000000000"), 8),
        'R': deserialize_header(bfh("00000020552755b6c59f3d51e361d16281842a4e166007799665b5daed86a063dd89857415681cb2d00ff889193f6a68a93f5096aeb2d84ca0af6185a462555822552221a626f45bffff7f2000000000"), 9),
        'S': deserialize_header(bfh("00000020a13a491cbefc93cd1bb1938f19957e22a134faf14c7dee951c45533e2c750f239dc087fc977b06c24a69c682d1afd1020e6dc1f087571ccec66310a786e1548fab26f45bffff7f2000000000"), 10),
        'T': deserialize_header(bfh("00000020dbf3a9b55dfefbaf8b6e43a89cf833fa2e208bbc0c1c5d76c0d71b9e4a65337803b243756c25053253aeda309604363460a3911015929e68705bd89dff6fe064b026f45bffff7f2002000000"), 11),
        'U': deserialize_header(bfh("000000203d0932b3b0c78eccb39a595a28ae4a7c966388648d7783fd1305ec8d40d4fe5fd67cb902a7d807cee7676cb543feec3e053aa824d5dfb528d5b94f9760313d9db726f45bffff7f2001000000"), 12),
        'G': deserialize_header(bfh("00000020b833ed46eea01d4c980f59feee44a66aa1162748b6801029565d1466790c405c3a141ce635cbb1cd2b3a4fcdd0a3380517845ba41736c82a79cab535d31128066928f45bffff7f2001000000"), 6),
        'H': deserialize_header(bfh("00000020e19e687f6e7f83ca394c114144dbbbc4f3f9c9450f66331a125413702a2e1a719690c2fe7c1a4450c74dc908fe94dd96c3b0637d51475e9e06a78e944a0c7fe26a28f45bffff7f2002000000"), 7),
        'I': deserialize_header(bfh("0000002009dcb3b158293c89d7cf7ceeb513add122ebc3880a850f47afbb2747f5e48c54148be228a4c3f2061bafe7efdfc4a8d5a94759464b9b5c619994d45dfcaf49e16a28f45bffff7f2000000000"), 8),
        'J': deserialize_header(bfh("000000206a65f3bdd3374a5a6c4538008ba0b0a560b8566291f9ef4280ab877627a1742815681cb2d00ff889193f6a68a93f5096aeb2d84ca0af6185a462555822552221c928f45bffff7f2000000000"), 9),
        'K': deserialize_header(bfh("00000020bb3b421653548991998f96f8ba486b652fdb07ca16e9cee30ece033547cd1a6e9dc087fc977b06c24a69c682d1afd1020e6dc1f087571ccec66310a786e1548fca28f45bffff7f2000000000"), 10),
        'L': deserialize_header(bfh("00000020c391d74d37c24a130f4bf4737932bdf9e206dd4fad22860ec5408978eb55d46303b243756c25053253aeda309604363460a3911015929e68705bd89dff6fe064ca28f45bffff7f2000000000"), 11),
        'M': deserialize_header(bfh("000000206a65f3bdd3374a5a6c4538008ba0b0a560b8566291f9ef4280ab877627a1742815681cb2d00ff889193f6a68a93f5096aeb2d84ca0af6185a4625558225522214229f45bffff7f2000000000"), 9),
        'N': deserialize_header(bfh("00000020383dab38b57f98aa9b4f0d5ff868bc674b4828d76766bf048296f4c45fff680a9dc087fc977b06c24a69c682d1afd1020e6dc1f087571ccec66310a786e1548f4329f45bffff7f2003000000"), 10),
        'X': deserialize_header(bfh("0000002067f1857f54b7fef732cb4940f7d1b339472b3514660711a820330fd09d8fba6b03b243756c25053253aeda309604363460a3911015929e68705bd89dff6fe0649b29f45bffff7f2002000000"), 11),
        'Y': deserialize_header(bfh("00000020db33c9768a9e5f7c37d0f09aad88d48165946c87d08f7d63793f07b5c08c527fd67cb902a7d807cee7676cb543feec3e053aa824d5dfb528d5b94f9760313d9d9b29f45bffff7f2000000000"), 12),
        'Z': deserialize_header(bfh("0000002047822b67940e337fda38be6f13390b3596e4dea2549250256879722073824e7f0f2596c29203f8a0f71ae94193092dc8f113be3dbee4579f1e649fa3d6dcc38c622ef45bffff7f2003000000"), 13),
    }
    # tree of headers:
    #                                            - M <- N <- X <- Y <- Z
    #                                          /
    #                             - G <- H <- I <- J <- K <- L
    #                           /
    # A <- B <- C <- D <- E <- F <- O <- P <- Q <- R <- S <- T <- U

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        constants.BitcoinRegtest.set_as_network()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        constants.BitcoinMainnet.set_as_network()

    def setUp(self):
        super().setUp()
        self.data_dir = Path(self.electrum_path)
        self.config = SimpleConfig({'electrum_path': self.data_dir})
        self.bc_mgr = BlockchainManager.from_config(self.config)

    def _append_header(self, chain: Blockchain, header: dict):
        self.assertTrue(chain.can_connect(header))
        chain.save_header(header)

    def test_get_height_of_last_common_block_with_chain(self):
        self.bc_mgr.blockchains[constants.net.GENESIS] = chain_u = Blockchain(
            bc_mgr=self.bc_mgr, forkpoint=0, parent=None,
            forkpoint_hash=constants.net.GENESIS, prev_hash=None)
        open(chain_u.path(), 'w+').close()
        self._append_header(chain_u, self.HEADERS['A'])
        self._append_header(chain_u, self.HEADERS['B'])
        self._append_header(chain_u, self.HEADERS['C'])
        self._append_header(chain_u, self.HEADERS['D'])
        self._append_header(chain_u, self.HEADERS['E'])
        self._append_header(chain_u, self.HEADERS['F'])
        self._append_header(chain_u, self.HEADERS['O'])
        self._append_header(chain_u, self.HEADERS['P'])
        self._append_header(chain_u, self.HEADERS['Q'])

        chain_l = chain_u.fork(self.HEADERS['G'])
        self._append_header(chain_l, self.HEADERS['H'])
        self._append_header(chain_l, self.HEADERS['I'])
        self._append_header(chain_l, self.HEADERS['J'])
        self._append_header(chain_l, self.HEADERS['K'])
        self._append_header(chain_l, self.HEADERS['L'])

        self.assertEqual({chain_u:  8, chain_l: 5}, chain_u.get_parent_heights())
        self.assertEqual({chain_l: 11},             chain_l.get_parent_heights())

        chain_z = chain_l.fork(self.HEADERS['M'])
        self._append_header(chain_z, self.HEADERS['N'])
        self._append_header(chain_z, self.HEADERS['X'])
        self._append_header(chain_z, self.HEADERS['Y'])
        self._append_header(chain_z, self.HEADERS['Z'])

        self.assertEqual({chain_u:  8, chain_z: 5}, chain_u.get_parent_heights())
        self.assertEqual({chain_l: 11, chain_z: 8}, chain_l.get_parent_heights())
        self.assertEqual({chain_z: 13},             chain_z.get_parent_heights())
        self.assertEqual(5, chain_u.get_height_of_last_common_block_with_chain(chain_l))
        self.assertEqual(5, chain_l.get_height_of_last_common_block_with_chain(chain_u))
        self.assertEqual(5, chain_u.get_height_of_last_common_block_with_chain(chain_z))
        self.assertEqual(5, chain_z.get_height_of_last_common_block_with_chain(chain_u))
        self.assertEqual(8, chain_l.get_height_of_last_common_block_with_chain(chain_z))
        self.assertEqual(8, chain_z.get_height_of_last_common_block_with_chain(chain_l))

        self._append_header(chain_u, self.HEADERS['R'])
        self._append_header(chain_u, self.HEADERS['S'])
        self._append_header(chain_u, self.HEADERS['T'])
        self._append_header(chain_u, self.HEADERS['U'])

        self.assertEqual({chain_u: 12, chain_z: 5}, chain_u.get_parent_heights())
        self.assertEqual({chain_l: 11, chain_z: 8}, chain_l.get_parent_heights())
        self.assertEqual({chain_z: 13},             chain_z.get_parent_heights())
        self.assertEqual(5, chain_u.get_height_of_last_common_block_with_chain(chain_l))
        self.assertEqual(5, chain_l.get_height_of_last_common_block_with_chain(chain_u))
        self.assertEqual(5, chain_u.get_height_of_last_common_block_with_chain(chain_z))
        self.assertEqual(5, chain_z.get_height_of_last_common_block_with_chain(chain_u))
        self.assertEqual(8, chain_l.get_height_of_last_common_block_with_chain(chain_z))
        self.assertEqual(8, chain_z.get_height_of_last_common_block_with_chain(chain_l))

    def test_parents_after_forking(self):
        self.bc_mgr.blockchains[constants.net.GENESIS] = chain_u = Blockchain(
            bc_mgr=self.bc_mgr, forkpoint=0, parent=None,
            forkpoint_hash=constants.net.GENESIS, prev_hash=None)
        open(chain_u.path(), 'w+').close()
        self._append_header(chain_u, self.HEADERS['A'])
        self._append_header(chain_u, self.HEADERS['B'])
        self._append_header(chain_u, self.HEADERS['C'])
        self._append_header(chain_u, self.HEADERS['D'])
        self._append_header(chain_u, self.HEADERS['E'])
        self._append_header(chain_u, self.HEADERS['F'])
        self._append_header(chain_u, self.HEADERS['O'])
        self._append_header(chain_u, self.HEADERS['P'])
        self._append_header(chain_u, self.HEADERS['Q'])

        self.assertEqual(None, chain_u.parent)

        chain_l = chain_u.fork(self.HEADERS['G'])
        self._append_header(chain_l, self.HEADERS['H'])
        self._append_header(chain_l, self.HEADERS['I'])
        self._append_header(chain_l, self.HEADERS['J'])
        self._append_header(chain_l, self.HEADERS['K'])
        self._append_header(chain_l, self.HEADERS['L'])

        self.assertEqual(None,    chain_l.parent)
        self.assertEqual(chain_l, chain_u.parent)

        chain_z = chain_l.fork(self.HEADERS['M'])
        self._append_header(chain_z, self.HEADERS['N'])
        self._append_header(chain_z, self.HEADERS['X'])
        self._append_header(chain_z, self.HEADERS['Y'])
        self._append_header(chain_z, self.HEADERS['Z'])

        self.assertEqual(chain_z, chain_u.parent)
        self.assertEqual(chain_z, chain_l.parent)
        self.assertEqual(None,    chain_z.parent)

        self._append_header(chain_u, self.HEADERS['R'])
        self._append_header(chain_u, self.HEADERS['S'])
        self._append_header(chain_u, self.HEADERS['T'])
        self._append_header(chain_u, self.HEADERS['U'])

        self.assertEqual(chain_z, chain_u.parent)
        self.assertEqual(chain_z, chain_l.parent)
        self.assertEqual(None,    chain_z.parent)

    def test_forking_and_swapping(self):
        self.bc_mgr.blockchains[constants.net.GENESIS] = chain_u = Blockchain(
            bc_mgr=self.bc_mgr, forkpoint=0, parent=None,
            forkpoint_hash=constants.net.GENESIS, prev_hash=None)
        open(chain_u.path(), 'w+').close()

        self._append_header(chain_u, self.HEADERS['A'])
        self._append_header(chain_u, self.HEADERS['B'])
        self._append_header(chain_u, self.HEADERS['C'])
        self._append_header(chain_u, self.HEADERS['D'])
        self._append_header(chain_u, self.HEADERS['E'])
        self._append_header(chain_u, self.HEADERS['F'])
        self._append_header(chain_u, self.HEADERS['O'])
        self._append_header(chain_u, self.HEADERS['P'])
        self._append_header(chain_u, self.HEADERS['Q'])
        self._append_header(chain_u, self.HEADERS['R'])

        chain_l = chain_u.fork(self.HEADERS['G'])
        self._append_header(chain_l, self.HEADERS['H'])
        self._append_header(chain_l, self.HEADERS['I'])
        self._append_header(chain_l, self.HEADERS['J'])

        # do checks
        self.assertEqual(2, len(self.bc_mgr.blockchains))
        self.assertEqual(1, len(os.listdir(self.data_dir / "forks")))
        self.assertEqual(0, chain_u.forkpoint)
        self.assertEqual(None, chain_u.parent)
        self.assertEqual(constants.net.GENESIS, chain_u._forkpoint_hash)
        self.assertEqual(None, chain_u._prev_hash)
        self.assertEqual(self.data_dir / "blockchain_headers", chain_u.path())
        self.assertEqual(10 * 80, os.stat(chain_u.path()).st_size)
        self.assertEqual(6, chain_l.forkpoint)
        self.assertEqual(chain_u, chain_l.parent)
        self.assertEqual(hash_header(self.HEADERS['G']), chain_l._forkpoint_hash)
        self.assertEqual(hash_header(self.HEADERS['F']), chain_l._prev_hash)
        self.assertEqual(self.data_dir / "forks" / "fork2_6_5c400c7966145d56291080b6482716a16aa644eefe590f984c1da0ee46ed33b8_711a2e2a701354121a33660f45c9f9f3c4bbdb4441114c39ca837f6e7f689ee1", chain_l.path())
        self.assertEqual(4 * 80, os.stat(chain_l.path()).st_size)

        self._append_header(chain_l, self.HEADERS['K'])

        # chains were swapped, do checks
        self.assertEqual(2, len(self.bc_mgr.blockchains))
        self.assertEqual(1, len(os.listdir(self.data_dir / "forks")))
        self.assertEqual(6, chain_u.forkpoint)
        self.assertEqual(chain_l, chain_u.parent)
        self.assertEqual(hash_header(self.HEADERS['O']), chain_u._forkpoint_hash)
        self.assertEqual(hash_header(self.HEADERS['F']), chain_u._prev_hash)
        self.assertEqual(self.data_dir / "forks" / "fork2_6_5c400c7966145d56291080b6482716a16aa644eefe590f984c1da0ee46ed33b8_aff81830e28e01ef7d23277c56779a6b93f251a2d50dcc09d7c87d119e1e8ab", chain_u.path())
        self.assertEqual(4 * 80, os.stat(chain_u.path()).st_size)
        self.assertEqual(0, chain_l.forkpoint)
        self.assertEqual(None, chain_l.parent)
        self.assertEqual(constants.net.GENESIS, chain_l._forkpoint_hash)
        self.assertEqual(None, chain_l._prev_hash)
        self.assertEqual(self.data_dir / "blockchain_headers", chain_l.path())
        self.assertEqual(11 * 80, os.stat(chain_l.path()).st_size)
        for b in (chain_u, chain_l):
            self.assertTrue(all([b.can_connect(b.read_header(i), check_height=False) for i in range(b.height())]))

        self._append_header(chain_u, self.HEADERS['S'])
        self._append_header(chain_u, self.HEADERS['T'])
        self._append_header(chain_u, self.HEADERS['U'])
        self._append_header(chain_l, self.HEADERS['L'])

        chain_z = chain_l.fork(self.HEADERS['M'])
        self._append_header(chain_z, self.HEADERS['N'])
        self._append_header(chain_z, self.HEADERS['X'])
        self._append_header(chain_z, self.HEADERS['Y'])
        self._append_header(chain_z, self.HEADERS['Z'])

        # chain_z became best chain, do checks
        self.assertEqual(3, len(self.bc_mgr.blockchains))
        self.assertEqual(2, len(os.listdir(self.data_dir / "forks")))
        self.assertEqual(0, chain_z.forkpoint)
        self.assertEqual(None, chain_z.parent)
        self.assertEqual(constants.net.GENESIS, chain_z._forkpoint_hash)
        self.assertEqual(None, chain_z._prev_hash)
        self.assertEqual(self.data_dir / "blockchain_headers", chain_z.path())
        self.assertEqual(14 * 80, os.stat(chain_z.path()).st_size)
        self.assertEqual(9, chain_l.forkpoint)
        self.assertEqual(chain_z, chain_l.parent)
        self.assertEqual(hash_header(self.HEADERS['J']), chain_l._forkpoint_hash)
        self.assertEqual(hash_header(self.HEADERS['I']), chain_l._prev_hash)
        self.assertEqual(self.data_dir / "forks" / "fork2_9_2874a1277687ab8042eff9916256b860a5b0a08b0038456c5a4a37d3bdf3656a_6e1acd473503ce0ee3cee916ca07db2f656b48baf8968f999189545316423bbb", chain_l.path())
        self.assertEqual(3 * 80, os.stat(chain_l.path()).st_size)
        self.assertEqual(6, chain_u.forkpoint)
        self.assertEqual(chain_z, chain_u.parent)
        self.assertEqual(hash_header(self.HEADERS['O']), chain_u._forkpoint_hash)
        self.assertEqual(hash_header(self.HEADERS['F']), chain_u._prev_hash)
        self.assertEqual(self.data_dir / "forks" / "fork2_6_5c400c7966145d56291080b6482716a16aa644eefe590f984c1da0ee46ed33b8_aff81830e28e01ef7d23277c56779a6b93f251a2d50dcc09d7c87d119e1e8ab", chain_u.path())
        self.assertEqual(7 * 80, os.stat(chain_u.path()).st_size)
        for b in (chain_u, chain_l, chain_z):
            self.assertTrue(all([b.can_connect(b.read_header(i), check_height=False) for i in range(b.height())]))

        self.assertEqual(constants.net.GENESIS, chain_z.get_hash(0))
        self.assertEqual(hash_header(self.HEADERS['F']), chain_z.get_hash(5))
        self.assertEqual(hash_header(self.HEADERS['G']), chain_z.get_hash(6))
        self.assertEqual(hash_header(self.HEADERS['I']), chain_z.get_hash(8))
        self.assertEqual(hash_header(self.HEADERS['M']), chain_z.get_hash(9))
        self.assertEqual(hash_header(self.HEADERS['Z']), chain_z.get_hash(13))

    def test_doing_multiple_swaps_after_single_new_header(self):
        self.bc_mgr.blockchains[constants.net.GENESIS] = chain_u = Blockchain(
            bc_mgr=self.bc_mgr, forkpoint=0, parent=None,
            forkpoint_hash=constants.net.GENESIS, prev_hash=None)
        open(chain_u.path(), 'w+').close()

        self._append_header(chain_u, self.HEADERS['A'])
        self._append_header(chain_u, self.HEADERS['B'])
        self._append_header(chain_u, self.HEADERS['C'])
        self._append_header(chain_u, self.HEADERS['D'])
        self._append_header(chain_u, self.HEADERS['E'])
        self._append_header(chain_u, self.HEADERS['F'])
        self._append_header(chain_u, self.HEADERS['O'])
        self._append_header(chain_u, self.HEADERS['P'])
        self._append_header(chain_u, self.HEADERS['Q'])
        self._append_header(chain_u, self.HEADERS['R'])
        self._append_header(chain_u, self.HEADERS['S'])

        self.assertEqual(1, len(self.bc_mgr.blockchains))
        self.assertEqual(0, len(os.listdir(self.data_dir / "forks")))

        chain_l = chain_u.fork(self.HEADERS['G'])
        self._append_header(chain_l, self.HEADERS['H'])
        self._append_header(chain_l, self.HEADERS['I'])
        self._append_header(chain_l, self.HEADERS['J'])
        self._append_header(chain_l, self.HEADERS['K'])
        # now chain_u is best chain, but it's tied with chain_l

        self.assertEqual(2, len(self.bc_mgr.blockchains))
        self.assertEqual(1, len(os.listdir(self.data_dir / "forks")))

        chain_z = chain_l.fork(self.HEADERS['M'])
        self._append_header(chain_z, self.HEADERS['N'])
        self._append_header(chain_z, self.HEADERS['X'])

        self.assertEqual(3, len(self.bc_mgr.blockchains))
        self.assertEqual(2, len(os.listdir(self.data_dir / "forks")))

        # chain_z became best chain, do checks
        self.assertEqual(0, chain_z.forkpoint)
        self.assertEqual(None, chain_z.parent)
        self.assertEqual(constants.net.GENESIS, chain_z._forkpoint_hash)
        self.assertEqual(None, chain_z._prev_hash)
        self.assertEqual(self.data_dir / "blockchain_headers", chain_z.path())
        self.assertEqual(12 * 80, os.stat(chain_z.path()).st_size)
        self.assertEqual(9, chain_l.forkpoint)
        self.assertEqual(chain_z, chain_l.parent)
        self.assertEqual(hash_header(self.HEADERS['J']), chain_l._forkpoint_hash)
        self.assertEqual(hash_header(self.HEADERS['I']), chain_l._prev_hash)
        self.assertEqual(self.data_dir / "forks" / "fork2_9_2874a1277687ab8042eff9916256b860a5b0a08b0038456c5a4a37d3bdf3656a_6e1acd473503ce0ee3cee916ca07db2f656b48baf8968f999189545316423bbb", chain_l.path())
        self.assertEqual(2 * 80, os.stat(chain_l.path()).st_size)
        self.assertEqual(6, chain_u.forkpoint)
        self.assertEqual(chain_z, chain_u.parent)
        self.assertEqual(hash_header(self.HEADERS['O']), chain_u._forkpoint_hash)
        self.assertEqual(hash_header(self.HEADERS['F']), chain_u._prev_hash)
        self.assertEqual(self.data_dir / "forks" / "fork2_6_5c400c7966145d56291080b6482716a16aa644eefe590f984c1da0ee46ed33b8_aff81830e28e01ef7d23277c56779a6b93f251a2d50dcc09d7c87d119e1e8ab", chain_u.path())
        self.assertEqual(5 * 80, os.stat(chain_u.path()).st_size)

        self.assertEqual(constants.net.GENESIS, chain_z.get_hash(0))
        self.assertEqual(hash_header(self.HEADERS['F']), chain_z.get_hash(5))
        self.assertEqual(hash_header(self.HEADERS['G']), chain_z.get_hash(6))
        self.assertEqual(hash_header(self.HEADERS['I']), chain_z.get_hash(8))
        self.assertEqual(hash_header(self.HEADERS['M']), chain_z.get_hash(9))
        self.assertEqual(hash_header(self.HEADERS['X']), chain_z.get_hash(11))

        for b in (chain_u, chain_l, chain_z):
            self.assertTrue(all([b.can_connect(b.read_header(i), check_height=False) for i in range(b.height())]))

    def get_chains_that_contain_header_helper(self, header: dict):
        height = header['block_height']
        header_hash = hash_header(header)
        return self.bc_mgr.get_chains_that_contain_header(height, header_hash)

    def test_get_chains_that_contain_header(self):
        self.bc_mgr.blockchains[constants.net.GENESIS] = chain_u = Blockchain(
            bc_mgr=self.bc_mgr, forkpoint=0, parent=None,
            forkpoint_hash=constants.net.GENESIS, prev_hash=None)
        open(chain_u.path(), 'w+').close()
        self._append_header(chain_u, self.HEADERS['A'])
        self._append_header(chain_u, self.HEADERS['B'])
        self._append_header(chain_u, self.HEADERS['C'])
        self._append_header(chain_u, self.HEADERS['D'])
        self._append_header(chain_u, self.HEADERS['E'])
        self._append_header(chain_u, self.HEADERS['F'])
        self._append_header(chain_u, self.HEADERS['O'])
        self._append_header(chain_u, self.HEADERS['P'])
        self._append_header(chain_u, self.HEADERS['Q'])

        chain_l = chain_u.fork(self.HEADERS['G'])
        self._append_header(chain_l, self.HEADERS['H'])
        self._append_header(chain_l, self.HEADERS['I'])
        self._append_header(chain_l, self.HEADERS['J'])
        self._append_header(chain_l, self.HEADERS['K'])
        self._append_header(chain_l, self.HEADERS['L'])

        chain_z = chain_l.fork(self.HEADERS['M'])

        self.assertEqual([chain_l, chain_z, chain_u], self.get_chains_that_contain_header_helper(self.HEADERS['A']))
        self.assertEqual([chain_l, chain_z, chain_u], self.get_chains_that_contain_header_helper(self.HEADERS['C']))
        self.assertEqual([chain_l, chain_z, chain_u], self.get_chains_that_contain_header_helper(self.HEADERS['F']))
        self.assertEqual([chain_l, chain_z], self.get_chains_that_contain_header_helper(self.HEADERS['G']))
        self.assertEqual([chain_l, chain_z], self.get_chains_that_contain_header_helper(self.HEADERS['I']))
        self.assertEqual([chain_z], self.get_chains_that_contain_header_helper(self.HEADERS['M']))
        self.assertEqual([chain_l], self.get_chains_that_contain_header_helper(self.HEADERS['K']))

        self._append_header(chain_z, self.HEADERS['N'])
        self._append_header(chain_z, self.HEADERS['X'])
        self._append_header(chain_z, self.HEADERS['Y'])
        self._append_header(chain_z, self.HEADERS['Z'])

        self.assertEqual([chain_z, chain_l, chain_u], self.get_chains_that_contain_header_helper(self.HEADERS['A']))
        self.assertEqual([chain_z, chain_l, chain_u], self.get_chains_that_contain_header_helper(self.HEADERS['C']))
        self.assertEqual([chain_z, chain_l, chain_u], self.get_chains_that_contain_header_helper(self.HEADERS['F']))
        self.assertEqual([chain_u], self.get_chains_that_contain_header_helper(self.HEADERS['O']))
        self.assertEqual([chain_z, chain_l], self.get_chains_that_contain_header_helper(self.HEADERS['I']))

    def test_target_to_bits(self):
        # https://github.com/bitcoin/bitcoin/blob/7fcf53f7b4524572d1d0c9a5fdc388e87eb02416/src/arith_uint256.h#L269
        self.assertEqual(0x05123456, Blockchain.target_to_bits(0x1234560000))
        self.assertEqual(0x0600c0de, Blockchain.target_to_bits(0xc0de000000))

        # tests from https://github.com/bitcoin/bitcoin/blob/a7d17daa5cd8bf6398d5f8d7e77290009407d6ea/src/test/arith_uint256_tests.cpp#L411
        tuples = (
            (0, 0x0000000000000000000000000000000000000000000000000000000000000000, 0),
            (0x00123456, 0x0000000000000000000000000000000000000000000000000000000000000000, 0),
            (0x01003456, 0x0000000000000000000000000000000000000000000000000000000000000000, 0),
            (0x02000056, 0x0000000000000000000000000000000000000000000000000000000000000000, 0),
            (0x03000000, 0x0000000000000000000000000000000000000000000000000000000000000000, 0),
            (0x04000000, 0x0000000000000000000000000000000000000000000000000000000000000000, 0),
            (0x00923456, 0x0000000000000000000000000000000000000000000000000000000000000000, 0),
            (0x01803456, 0x0000000000000000000000000000000000000000000000000000000000000000, 0),
            (0x02800056, 0x0000000000000000000000000000000000000000000000000000000000000000, 0),
            (0x03800000, 0x0000000000000000000000000000000000000000000000000000000000000000, 0),
            (0x04800000, 0x0000000000000000000000000000000000000000000000000000000000000000, 0),
            (0x01123456, 0x0000000000000000000000000000000000000000000000000000000000000012, 0x01120000),
            (0x02123456, 0x0000000000000000000000000000000000000000000000000000000000001234, 0x02123400),
            (0x03123456, 0x0000000000000000000000000000000000000000000000000000000000123456, 0x03123456),
            (0x04123456, 0x0000000000000000000000000000000000000000000000000000000012345600, 0x04123456),
            (0x05009234, 0x0000000000000000000000000000000000000000000000000000000092340000, 0x05009234),
            (0x20123456, 0x1234560000000000000000000000000000000000000000000000000000000000, 0x20123456),
        )
        for nbits1, target, nbits2 in tuples:
            with self.subTest(original_compact_nbits=nbits1.to_bytes(length=4, byteorder="big").hex()):
                num = Blockchain.bits_to_target(nbits1)
                self.assertEqual(target, num)
                self.assertEqual(nbits2, Blockchain.target_to_bits(num))

        # Make sure that we don't generate compacts with the 0x00800000 bit set
        self.assertEqual(0x02008000, Blockchain.target_to_bits(0x80))

        with self.assertRaises(InvalidHeader):  # target cannot be negative
            Blockchain.bits_to_target(0x01fedcba)
        with self.assertRaises(InvalidHeader):  # target cannot be negative
            Blockchain.bits_to_target(0x04923456)
        with self.assertRaises(InvalidHeader):  # overflow
            Blockchain.bits_to_target(0xff123456)


class TestVerifyHeader(ElectrumTestCase):

    # Data for Monacoin block header #2618875. (proof-of-work: Lyra2REv2)
    # note: this height is above the checkpoints. Most headers below them are not pow-checked,
    #       see TestMonacoinHeaders.
    valid_header = "000000207ef097f85c42eae5e53551c95a30c336a86b3958e9b2c99a44a16b4a4e5efb90c31ab1ae02f56e9391b2427f02f418410d864df97ff869d0ab6f03f0971960528a8f41620c6d041a88c2bf8b"
    target = Blockchain.bits_to_target(0x1a046d0c)
    prev_hash = "90fb5e4e4a6ba1449ac9b2e958396ba836c3305ac95135e5e5ea425cf897f07e"

    def setUp(self):
        super().setUp()
        pin_mainnet_checkpoints(self)
        self.header = deserialize_header(bfh(self.valid_header), 2618875)

    def test_valid_header(self):
        Blockchain.verify_header(self.header, self.prev_hash, self.target)

    def test_expected_hash_mismatch(self):
        with self.assertRaises(InvalidHeader):
            Blockchain.verify_header(self.header, self.prev_hash, self.target,
                                     expected_header_hash="foo")

    def test_prev_hash_mismatch(self):
        with self.assertRaises(InvalidHeader):
            Blockchain.verify_header(self.header, "foo", self.target)

    def test_target_mismatch(self):
        with self.assertRaises(InvalidHeader):
            other_target = Blockchain.bits_to_target(0x1b046d0c)
            Blockchain.verify_header(self.header, self.prev_hash, other_target)

    def test_insufficient_pow(self):
        with self.assertRaises(InvalidHeader):
            self.header["nonce"] = 42
            Blockchain.verify_header(self.header, self.prev_hash, self.target)


class TestMonacoinHeaders(MonacoinParamsMixin, ElectrumTestCase):
    """Proof-of-work (scrypt, Lyra2REv2) and difficulty (DGWv3) of real mainnet headers,
    on top of the shipped checkpoints. The headers are in tests/monacoin-headers.json.
    """

    FIRST = 2618784  # first height above the checkpoints
    TIP = 2618875  # last header we have
    TIP_HASH = "6dbe95e2e280c8e46229c567fa1edf8c80d7db84af9fdbf6f9a4baf032742f3c"  # as seen on block explorers
    # the first headers above the checkpoints are not pow-checked, see Blockchain.verify_header
    FIRST_CHECKED = FIRST + DGWV3_PAST_BLOCKS + 1

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open(os.path.join(os.path.dirname(__file__), "monacoin-headers.json")) as f:
            vectors = json.load(f)
        cls.raw_headers = {2015: bfh(vectors["2015"]), 461663: bfh(vectors["461663"])}
        for i, raw_header in enumerate(vectors["2618784"]):
            cls.raw_headers[cls.FIRST + i] = bfh(raw_header)
        assert max(cls.raw_headers) == cls.TIP

    def setUp(self):
        super().setUp()
        pin_mainnet_checkpoints(self)
        self.config = SimpleConfig({'electrum_path': self.electrum_path})
        self.bc_mgr = BlockchainManager.from_config(self.config)
        self.chain = self.bc_mgr.get_best_chain()

    def header(self, height: int, **changes) -> dict:
        header = deserialize_header(self.raw_headers[height], height)
        header.update(changes)
        return header

    def headers(self, first: int = FIRST, last: int = TIP) -> dict:
        return {height: self.header(height) for height in range(first, last + 1)}

    def header_with_bad_nonce(self, height: int, **changes) -> dict:
        return self.header(height, nonce=self.header(height)['nonce'] ^ 1, **changes)

    def connect(self, first: int, last: int) -> None:
        for height in range(first, last + 1):
            header = self.header(height)
            self.assertTrue(self.chain.can_connect(header), msg=height)
            self.chain.save_header(header)

    def test_vectors_are_anchored_to_the_checkpoints(self):
        checkpoints = constants.net.CHECKPOINTS
        self.assertEqual(self.FIRST, len(checkpoints) * CHUNK_SIZE)
        self.assertEqual(self.FIRST - 1, constants.net.max_checkpoint())
        # a checkpoint is (hash of the last header of the chunk, target of that header)
        for height in (2015, 461663):
            header = self.header(height)
            cp_hash, cp_target = checkpoints[height // CHUNK_SIZE]
            self.assertEqual(cp_hash, hash_header(header))
            self.assertEqual(cp_target, Blockchain.bits_to_target(header['bits']))
        prev_hash = checkpoints[-1][0]
        for height in range(self.FIRST, self.TIP + 1):
            header = self.header(height)
            self.assertEqual(prev_hash, header['prev_block_hash'], msg=height)
            prev_hash = hash_header(header)
        self.assertEqual(self.TIP_HASH, prev_hash)

    def test_headers_file_starts_at_the_checkpoints(self):
        self.assertEqual(self.FIRST - 1, self.chain.height())
        self.assertEqual(constants.net.CHECKPOINTS[-1][0], self.chain.get_hash(self.FIRST - 1))
        self.assertEqual(constants.net.GENESIS, self.chain.get_hash(0))

    def test_max_target(self):
        # powLimit of Monacoin Core
        self.assertEqual(0x00000fffffffffffffffffffffffffffffffffffffffffffffffffffffffffff, MAX_TARGET)
        self.assertEqual(0x1e0fffff, Blockchain.target_to_bits(MAX_TARGET))
        self.assertEqual(0x00000fffff << 216, Blockchain.bits_to_target(0x1e0fffff))  # compact form is less precise

    def test_pow_hash_satisfies_the_target(self):
        """The hash that has to satisfy the target is not the block hash, but the scrypt hash
        of the header (below height 450000), or its Lyra2REv2 hash."""
        self.assertEqual(450000, LYRA2REV2_FORK_HEIGHT)
        for height in sorted(self.raw_headers):
            header = self.header(height)
            target = Blockchain.bits_to_target(header['bits'])
            self.assertLessEqual(int(pow_hash_header(header), 16), target, msg=height)
        # the wrong algorithm does not result in a valid proof-of-work
        for height, wrong_height in ((2015, LYRA2REV2_FORK_HEIGHT), (self.TIP, LYRA2REV2_FORK_HEIGHT - 1)):
            header = self.header(height, block_height=wrong_height)
            target = Blockchain.bits_to_target(header['bits'])
            self.assertGreater(int(pow_hash_header(header), 16), target, msg=height)
        # the block hash is not good enough either. (it was for bitcoin)
        header = self.header(self.TIP)
        self.assertGreater(int(hash_header(header), 16), Blockchain.bits_to_target(header['bits']))

    def test_pow_hash_below_the_pow_limit_is_not_enough(self):
        # with this nonce the pow hash is below the pow limit (min difficulty), but far above the target of the header
        header = self.header(self.TIP, nonce=1370737)
        target = self.chain.get_target(self.TIP, self.headers())
        self.assertEqual("00000973eab9b66ab299a0bd44018478d44ff25b199f0fb3a9328b56eb1e955d", pow_hash_header(header))
        self.assertTrue(target < int(pow_hash_header(header), 16) < MAX_TARGET)
        with self.assertRaises(InvalidHeader):
            Blockchain.verify_header(header, header['prev_block_hash'], target)
        Blockchain.verify_header(self.header(self.TIP), header['prev_block_hash'], target)

    def test_pow_hash_scrypt_implementations_agree(self):
        """blockchain.py uses hashlib.scrypt, and falls back to electrum_mona/scrypt.py (pure python)."""
        header = self.header(2015)
        raw_header = self.raw_headers[2015]
        pow_hash = hash_encode(scrypt_1024_1_1_80(raw_header))
        self.assertLessEqual(int(pow_hash, 16), Blockchain.bits_to_target(header['bits']))
        self.assertEqual(pow_hash, pow_hash_header(header))
        for exc in (AttributeError, ValueError):  # hashlib built without scrypt support
            with mock.patch.object(hashlib, "scrypt", side_effect=exc, create=True) as mock_scrypt:
                self.assertEqual(pow_hash, pow_hash_header(header))
                mock_scrypt.assert_called_once()

    def test_verify_header_scrypt(self):
        header = self.header(2015)
        prev_hash = header['prev_block_hash']
        target = self.chain.get_target(2015)
        Blockchain.verify_header(header, prev_hash, target, expected_header_hash=self.chain.get_hash(2015))
        with self.assertRaises(InvalidHeader):  # insufficient pow
            Blockchain.verify_header(self.header_with_bad_nonce(2015), prev_hash, target)
        with self.assertRaises(InvalidHeader):  # bits mismatch
            Blockchain.verify_header(header, prev_hash, MAX_TARGET)
        with self.assertRaises(InvalidHeader):
            Blockchain.verify_header(header, "00" * 32, target)

    def test_verify_header_lyra2rev2_below_checkpoints(self):
        header = self.header(461663)
        prev_hash = header['prev_block_hash']
        target = self.chain.get_target(461663)
        Blockchain.verify_header(header, prev_hash, target, expected_header_hash=self.chain.get_hash(461663))
        with self.assertRaises(InvalidHeader):  # insufficient pow
            Blockchain.verify_header(self.header_with_bad_nonce(461663), prev_hash, target)
        with self.assertRaises(InvalidHeader):  # bits mismatch
            Blockchain.verify_header(header, prev_hash, MAX_TARGET)

    def test_get_target(self):
        # expected values are from Electrum-MONA 4.2.1
        chain = self.chain
        # before DGWv3, with checkpoint
        self.assertEqual(65339010432214603900175979833807329994044402934458085644623414103638016, chain.get_target(2015))
        # before DGWv3, without checkpoint
        self.assertEqual(0, chain.get_target(2016))
        # after DGWv3, with checkpoint
        self.assertEqual(62635231089126922960074598435273835921110428291665699134377033728, chain.get_target(461663))
        # after DGWv3, without checkpoint
        self.assertEqual(0, chain.get_target(461664))
        # after DGWv3, after the checkpoints. The headers are not saved yet.
        self.assertEqual(7112266753876343510151023106557578774485394364773876493401627,
                         chain.get_target(self.TIP, self.headers()))
        self.assertEqual(self.header(self.TIP)['bits'],
                         Blockchain.target_to_bits(7112266753876343510151023106557578774485394364773876493401627))

    def test_get_target_dgwv3_matches_the_bits_of_real_headers(self):
        headers = self.headers()
        # DGWv3 needs the previous 24 headers, which the checkpoints do not have
        for height in range(self.FIRST, self.FIRST + DGWV3_PAST_BLOCKS):
            self.assertEqual(0, self.chain.get_target(height, headers), msg=height)
        for height in range(self.FIRST + DGWV3_PAST_BLOCKS, self.TIP + 1):
            target = self.chain.get_target(height, headers)
            self.assertEqual(headers[height]['bits'], Blockchain.target_to_bits(target), msg=height)
        # one of the 24 headers is missing
        with self.assertRaises(MissingHeader):
            self.chain.get_target(self.TIP, self.headers(self.TIP - DGWV3_PAST_BLOCKS + 1))

    def _dgwv3_window(self, height: int, *, bits: int, spacing: int) -> dict:
        """The 24 headers before `height`: same bits, `spacing` seconds apart."""
        return {height - 1 - i: {'bits': bits, 'timestamp': 1_700_000_000 - i * spacing}
                for i in range(DGWV3_PAST_BLOCKS)}

    def test_get_target_dgwv3_timespan(self):
        """new target = (average of the last 24 targets) * (time the last 24 blocks took) / (24 * 90 seconds),
        where the timespan is limited to [1/3, 3] of what it should have been."""
        self.assertEqual(90, DGWV3_TARGET_SPACING)
        height = self.FIRST + 1000
        bits = 0x1a046d0c
        target = Blockchain.bits_to_target(bits)
        # blocks on schedule. (there are only 23 intervals between 24 blocks)
        window = self._dgwv3_window(height, bits=bits, spacing=90)
        self.assertEqual(target * 23 // 24, self.chain.get_target(height, window))
        # blocks twice as fast
        window = self._dgwv3_window(height, bits=bits, spacing=45)
        self.assertEqual(target * 23 // 48, self.chain.get_target(height, window))
        # the target cannot fall to less than a third
        for spacing in (0, 1, 30):
            window = self._dgwv3_window(height, bits=bits, spacing=spacing)
            self.assertEqual(target // 3, self.chain.get_target(height, window))
        # the target cannot more than triple
        for spacing in (300, 3600):
            window = self._dgwv3_window(height, bits=bits, spacing=spacing)
            self.assertEqual(target * 3, self.chain.get_target(height, window))
        # and it never exceeds the pow limit
        window = self._dgwv3_window(height, bits=0x1e0fffff, spacing=3600)
        self.assertEqual(MAX_TARGET, self.chain.get_target(height, window))

    def test_get_target_dgwv3_starts_24_blocks_after_the_fork(self):
        """As in Monacoin Core: min difficulty until 24 headers are above the Lyra2REv2 fork height."""
        bits = 0x1c009842
        target = Blockchain.bits_to_target(bits)
        fork_chunk = LYRA2REV2_FORK_HEIGHT // CHUNK_SIZE
        # pretend that the checkpoints end right before the fork
        with mock.patch.object(constants.BitcoinMainnet, "_cached_checkpoints", constants.net.CHECKPOINTS[:fork_chunk]):
            for height in (LYRA2REV2_FORK_HEIGHT, LYRA2REV2_FORK_HEIGHT + DGWV3_PAST_BLOCKS):
                window = self._dgwv3_window(height, bits=bits, spacing=90)
                self.assertEqual(MAX_TARGET, self.chain.get_target(height, window), msg=height)
            height = LYRA2REV2_FORK_HEIGHT + DGWV3_PAST_BLOCKS + 1
            window = self._dgwv3_window(height, bits=bits, spacing=90)
            self.assertEqual(target * 23 // 24, self.chain.get_target(height, window))

    def test_connect_headers_above_checkpoints(self):
        self.connect(self.FIRST, self.TIP)
        self.assertEqual(self.TIP, self.chain.height())
        self.assertEqual(self.TIP_HASH, self.chain.get_hash(self.TIP))
        self.assertEqual(self.header(self.TIP), self.chain.header_at_tip())
        # now the targets come from the headers file
        for height in range(self.FIRST + DGWV3_PAST_BLOCKS, self.TIP + 1):
            target = self.chain.get_target(height)
            self.assertEqual(self.header(height)['bits'], Blockchain.target_to_bits(target), msg=height)
        # competing chains are compared by their length. (the checkpoints do not have the targets
        # that would be needed to calculate the chainwork)
        self.assertEqual(self.TIP, self.chain.get_chainwork())
        self.assertEqual(self.FIRST, self.chain.get_chainwork(self.FIRST))

    def test_can_connect(self):
        self.connect(self.FIRST, self.TIP - 1)
        header = self.header(self.TIP)
        self.assertTrue(self.chain.can_connect(header))
        self.assertIs(self.chain, self.bc_mgr.can_connect(header))
        # insufficient pow
        self.assertFalse(self.chain.can_connect(self.header_with_bad_nonce(self.TIP)))
        # the bits are not what DGWv3 says
        self.assertFalse(self.chain.can_connect(self.header(self.TIP, bits=header['bits'] + 1)))
        self.assertFalse(self.chain.can_connect(self.header(self.TIP, bits=0x1e0fffff)))
        # does not build on our tip
        self.assertFalse(self.chain.can_connect(self.header(self.TIP, prev_block_hash=self.chain.get_hash(self.TIP - 2))))
        self.assertFalse(self.chain.can_connect(self.header(self.TIP, block_height=self.TIP + 1)))
        self.assertFalse(self.chain.can_connect(self.header(self.TIP - 1)))
        self.assertTrue(self.chain.can_connect(self.header(self.TIP - 1), check_height=False))

    def test_headers_that_are_not_pow_checked(self):
        """The checkpoints only have the target of the last header of each chunk, and DGWv3 needs 24
        previous headers: there is no pow check for the other headers below the checkpoints, and for
        the first 25 above them. Their hashes are still checked (prev_hash, checkpoints)."""
        # below the checkpoints: the last header of a chunk is checked. (see test_verify_header_scrypt)
        # Let's pretend it was the one before.
        header = self.header_with_bad_nonce(2015, block_height=2014)
        self.assertEqual(0, self.chain.get_target(2014))
        Blockchain.verify_header(header, header['prev_block_hash'], 0)
        with self.assertRaises(InvalidHeader):
            Blockchain.verify_header(header, "00" * 32, 0)
        with self.assertRaises(InvalidHeader):
            Blockchain.verify_header(header, header['prev_block_hash'], 0,
                                     expected_header_hash=hash_header(self.header(2015)))
        # above the checkpoints
        headers = self.headers()
        self.assertEqual(self.FIRST + 25, self.FIRST_CHECKED)
        for height in (self.FIRST, self.FIRST + 1, self.FIRST_CHECKED - 1):
            header = self.header_with_bad_nonce(height)
            target = self.chain.get_target(height, headers)
            Blockchain.verify_header(header, header['prev_block_hash'], target)
            with self.assertRaises(InvalidHeader):
                Blockchain.verify_header(header, "00" * 32, target)
        header = self.header_with_bad_nonce(self.FIRST_CHECKED)
        target = self.chain.get_target(self.FIRST_CHECKED, headers)
        with self.assertRaises(InvalidHeader):
            Blockchain.verify_header(header, header['prev_block_hash'], target)
        Blockchain.verify_header(self.header(self.FIRST_CHECKED), header['prev_block_hash'], target)

    def test_no_pow_check_on_testnet(self):
        header = self.header_with_bad_nonce(self.TIP)
        # note: do not let the testnet checkpoints get cached, regtest would inherit them
        with mock.patch.object(constants.BitcoinTestnet, "_cached_checkpoints", []):
            constants.BitcoinTestnet.set_as_network()
            try:
                self.assertEqual(0, self.chain.get_target(self.TIP, self.headers()))
                Blockchain.verify_header(header, header['prev_block_hash'], 0)
                with self.assertRaises(InvalidHeader):
                    Blockchain.verify_header(header, "00" * 32, 0)
            finally:
                constants.BitcoinMainnet.set_as_network()
        with self.assertRaises(InvalidHeader):
            Blockchain.verify_header(header, header['prev_block_hash'], self.chain.get_target(self.TIP, self.headers()))

    def _chunk(self, *, last: int = TIP, bad_nonce_at: int = None) -> bytes:
        headers = self.headers(self.FIRST, last)
        if bad_nonce_at is not None:
            headers[bad_nonce_at] = self.header_with_bad_nonce(bad_nonce_at)
        return b"".join(serialize_header(headers[height]) for height in sorted(headers))

    def test_verify_chunk(self):
        index = self.FIRST // CHUNK_SIZE
        self.chain.verify_chunk(index, self._chunk())
        # insufficient pow
        for height in (self.FIRST_CHECKED, self.TIP - 10, self.TIP):
            with self.assertRaises(InvalidHeader, msg=height):
                self.chain.verify_chunk(index, self._chunk(bad_nonce_at=height))
        # the first headers are not pow-checked, but the next header commits to their hash
        for height in (self.FIRST, self.FIRST_CHECKED - 1):
            with self.assertRaises(InvalidHeader, msg=height):
                self.chain.verify_chunk(index, self._chunk(bad_nonce_at=height))
            self.chain.verify_chunk(index, self._chunk(last=height, bad_nonce_at=height))
        # does not connect to the checkpoints
        with self.assertRaises(InvalidHeader):
            self.chain.verify_chunk(index, self._chunk()[HEADER_SIZE:])

    def test_connect_chunk(self):
        index = self.FIRST // CHUNK_SIZE
        self.assertFalse(self.chain.connect_chunk(index, self._chunk(bad_nonce_at=self.TIP)))
        self.assertEqual(self.FIRST - 1, self.chain.height())
        self.assertTrue(self.chain.connect_chunk(index, self._chunk()))
        self.assertEqual(self.TIP, self.chain.height())
        self.assertEqual(self.TIP_HASH, self.chain.get_hash(self.TIP))
        self.assertEqual(self.header(self.TIP), self.chain.read_header(self.TIP))
