import hashlib
import unittest
from unittest import mock

from electrum_mona import blockchain
from electrum_mona.bitcoin import hash_encode
from electrum_mona.blockchain import serialize_header, deserialize_header, pow_hash_header
from electrum_mona.scrypt import scrypt_1024_1_1_80
from electrum_mona.util import bfh

from . import ElectrumTestCase


class Test_scrypt(ElectrumTestCase):
    """scrypt(N=1024, r=1, p=1) of a block header, salted with itself.
    This was the proof-of-work of Monacoin below height 450000. (as in Litecoin)
    """

    # (raw header, pow hash)
    VECTORS = [
        # Monacoin block 12095
        ("0200000011f1fe21e0b66dc214be46366465cb95d29830e31ddd225a11349a836a993bf7b5db36b3e5593d039779bff204d132b65ee029a2e499ebeb5a4b19cbe862eee2b623cc5276676c1c000e1c60",
         "00000000335c88172421df73a1c1f22f4d7c23d8ef34c78d728c4eff3ba24a34"),
        # from Litecoin Core, src/test/scrypt_tests.cpp
        ("020000004c1271c211717198227392b029a64a7971931d351b387bb80db027f270411e398a07046f7d4a08dd815412a8712f874a7ebf0507e3878bd24e20a3b73fd750a667d2f451eac7471b00de6659",
         "00000000002bef4107f882f6115e0b01f348d21195dacd3582aa2dabd7985806"),
        ("0200000011503ee6a855e900c00cfdd98f5f55fffeaee9b6bf55bea9b852d9de2ce35828e204eef76acfd36949ae56d1fbe81c1ac9c0209e6331ad56414f9072506a77f8c6faf551eac7471b00389d01",
         "00000000003a0d11bdd5eb634e08b7feddcfbbf228ed35d250daf19f1c88fc94"),
    ]

    def test_scrypt(self):
        header = {'block_height': 12095, 'nonce': 1612451328, 'timestamp': 1389110198, 'version': 2, 'prev_block_hash': 'f73b996a839a34115a22dd1de33098d295cb65643646be14c26db6e021fef111', 'merkle_root': 'e2ee62e8cb194b5aebeb99e4a229e05eb632d104f2bf7997033d59e5b336dbb5', 'bits': 476866422}
        self.assertEqual(self.VECTORS[0][0], serialize_header(header).hex())
        powhash = hash_encode(scrypt_1024_1_1_80(serialize_header(header)))
        self.assertEqual(powhash, '00000000335c88172421df73a1c1f22f4d7c23d8ef34c78d728c4eff3ba24a34')
        self.assertEqual(powhash, pow_hash_header(header))

    def test_pure_python_implementation(self):
        for raw_header, pow_hash in self.VECTORS:
            self.assertEqual(pow_hash, hash_encode(scrypt_1024_1_1_80(bfh(raw_header))))

    @unittest.skipUnless(hasattr(hashlib, "scrypt"), "hashlib was built without scrypt (needs OpenSSL 1.1+)")
    def test_hashlib_implementation(self):
        with mock.patch("electrum_mona.scrypt.scrypt_1024_1_1_80", side_effect=AssertionError("fallback used")):
            for raw_header, pow_hash in self.VECTORS:
                self.assertEqual(pow_hash, hash_encode(blockchain._scrypt_1024_1_1_80(bfh(raw_header))))

    def test_fallback_to_pure_python_implementation(self):
        for exc in (AttributeError, ValueError):
            with mock.patch.object(hashlib, "scrypt", side_effect=exc, create=True):
                for raw_header, pow_hash in self.VECTORS:
                    self.assertEqual(pow_hash, hash_encode(blockchain._scrypt_1024_1_1_80(bfh(raw_header))))

    def test_pow_hash_header_uses_scrypt_below_the_lyra2rev2_fork(self):
        raw_header, pow_hash = self.VECTORS[0]
        self.assertEqual(pow_hash, pow_hash_header(deserialize_header(bfh(raw_header), 12095)))
        self.assertEqual(pow_hash, pow_hash_header(deserialize_header(bfh(raw_header), 449999)))
        self.assertNotEqual(pow_hash, pow_hash_header(deserialize_header(bfh(raw_header), 450000)))

    def test_input_must_be_a_raw_header(self):
        raw_header = bfh(self.VECTORS[0][0])
        for bad_input in (raw_header[:79], raw_header + b"\x00", b"", raw_header.hex(), bytearray(raw_header), None):
            with self.assertRaises(ValueError):
                scrypt_1024_1_1_80(bad_input)
