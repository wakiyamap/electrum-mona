import unittest
from unittest import mock
import shutil
import tempfile
from typing import Sequence
import asyncio
import copy

from electrum_mona import storage, bitcoin, keystore, bip32, wallet
from electrum_mona import Transaction
from electrum_mona import SimpleConfig
from electrum_mona.address_synchronizer import TX_HEIGHT_UNCONFIRMED, TX_HEIGHT_UNCONF_PARENT
from electrum_mona.wallet import sweep, Multisig_Wallet, Standard_Wallet, Imported_Wallet, restore_wallet_from_text, Abstract_Wallet
from electrum_mona.util import bfh, bh2u, create_and_start_event_loop
from electrum_mona.transaction import TxOutput, Transaction, PartialTransaction, PartialTxOutput, PartialTxInput, tx_from_any
from electrum_mona.mnemonic import seed_type

#from electrum_mona.plugins.trustedcoin import trustedcoin

from . import TestCaseForTestnet
from . import ElectrumTestCase


UNICODE_HORROR_HEX = 'e282bf20f09f988020f09f98882020202020e3818620e38191e3819fe381be20e3828fe3828b2077cda2cda2cd9d68cda16fcda2cda120ccb8cda26bccb5cd9f6eccb4cd98c7ab77ccb8cc9b73cd9820cc80cc8177cd98cda2e1b8a9ccb561d289cca1cda27420cca7cc9568cc816fccb572cd8fccb5726f7273cca120ccb6cda1cda06cc4afccb665cd9fcd9f20ccb6cd9d696ecda220cd8f74cc9568ccb7cca1cd9f6520cd9fcd9f64cc9b61cd9c72cc95cda16bcca2cca820cda168ccb465cd8f61ccb7cca2cca17274cc81cd8f20ccb4ccb7cda0c3b2ccb5ccb666ccb82075cca7cd986ec3adcc9bcd9c63cda2cd8f6fccb7cd8f64ccb8cda265cca1cd9d3fcd9e'
UNICODE_HORROR = bfh(UNICODE_HORROR_HEX).decode('utf-8')
assert UNICODE_HORROR == '₿ 😀 😈     う けたま わる w͢͢͝h͡o͢͡ ̸͢k̵͟n̴͘ǫw̸̛s͘ ̀́w͘͢ḩ̵a҉̡͢t ̧̕h́o̵r͏̵rors̡ ̶͡͠lį̶e͟͟ ̶͝in͢ ͏t̕h̷̡͟e ͟͟d̛a͜r̕͡k̢̨ ͡h̴e͏a̷̢̡rt́͏ ̴̷͠ò̵̶f̸ u̧͘ní̛͜c͢͏o̷͏d̸͢e̡͝?͞'


class WalletIntegrityHelper:

    gap_limit = 1  # make tests run faster

    @classmethod
    def check_seeded_keystore_sanity(cls, test_obj, ks):
        test_obj.assertTrue(ks.is_deterministic())
        test_obj.assertFalse(ks.is_watching_only())
        test_obj.assertFalse(ks.can_import())
        test_obj.assertTrue(ks.has_seed())

    @classmethod
    def check_xpub_keystore_sanity(cls, test_obj, ks):
        test_obj.assertTrue(ks.is_deterministic())
        test_obj.assertTrue(ks.is_watching_only())
        test_obj.assertFalse(ks.can_import())
        test_obj.assertFalse(ks.has_seed())

    @classmethod
    def create_standard_wallet(cls, ks, *, config: SimpleConfig, gap_limit=None):
        db = storage.WalletDB('', manual_upgrades=False)
        db.put('keystore', ks.dump())
        db.put('gap_limit', gap_limit or cls.gap_limit)
        w = Standard_Wallet(db, None, config=config)
        w.synchronize()
        return w

    @classmethod
    def create_imported_wallet(cls, *, config: SimpleConfig, privkeys: bool):
        db = storage.WalletDB('', manual_upgrades=False)
        if privkeys:
            k = keystore.Imported_KeyStore({})
            db.put('keystore', k.dump())
        w = Imported_Wallet(db, None, config=config)
        return w

    @classmethod
    def create_multisig_wallet(cls, keystores: Sequence, multisig_type: str, *,
                               config: SimpleConfig, gap_limit=None):
        """Creates a multisig wallet."""
        db = storage.WalletDB('', manual_upgrades=True)
        for i, ks in enumerate(keystores):
            cosigner_index = i + 1
            db.put('x%d/' % cosigner_index, ks.dump())
        db.put('wallet_type', multisig_type)
        db.put('gap_limit', gap_limit or cls.gap_limit)
        w = Multisig_Wallet(db, None, config=config)
        w.synchronize()
        return w


class TestWalletKeystoreAddressIntegrityForMainnet(ElectrumTestCase):

    def setUp(self):
        super().setUp()
        self.config = SimpleConfig({'electrum_path': self.electrum_path})

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_electrum_seed_standard(self, mock_save_db):
        seed_words = 'cycle rocket west magnet parrot shuffle foot correct salt library feed song'
        self.assertEqual(seed_type(seed_words), 'standard')

        ks = keystore.from_seed(seed_words, '', False)

        WalletIntegrityHelper.check_seeded_keystore_sanity(self, ks)
        self.assertTrue(isinstance(ks, keystore.BIP32_KeyStore))

        self.assertEqual(ks.xprv, 'xprv9s21ZrQH143K32jECVM729vWgGq4mUDJCk1ozqAStTphzQtCTuoFmFafNoG1g55iCnBTXUzz3zWnDb5CVLGiFvmaZjuazHDL8a81cPQ8KL6')
        self.assertEqual(ks.xpub, 'xpub661MyMwAqRbcFWohJWt7PHsFEJfZAvw9ZxwQoDa4SoMgsDDM1T7WK3u9E4edkC4ugRnZ8E4xDZRpk8Rnts3Nbt97dPwT52CwBdDWroaZf8U')

        w = WalletIntegrityHelper.create_standard_wallet(ks, config=self.config)
        self.assertEqual(w.txin_type, 'p2pkh')

        self.assertEqual(w.get_receiving_addresses()[0], 'MVGv8KgR3wf5XW9qHN53FCDP3AvSabYdPv')
        self.assertEqual(w.get_change_addresses()[0], 'MSLpDyG6fKXKivZpU9gF7yA1ZNMzNFCUjK')

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_electrum_seed_segwit(self, mock_save_db):
        seed_words = 'bitter grass shiver impose acquire brush forget axis eager alone wine silver'
        self.assertEqual(seed_type(seed_words), 'segwit')

        ks = keystore.from_seed(seed_words, '', False)

        WalletIntegrityHelper.check_seeded_keystore_sanity(self, ks)
        self.assertTrue(isinstance(ks, keystore.BIP32_KeyStore))

        self.assertEqual(ks.xprv, 'zprvAZswDvNeJeha8qZ8g7efN3FXYVJLaEUsE9TW6qXDEbVe74AZ75c2sZFZXPNFzxnhChDQ89oC8C5AjWwHmH1HeRKE1c4kKBQAmjUDdKDUZw2')
        self.assertEqual(ks.xpub, 'zpub6nsHdRuY92FsMKdbn9BfjBCG6X8pyhCibNP6uDvpnw2cyrVhecvHRMa3Ne8kdJZxjxgwnpbHLkcR4bfnhHy6auHPJyDTQ3kianeuVLdkCYQ')

        w = WalletIntegrityHelper.create_standard_wallet(ks, config=self.config)
        self.assertEqual(w.txin_type, 'p2wpkh')

        self.assertEqual(w.get_receiving_addresses()[0], 'mona1q3g5tmkmlvxryhh843v4dz026avatc0zz8fpnsg')
        self.assertEqual(w.get_change_addresses()[0], 'mona1qdy94n2q5qcp0kg7v9yzwe6wvfkhnvyzjad9y8q')

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_electrum_seed_segwit_passphrase(self, mock_save_db):
        seed_words = 'bitter grass shiver impose acquire brush forget axis eager alone wine silver'
        self.assertEqual(seed_type(seed_words), 'segwit')

        ks = keystore.from_seed(seed_words, UNICODE_HORROR, False)

        WalletIntegrityHelper.check_seeded_keystore_sanity(self, ks)
        self.assertTrue(isinstance(ks, keystore.BIP32_KeyStore))

        self.assertEqual(ks.xprv, 'zprvAZDmEQiCLUcZXPfrBXoksCD2R6RMAzAre7SUyBotibisy9c7vGhLYvHaP3d9rYU12DKAWdZfscPNA7qEPgTkCDqX5sE93ryAJAQvkDbfLxU')
        self.assertEqual(ks.xpub, 'zpub6nD7dvF6ArArjskKHZLmEL9ky8FqaSti1LN5maDWGwFrqwwGTp1b6ic4EHwciFNaYDmCXcQYxXSiF9BjcLCMPcaYkVN2nQD6QjYQ8vpSR3Z')

        w = WalletIntegrityHelper.create_standard_wallet(ks, config=self.config)
        self.assertEqual(w.txin_type, 'p2wpkh')

        self.assertEqual(w.get_receiving_addresses()[0], 'mona1qx94dutas7ysn2my645cyttujrms5d9p566vls6')
        self.assertEqual(w.get_change_addresses()[0], 'mona1qcywwsy87sdp8vz5rfjh3sxdv6rt95kujfnkn2f')

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_electrum_seed_old(self, mock_save_db):
        seed_words = 'powerful random nobody notice nothing important anyway look away hidden message over'
        self.assertEqual(seed_type(seed_words), 'old')

        ks = keystore.from_seed(seed_words, '', False)

        WalletIntegrityHelper.check_seeded_keystore_sanity(self, ks)
        self.assertTrue(isinstance(ks, keystore.Old_KeyStore))

        self.assertEqual(ks.mpk, 'e9d4b7866dd1e91c862aebf62a49548c7dbf7bcc6e4b7b8c9da820c7737968df9c09d5a3e271dc814a29981f81b3faaf2737b551ef5dcc6189cf0f8252c442b3')

        w = WalletIntegrityHelper.create_standard_wallet(ks, config=self.config)
        self.assertEqual(w.txin_type, 'p2pkh')

        self.assertEqual(w.get_receiving_addresses()[0], 'MNCPTc38CQXQtXzmyKRnHPEdSe9A6RWaht')
        self.assertEqual(w.get_change_addresses()[0], 'MSKfNFBVnGTNao6UiCV2uVwGF5kvm2QBtq')

#    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
#    def test_electrum_seed_2fa_legacy(self, mock_save_db):
#        seed_words = 'kiss live scene rude gate step hip quarter bunker oxygen motor glove'
#        self.assertEqual(seed_type(seed_words), '2fa')

#        xprv1, xpub1, xprv2, xpub2 = trustedcoin.TrustedCoinPlugin.xkeys_from_seed(seed_words, '')

#        ks1 = keystore.from_xprv(xprv1)
#        self.assertTrue(isinstance(ks1, keystore.BIP32_KeyStore))
#        self.assertEqual(ks1.xprv, 'xprv9uraXy9F3HP7i8QDqwNTBiD8Jf4bPD4Epif8cS8qbUbgeidUesyZpKmzfcSeHutsGfFnjgih7kzwTB5UQVRNB5LoXaNc8pFusKYx3KVVvYR')
#        self.assertEqual(ks1.xpub, 'xpub68qvwUg8sewQvcUgwxuTYr9rrgu5nfn6BwajQpYT9p8fXWxdCRHpN86UWruWJAD1ede8Sv8ERrTa22Gyc4SBfm7zFpcyoVWVBKCVwnw6s1J')
#        self.assertEqual(ks1.xpub, xpub1)

#        ks2 = keystore.from_xprv(xprv2)
#        self.assertTrue(isinstance(ks2, keystore.BIP32_KeyStore))
#        self.assertEqual(ks2.xprv, 'xprv9uraXy9F3HP7kKSiRAvLV7Nrjj7YzspDys7dvGLLu4tLZT49CEBxPWp88dHhVxvZ69SHrPQMUCWjj4Ka2z9kNvs1HAeEf3extGGeSWqEVqf')
#        self.assertEqual(ks2.xpub, 'xpub68qvwUg8sewQxoXBXCTLrFKbHkx3QLY5M63EiejxTQRKSFPHjmWCwK8byvZMM2wZNYA3SmxXoma3M1zxhGESHZwtB7SwrxRgKXAG8dCD2eS')
#        self.assertEqual(ks2.xpub, xpub2)

#        long_user_id, short_id = trustedcoin.get_user_id(
#            {'x1/': {'xpub': xpub1},
#             'x2/': {'xpub': xpub2}})
#        xtype = bip32.xpub_type(xpub1)
#        xpub3 = trustedcoin.make_xpub(trustedcoin.get_signing_xpub(xtype), long_user_id)
#        ks3 = keystore.from_xpub(xpub3)
#        WalletIntegrityHelper.check_xpub_keystore_sanity(self, ks3)
#        self.assertTrue(isinstance(ks3, keystore.BIP32_KeyStore))

#        w = WalletIntegrityHelper.create_multisig_wallet([ks1, ks2, ks3], '2of3', config=self.config)
#        self.assertEqual(w.txin_type, 'p2sh')

#        self.assertEqual(w.get_receiving_addresses()[0], '35L8XmCDoEBKeaWRjvmZvoZvhp8BXMMMPV')
#        self.assertEqual(w.get_change_addresses()[0], '3PeZEcumRqHSPNN43hd4yskGEBdzXgY8Cy')

#    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
#    def test_electrum_seed_2fa_segwit(self, mock_save_db):
#        seed_words = 'universe topic remind silver february ranch shine worth innocent cattle enhance wise'
#        self.assertEqual(seed_type(seed_words), '2fa_segwit')

#        xprv1, xpub1, xprv2, xpub2 = trustedcoin.TrustedCoinPlugin.xkeys_from_seed(seed_words, '')

#        ks1 = keystore.from_xprv(xprv1)
#        self.assertTrue(isinstance(ks1, keystore.BIP32_KeyStore))
#        self.assertEqual(ks1.xprv, 'ZprvAm1R3RZMrkSLYKZer8QECGoc8oA1RQuKfsztHkBTmi2yF8RhmN1JRb7Ag69mMrL88sP67WiaegaSSDnKndorWEpFr7a5B2QgrD7TkERSYX6')
#        self.assertEqual(ks1.xpub, 'Zpub6yzmSw6Fh7zdkoe7x9wEZQkLgpzVpsdB36vV68b5L3Zx7vkrJuKYyPReXMSjBegmtUjFBxP2uZEdL87cYvtTtGaVuwtRRCTSFUsoAdKZMge')
#        self.assertEqual(ks1.xpub, xpub1)

#        ks2 = keystore.from_xprv(xprv2)
#        self.assertTrue(isinstance(ks2, keystore.BIP32_KeyStore))
#        self.assertEqual(ks2.xprv, 'ZprvAm1R3RZMrkSLab4jVKTwuroBgKEfnsmK9CQa1ErkuRzpsPauYuv9z2UzhDNn9YgbLHcmXpmxbNq4MdDRAUM5B2N9Wr3Uq9yp2c4AtTJDFdi')
#        self.assertEqual(ks2.xpub, 'Zpub6yzmSw6Fh7zdo59CbLzxGzjvEM5ACLVAWRLAodGNTmXokBv46TEQXpoUYUaoxPCeynysxg7APfScikCQ2jhCfM3NcNEk46BCVfSSrdrSkbR')
#        self.assertEqual(ks2.xpub, xpub2)

#        long_user_id, short_id = trustedcoin.get_user_id(
#            {'x1/': {'xpub': xpub1},
#             'x2/': {'xpub': xpub2}})
#        xtype = bip32.xpub_type(xpub1)
#        xpub3 = trustedcoin.make_xpub(trustedcoin.get_signing_xpub(xtype), long_user_id)
#        ks3 = keystore.from_xpub(xpub3)
#        WalletIntegrityHelper.check_xpub_keystore_sanity(self, ks3)
#        self.assertTrue(isinstance(ks3, keystore.BIP32_KeyStore))

#        w = WalletIntegrityHelper.create_multisig_wallet([ks1, ks2, ks3], '2of3', config=self.config)
#        self.assertEqual(w.txin_type, 'p2wsh')

#        self.assertEqual(w.get_receiving_addresses()[0], 'bc1qpmufh0zjp5prfsrk2yskcy82sa26srqkd97j0457andc6m0gh5asw7kqd2')
#        self.assertEqual(w.get_change_addresses()[0], 'bc1qd4q50nft7kxm9yglfnpup9ed2ukj3tkxp793y0zya8dc9m39jcwq308dxz')

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_bip39_seed_bip44_standard(self, mock_save_db):
        seed_words = 'treat dwarf wealth gasp brass outside high rent blood crowd make initial'
        self.assertEqual(keystore.bip39_is_checksum_valid(seed_words), (True, True))

        ks = keystore.from_bip39_seed(seed_words, '', "m/44'/22'/0'")

        self.assertTrue(isinstance(ks, keystore.BIP32_KeyStore))

        self.assertEqual(ks.xprv, 'xprv9zVbADshjvA9gHUa8hVtVooXMEr9Zs2Rir6buwPY3bxodxYiqfKdGrMWq2TbKbrA3AJ6s9DtJgywm18qMdbpmtUV2zfcqbzxsbEvZQXPjRD')
        self.assertEqual(ks.xpub, 'xpub6DUwZjQbaHiStmZ3Ej2trwkFuGgdyKkH652CiKo9bwVnWkssPCdspefzgJtxsZd9TnxUHnrADeNMhx22G9io7DwnMh3HdEWSxt6jAbaH5Zp')

        w = WalletIntegrityHelper.create_standard_wallet(ks, config=self.config)
        self.assertEqual(w.txin_type, 'p2pkh')

        self.assertEqual(w.get_receiving_addresses()[0], 'MS5xvLi9MztCEBdct5TaGWBxgbxkbdKioY')
        self.assertEqual(w.get_change_addresses()[0], 'MU8uE2nH1pkVt7outQMjki68do5Pp6gzK7')

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_bip39_seed_bip44_standard_passphrase(self, mock_save_db):
        seed_words = 'treat dwarf wealth gasp brass outside high rent blood crowd make initial'
        self.assertEqual(keystore.bip39_is_checksum_valid(seed_words), (True, True))

        ks = keystore.from_bip39_seed(seed_words, UNICODE_HORROR, "m/44'/22'/0'")

        self.assertTrue(isinstance(ks, keystore.BIP32_KeyStore))

        self.assertEqual(ks.xprv, 'xprv9yT9wTgHbNGsd8cUWegrXUmvGRWYnzhBVnKXBABGEydimfVe13zuCUYposYjqFE5rDc2jj1W9F5MFuA59AfbPmAX2Lp7nMVQ6XgbaZbx2YC')
        self.assertEqual(ks.xpub, 'xpub6CSWLyDBRjqAqcgwcgDrtciepTM3CTR2s1F7yYasoKAheTpnYbK9kGsJfBPeBXjfHJsiEUs1vzto6JiK8MQTfFmXQgZSxFQSNbTsWExoBx7')

        w = WalletIntegrityHelper.create_standard_wallet(ks, config=self.config)
        self.assertEqual(w.txin_type, 'p2pkh')

        self.assertEqual(w.get_receiving_addresses()[0], 'MPupn7dRc9tSpayLQrk6j6UGidRWbquccD')
        self.assertEqual(w.get_change_addresses()[0], 'MR3eRFkFt9rFVPM6eFi9pkDprm4shTEEf6')

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_bip39_seed_bip49_p2sh_segwit(self, mock_save_db):
        seed_words = 'treat dwarf wealth gasp brass outside high rent blood crowd make initial'
        self.assertEqual(keystore.bip39_is_checksum_valid(seed_words), (True, True))

        ks = keystore.from_bip39_seed(seed_words, '', "m/49'/22'/0'")

        self.assertTrue(isinstance(ks, keystore.BIP32_KeyStore))

        self.assertEqual(ks.xprv, 'yprvAJDepkT9xNsXwTx6q7r6F7hZHFRTgbCpMagfDnqNw6uEusMoUdvFhY8BYg7Xm6qM1X5jMyBZKwMindkYyEqv5yGVCEHWDKbq4cUG3uoatXF')
        self.assertEqual(ks.xpub, 'ypub6XD1EFz3nkRq9x2Zw9P6cFeHqHFx63vfiocG2BEzVSSDnfgx2BEWFLSfPy6qxQAESUApw5zQejoSPorqxzoV4y2rDnrVzuR93GcUxar2BBf')

        w = WalletIntegrityHelper.create_standard_wallet(ks, config=self.config)
        self.assertEqual(w.txin_type, 'p2wpkh-p2sh')

        self.assertEqual(w.get_receiving_addresses()[0], 'PNh2J16Tz4pcKfiJ7MBjD2b7o5kvPdSYcd')
        self.assertEqual(w.get_change_addresses()[0], 'PFiGomM32uDKXXcEs1LM57GpasTorJnb7J')

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_bip39_seed_bip84_native_segwit(self, mock_save_db):
        # test case from bip84
        seed_words = 'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about'
        self.assertEqual(keystore.bip39_is_checksum_valid(seed_words), (True, True))

        ks = keystore.from_bip39_seed(seed_words, '', "m/84'/22'/0'")

        self.assertTrue(isinstance(ks, keystore.BIP32_KeyStore))

        self.assertEqual(ks.xprv, 'zprvAcZ5F4WJkcPfLQbTgjhcNt4sxGSXFxHWyLZsxd8fENCMFKRhc32Xjdwo4WMje5zhNzy2WeqoHYWFhNittqCHD96Bj1mM7eFVdf5oNhahGtx')
        self.assertEqual(ks.xpub, 'zpub6qYRea3CaywxYtfvnmEck21cWJH1fR1NLZVUm1YGnhjL87kr9aLnHSGGumibCJWR9SswtGCuK15Z57WC18oJzkAhZXCTcWTcdHJMfbydrok')

        w = WalletIntegrityHelper.create_standard_wallet(ks, config=self.config)
        self.assertEqual(w.txin_type, 'p2wpkh')

        self.assertEqual(w.get_receiving_addresses()[0], 'mona1qpgmk2vdx5ve6xm93rplw9d6uszpe4am5my7x72')
        self.assertEqual(w.get_change_addresses()[0], 'mona1q7t5p3u22skphsflmxnta7tjw8kspf7s35q793e')

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_electrum_multisig_seed_standard(self, mock_save_db):
        seed_words = 'blast uniform dragon fiscal ensure vast young utility dinosaur abandon rookie sure'
        self.assertEqual(seed_type(seed_words), 'standard')

        ks1 = keystore.from_seed(seed_words, '', True)
        WalletIntegrityHelper.check_seeded_keystore_sanity(self, ks1)
        self.assertTrue(isinstance(ks1, keystore.BIP32_KeyStore))
        self.assertEqual(ks1.xprv, 'xprv9s21ZrQH143K3t9vo23J3hajRbzvkRLJ6Y1zFrUFAfU3t8oooMPfb7f87cn5KntgqZs5nipZkCiBFo5ZtaSD2eDo7j7CMuFV8Zu6GYLTpY6')
        self.assertEqual(ks1.xpub, 'xpub661MyMwAqRbcGNEPu3aJQqXTydqR9t49Tkwb4Esrj112kw8xLthv8uybxvaki4Ygt9xiwZUQGeFTG7T2TUzR3eA4Zp3aq5RXsABHFBUrq4c')

        # electrum seed: ghost into match ivory badge robot record tackle radar elbow traffic loud
        ks2 = keystore.from_xpub('xpub661MyMwAqRbcGfCPEkkyo5WmcrhTq8mi3xuBS7VEZ3LYvsgY1cCFDbenT33bdD12axvrmXhuX3xkAbKci3yZY9ZEk8vhLic7KNhLjqdh5ec')
        WalletIntegrityHelper.check_xpub_keystore_sanity(self, ks2)
        self.assertTrue(isinstance(ks2, keystore.BIP32_KeyStore))

        w = WalletIntegrityHelper.create_multisig_wallet([ks1, ks2], '2of2', config=self.config)
        self.assertEqual(w.txin_type, 'p2sh')

        self.assertEqual(w.get_receiving_addresses()[0], 'P9dsGqeaBYYnzUE8eeEhDUfKLEQhDZaf7h')
        self.assertEqual(w.get_change_addresses()[0], 'PDRgAfCGMWN9gNheJLWRjYNokub1jUeHve')

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_electrum_multisig_seed_segwit(self, mock_save_db):
        seed_words = 'snow nest raise royal more walk demise rotate smooth spirit canyon gun'
        self.assertEqual(seed_type(seed_words), 'segwit')

        ks1 = keystore.from_seed(seed_words, '', True)
        WalletIntegrityHelper.check_seeded_keystore_sanity(self, ks1)
        self.assertTrue(isinstance(ks1, keystore.BIP32_KeyStore))
        self.assertEqual(ks1.xprv, 'ZprvAjxLRqPiDfPDxXrm8JvcoCGRAW6xUtktucG6AMtdzaEbTEJN8qcECvujfhtDU3jLJ9g3Dr3Gz5m1ypfMs8iSUh62gWyHZ73bYLRWyeHf6y4')
        self.assertEqual(ks1.xpub, 'Zpub6xwgqLvc42wXB1wEELTdALD9iXwStMUkGqBgxkJFYumaL2dWgNvUkjEDWyDFZD3fZuDWDzd1KQJ4NwVHS7hs6H6QkpNYSShfNiUZsgMdtNg')

        # electrum seed: hedgehog sunset update estate number jungle amount piano friend donate upper wool
        ks2 = keystore.from_xpub('Zpub6y4oYeETXAbzLNg45wcFDGwEG3vpgsyMJybiAfi2pJtNF3i3fJVxK2BeZJaw7VeKZm192QHvXP3uHDNpNmNDbQft9FiMzkKUhNXQafUMYUY')
        WalletIntegrityHelper.check_xpub_keystore_sanity(self, ks2)
        self.assertTrue(isinstance(ks2, keystore.BIP32_KeyStore))

        w = WalletIntegrityHelper.create_multisig_wallet([ks1, ks2], '2of2', config=self.config)
        self.assertEqual(w.txin_type, 'p2wsh')

        self.assertEqual(w.get_receiving_addresses()[0], 'mona1qvzezdcv6vs5h45ugkavp896e0nde5c5lg5h0fwe2xyfhnpkxq6gqh82mms')
        self.assertEqual(w.get_change_addresses()[0], 'mona1qxqf840dqswcmu7a8v82fj6ej0msx08flvuy6kngr7axstjcaq6usv36vn9')

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_bip39_multisig_seed_bip45_standard(self, mock_save_db):
        seed_words = 'treat dwarf wealth gasp brass outside high rent blood crowd make initial'
        self.assertEqual(keystore.bip39_is_checksum_valid(seed_words), (True, True))

        ks1 = keystore.from_bip39_seed(seed_words, '', "m/45'/0")
        self.assertTrue(isinstance(ks1, keystore.BIP32_KeyStore))
        self.assertEqual(ks1.xprv, 'xprv9vyEFyXf7pYVv4eDU3hhuCEAHPHNGuxX73nwtYdpbLcqwJCPwFKknAK8pHWuHHBirCzAPDZ7UJHrYdhLfn1NkGp9rk3rVz2aEqrT93qKRD9')
        self.assertEqual(ks1.xpub, 'xpub69xafV4YxC6o8Yiga5EiGLAtqR7rgNgNUGiYgw3S9g9pp6XYUne1KxdcfYtxwmA3eBrzMFuYcNQKfqsXCygCo4GxQFHfywxpUbKNfYvGJka')

        # bip39 seed: tray machine cook badge night page project uncover ritual toward person enact
        # der: m/45'/0
        ks2 = keystore.from_xpub('xpub6B26nSWddbWv7J3qQn9FbwPPQktSBdPQfLfHhRK4375QoZq8fvM8rQey1koGSTxC5xVoMzNMaBETMUmCqmXzjc8HyAbN7LqrvE4ovGRwNGg')
        WalletIntegrityHelper.check_xpub_keystore_sanity(self, ks2)
        self.assertTrue(isinstance(ks2, keystore.BIP32_KeyStore))

        w = WalletIntegrityHelper.create_multisig_wallet([ks1, ks2], '2of2', config=self.config)
        self.assertEqual(w.txin_type, 'p2sh')

        self.assertEqual(w.get_receiving_addresses()[0], 'PRHcdTh8PX8L4xzJvLJABYiAXDzeGQDXGw')
        self.assertEqual(w.get_change_addresses()[0], 'PNB8TLs5yEwqi7XyJvpEXHapQfWsSNQgja')

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_bip39_multisig_seed_p2sh_segwit(self, mock_save_db):
        # bip39 seed: pulse mixture jazz invite dune enrich minor weapon mosquito flight fly vapor
        # der: m/49'/0'/0'
        # NOTE: there is currently no bip43 standard derivation path for p2wsh-p2sh
        ks1 = keystore.from_xprv('YprvAUXFReVvDjrPerocC3FxVH748sJUTvYjkAhtKop5VnnzVzMEHr1CHrYQKZwfJn1As3X4LYMav6upxd5nDiLb6SCjRZrBH76EFvyQAG4cn79')
        self.assertTrue(isinstance(ks1, keystore.BIP32_KeyStore))
        self.assertEqual(ks1.xpub, 'Ypub6hWbqA2p47QgsLt5J4nxrR3ngu8xsPGb7PdV8CDh48KyNngNqPKSqertAqYhQ4umELu1UsZUCYfj9XPA6AdSMZWDZQobwF7EJ8uNrECaZg1')

        # bip39 seed: slab mixture skin evoke harsh tattoo rare crew sphere extend balcony frost
        # der: m/49'/0'/0'
        ks2 = keystore.from_xpub('Ypub6iNDhL4WWq5kFZcdFqHHwX4YTH4rYGp8xbndpRrY7WNZFFRfogSrL7wRTajmVHgR46AT1cqUG1mrcRd7h1WXwBsgX2QvT3zFbBCDiSDLkau')
        WalletIntegrityHelper.check_xpub_keystore_sanity(self, ks2)
        self.assertTrue(isinstance(ks2, keystore.BIP32_KeyStore))

        w = WalletIntegrityHelper.create_multisig_wallet([ks1, ks2], '2of2', config=self.config)
        self.assertEqual(w.txin_type, 'p2wsh-p2sh')

        self.assertEqual(w.get_receiving_addresses()[0], 'PCEoRUypBDfTKUpM7Gs2ayq1rprki9RhuR')
        self.assertEqual(w.get_change_addresses()[0], 'PGKs7eX777tVfd4ECnNhx5LaoESkqwiLM4')

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_bip32_extended_version_bytes(self, mock_save_db):
        seed_words = 'crouch dumb relax small truck age shine pink invite spatial object tenant'
        self.assertEqual(keystore.bip39_is_checksum_valid(seed_words), (True, True))
        bip32_seed = keystore.bip39_to_seed(seed_words, '')
        self.assertEqual('0df68c16e522eea9c1d8e090cfb2139c3b3a2abed78cbcb3e20be2c29185d3b8df4e8ce4e52a1206a688aeb88bfee249585b41a7444673d1f16c0d45755fa8b9',
                         bh2u(bip32_seed))

        def create_keystore_from_bip32seed(xtype):
            ks = keystore.BIP32_KeyStore({})
            ks.add_xprv_from_seed(bip32_seed, xtype=xtype, derivation='m/')
            return ks

        ks = create_keystore_from_bip32seed(xtype='standard')
        self.assertEqual('033a05ec7ae9a9833b0696eb285a762f17379fa208b3dc28df1c501cf84fe415d0', ks.derive_pubkey(0, 0).hex())
        self.assertEqual('02bf27f41683d84183e4e930e66d64fc8af5508b4b5bf3c473c505e4dbddaeed80', ks.derive_pubkey(1, 0).hex())

        ks = create_keystore_from_bip32seed(xtype='standard')  # p2pkh
        w = WalletIntegrityHelper.create_standard_wallet(ks, config=self.config)
        self.assertEqual(ks.xprv, 'xprv9s21ZrQH143K3nyWMZVjzGL4KKAE1zahmhTHuV5pdw4eK3o3igC5QywgQG7UTRe6TGBniPDpPFWzXMeMUFbBj8uYsfXGjyMmF54wdNt8QBm')
        self.assertEqual(ks.xpub, 'xpub661MyMwAqRbcGH3yTb2kMQGnsLziRTJZ8vNthsVSCGbdBr8CGDWKxnGAFYgyKTzBtwvPPmfVAWJuFmxRXjSbUTg87wDkWQ5GmzpfUcN9t8Z')
        self.assertEqual(w.get_receiving_addresses()[0], 'MGZfTvUwLhU49T5dmMW34BaKCnrDYp77Xw')
        self.assertEqual(w.get_change_addresses()[0], 'MM8gM4USWrxSSecera12LMYMTrxr7cpHKd')

        ks = create_keystore_from_bip32seed(xtype='p2wpkh-p2sh')
        w = WalletIntegrityHelper.create_standard_wallet(ks, config=self.config)
        self.assertEqual(ks.xprv, 'yprvABrGsX5C9janu6AdBvHNCMRZVHJfxcaCgoyWgsyi1wSXN9cGyLMe33bpRU54TLJ1ruJbTrpNqusYQeFvBx1CXNb9k1DhKtBFWo8b1sLbXhN')
        self.assertEqual(ks.xpub, 'ypub6QqdH2c5z7967aF6HwpNZVNJ3K9AN5J442u7VGPKaGyWEwwRWsftaqvJGkeZKNe7Jb3C9FG3dAfT94ZzFRrcGhMizGvB6Jtm3itJsEFhxMC')
        self.assertEqual(w.get_receiving_addresses()[0], 'PBLKgWafk6eP5Nfmn7VBABZtPmunEh27xY')
        self.assertEqual(w.get_change_addresses()[0], 'PFowhmTz9uc5KztZB5yoA2JUTz1XwAJWPC')

        ks = create_keystore_from_bip32seed(xtype='p2wpkh')
        w = WalletIntegrityHelper.create_standard_wallet(ks, config=self.config)
        self.assertEqual(ks.xprv, 'zprvAWgYBBk7JR8GkPMk2H4zQSX4fFT7uEZhbvVjUGsbPwpQRFRWDzXCf7FxSg2eTEwwGYRQDLQwJaE6HvsUueRDKcGkcLv7unzjnXCEQVWhrF9')
        self.assertEqual(ks.xpub, 'zpub6jftahH18ngZxsSD8JbzmaToDHHcJhHYy9RLGfHCxHMPJ3kemXqTCuaSHxc9KHJ2iE9ztirc5q212MBYy8Gd4w3KrccbgDiFKSwxFpYKEH6')
        self.assertEqual(w.get_receiving_addresses()[0], 'mona1qtuynwzd0d6wptvyqmc6ehkm70zcamxpsnh57ec')
        self.assertEqual(w.get_change_addresses()[0], 'mona1qjy5zunxh6hjysele86qqywfa437z4xwmm2k9rh')

        ks = create_keystore_from_bip32seed(xtype='standard')  # p2sh
        w = WalletIntegrityHelper.create_multisig_wallet([ks], '1of1', config=self.config)
        self.assertEqual(ks.xprv, 'xprv9s21ZrQH143K3nyWMZVjzGL4KKAE1zahmhTHuV5pdw4eK3o3igC5QywgQG7UTRe6TGBniPDpPFWzXMeMUFbBj8uYsfXGjyMmF54wdNt8QBm')
        self.assertEqual(ks.xpub, 'xpub661MyMwAqRbcGH3yTb2kMQGnsLziRTJZ8vNthsVSCGbdBr8CGDWKxnGAFYgyKTzBtwvPPmfVAWJuFmxRXjSbUTg87wDkWQ5GmzpfUcN9t8Z')
        self.assertEqual(w.get_receiving_addresses()[0], 'PMxwzZQKHcHarAuAvT2xHPzt9rusMPmrwM')
        self.assertEqual(w.get_change_addresses()[0], 'PV2u9kBBU1f683kRQ3ePsqVNqNUvyMKFkT')

        ks = create_keystore_from_bip32seed(xtype='p2wsh-p2sh')
        w = WalletIntegrityHelper.create_multisig_wallet([ks], '1of1', config=self.config)
        self.assertEqual(ks.xprv, 'YprvANkMzkodih9AKfL18akM2RmND5LwAyFo15dBc9FFPiGvzLBBjjjv8ATkEB2Y1mWv6NNaLSpVj8G3XosgVBA9frhpaUL6jHeFQXQTbqVPcv2')
        self.assertEqual(ks.xpub, 'Ypub6bjiQGLXZ4hTY9QUEcHMPZi6m7BRaRyeNJYnQXerx3ous8WLHH4AfxnE5Tc2sos1Y47B1qGAWP3xGEBkYf1ZRBUPpk2aViMkwTABT6qoiBb')
        self.assertEqual(w.get_receiving_addresses()[0], 'PSuMBmEZwHV2vtPM5tWWm2f336aRk5obbq')
        self.assertEqual(w.get_change_addresses()[0], 'PV7Rr2Tu2UzPJBQ2wt9L4oUiMHZBo7mS28')

        ks = create_keystore_from_bip32seed(xtype='p2wsh')
        w = WalletIntegrityHelper.create_multisig_wallet([ks], '1of1', config=self.config)
        self.assertEqual(ks.xprv, 'ZprvAhadJRUYsNgeAxX7xwXyEWrsP3VP7bFHvC9QPY98miep3RzQzPuUkE7tFNz81gAqW1VP5vR4BncbR6VFCsaAU6PRSp2XKCTjgFU6zRpk6Xp')
        self.assertEqual(ks.xpub, 'Zpub6vZyhw1ShkEwPSbb4y4ybeobw5KsX3y9HR51BvYkL4BnvEKZXwDjJ2SN6fZcsiWvwhDymJriy3QW9WoKGMRaDR9zh5j15dBFDBDpqjK1ekQ')
        self.assertEqual(w.get_receiving_addresses()[0], 'mona1q84x0yrztvcjg88qef4d6978zccxulcmc9y88xcg4ghjdau999x7qhy4ly3')
        self.assertEqual(w.get_change_addresses()[0], 'mona1q0fj5mra96hhnum80kllklc52zqn6kppt3hyzr49yhr3ecr42z3ts2s3yvc')


class TestWalletKeystoreAddressIntegrityForTestnet(TestCaseForTestnet):

    def setUp(self):
        super().setUp()
        self.config = SimpleConfig({'electrum_path': self.electrum_path})

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_bip39_multisig_seed_p2sh_segwit_testnet(self, mock_save_db):
        # bip39 seed: finish seminar arrange erosion sunny coil insane together pretty lunch lunch rose
        # der: m/49'/1'/0'
        # NOTE: there is currently no bip43 standard derivation path for p2wsh-p2sh
        ks1 = keystore.from_xprv('Uprv9BEixD3As2LK5h6G2SNT3cTqbZpsWYPceKTSuVAm1yuSybxSvQz2MV1o8cHTtctQmj4HAenb3eh5YJv4YRZjv35i8fofVnNbs4Dd2B4i5je')
        self.assertTrue(isinstance(ks1, keystore.BIP32_KeyStore))
        self.assertEqual(ks1.xpub, 'Upub5QE5Mia4hPtcJBAj8TuTQkQa9bfMv17U1YP3hsaNaKSRrQHbTxJGuHLGyv3MbKZixuPyjfXGUdbTjE4KwyFcX8YD7PX5ybTDbP11UT8UpZR')

        # bip39 seed: square page wood spy oil story rebel give milk screen slide shuffle
        # der: m/49'/1'/0'
        ks2 = keystore.from_xpub('Upub5QRzUGRJuWJe5MxGzwgQAeyJjzcdGTXkkq77w6EfBkCyf5iWppSaZ4caY2MgWcU9LP4a4uE5apUFN4wLoENoe9tpu26mrUxeGsH84dN3JFh')
        WalletIntegrityHelper.check_xpub_keystore_sanity(self, ks2)
        self.assertTrue(isinstance(ks2, keystore.BIP32_KeyStore))

        w = WalletIntegrityHelper.create_multisig_wallet([ks1, ks2], '2of2', config=self.config)
        self.assertEqual(w.txin_type, 'p2wsh-p2sh')

        self.assertEqual(w.get_receiving_addresses()[0], 'pDB1g5uWiWnDBQ5cpUaBTtiaNVbFL8cMWw')
        self.assertEqual(w.get_change_addresses()[0], 'pU7W9ZLqTHmvxQ27UgLMsPubECL5LXjGqi')

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_bip32_extended_version_bytes(self, mock_save_db):
        seed_words = 'crouch dumb relax small truck age shine pink invite spatial object tenant'
        self.assertEqual(keystore.bip39_is_checksum_valid(seed_words), (True, True))
        bip32_seed = keystore.bip39_to_seed(seed_words, '')
        self.assertEqual('0df68c16e522eea9c1d8e090cfb2139c3b3a2abed78cbcb3e20be2c29185d3b8df4e8ce4e52a1206a688aeb88bfee249585b41a7444673d1f16c0d45755fa8b9',
                         bh2u(bip32_seed))

        def create_keystore_from_bip32seed(xtype):
            ks = keystore.BIP32_KeyStore({})
            ks.add_xprv_from_seed(bip32_seed, xtype=xtype, derivation='m/')
            return ks

        ks = create_keystore_from_bip32seed(xtype='standard')
        self.assertEqual('033a05ec7ae9a9833b0696eb285a762f17379fa208b3dc28df1c501cf84fe415d0', ks.derive_pubkey(0, 0).hex())
        self.assertEqual('02bf27f41683d84183e4e930e66d64fc8af5508b4b5bf3c473c505e4dbddaeed80', ks.derive_pubkey(1, 0).hex())

        ks = create_keystore_from_bip32seed(xtype='standard')  # p2pkh
        w = WalletIntegrityHelper.create_standard_wallet(ks, config=self.config)
        self.assertEqual(ks.xprv, 'tprv8ZgxMBicQKsPecD328MF9ux3dSaSFWci7FNQmuWH7uZ86eY8i3XpvjK8KSH8To2QphiZiUqaYc6nzDC6bTw8YCB9QJjaQL5pAApN4z7vh2B')
        self.assertEqual(ks.xpub, 'tpubD6NzVbkrYhZ4Y5Epun1qZKcACU6NQqocgYyC4RYaYBMWw8nuLSMR7DvzVamkqxwRgrTJ1MBMhc8wwxT2vbHqMu8RBXy4BvjWMxR5EdZroxE')
        self.assertEqual(w.get_receiving_addresses()[0], 'mpBTXYfWehjW2tavFwpUdqBJbZZkup13k2')
        self.assertEqual(w.get_change_addresses()[0], 'mtkUQgf1psDtL67wMAKTv19LrdgPWy6GDQ')

        ks = create_keystore_from_bip32seed(xtype='p2wpkh-p2sh')
        w = WalletIntegrityHelper.create_standard_wallet(ks, config=self.config)
        self.assertEqual(ks.xprv, 'uprv8tXDerPXZ1QsVuQ9rV8sN13YoQitC8cD2MtdZJQAVuw19kMMxhhPYnyGLeEiThgLELqNTxS91GTLsVofKAM9LRrkGeRzzEuJRtt1Tcostr7')
        self.assertEqual(ks.xpub, 'upub57Wa4MvRPNyAiPUcxWfsj8zHMSZNbbL4PapEMgon4FTz2YgWWF1e6bHkBvpDKk2Rg2Zy9LsonXFFbv7jNeCZ5kdKWv8UkfcoxpdjJrZuBX6')
        self.assertEqual(w.get_receiving_addresses()[0], 'p8HijF4XmHNhnFK9J88wDxSfR3tGMTyPbV')
        self.assertEqual(w.get_change_addresses()[0], 'pCmLkVwrB6LQ2sXvh6dZDoBFVFz26Z2k6D')

        ks = create_keystore_from_bip32seed(xtype='p2wpkh')
        w = WalletIntegrityHelper.create_standard_wallet(ks, config=self.config)
        self.assertEqual(ks.xprv, 'vprv9DMUxX4ShgxMMCbGgqvVa693yNsL8kbhwUQrLhJ3svJtCrAbDMrxArdQMrCJTcLFdyxBDS2hTvotknRE2rmA8fYM8z8Ra9inhcwerEsG6Ev')
        self.assertEqual(ks.xpub, 'vpub5SLqN2bLY4WeZgfjnsTVwE5nXQhpYDKZJhLT95hfSFqs5eVjkuBCiewtD8moKegM5fgmtpUNFBboVCjJ6LcZszJvPFpuLaSJEYhNhUAnrCS')
        self.assertEqual(w.get_receiving_addresses()[0], 'tmona1qtuynwzd0d6wptvyqmc6ehkm70zcamxpstvxpnz')
        self.assertEqual(w.get_change_addresses()[0], 'tmona1qjy5zunxh6hjysele86qqywfa437z4xwmr3y6fd')

        ks = create_keystore_from_bip32seed(xtype='standard')  # p2sh
        w = WalletIntegrityHelper.create_multisig_wallet([ks], '1of1', config=self.config)
        self.assertEqual(ks.xprv, 'tprv8ZgxMBicQKsPecD328MF9ux3dSaSFWci7FNQmuWH7uZ86eY8i3XpvjK8KSH8To2QphiZiUqaYc6nzDC6bTw8YCB9QJjaQL5pAApN4z7vh2B')
        self.assertEqual(ks.xpub, 'tpubD6NzVbkrYhZ4Y5Epun1qZKcACU6NQqocgYyC4RYaYBMWw8nuLSMR7DvzVamkqxwRgrTJ1MBMhc8wwxT2vbHqMu8RBXy4BvjWMxR5EdZroxE')
        self.assertEqual(w.get_receiving_addresses()[0], 'pJvM3HtBJo1uZ3YYSTgiMAsfB8tMSUYFJC')
        self.assertEqual(w.get_change_addresses()[0], 'pRzJCUf3VCPQpvPnv4J9wcN9reTR2iM3yD')

        ks = create_keystore_from_bip32seed(xtype='p2wsh-p2sh')
        w = WalletIntegrityHelper.create_multisig_wallet([ks], '1of1', config=self.config)
        self.assertEqual(ks.xprv, 'Uprv95RJn67y7xyEvUZXo9brC5PMXCm9QVHoLdYJUZfhsgmQmvvGj75fduqC9MCC28uETouMLYSFtUqqzfRRcPW6UuyR77YQPeNJKd9t3XutF8b')
        self.assertEqual(ks.xpub, 'Upub5JQfBberxLXY8xdzuB8rZDL65Ebdox1ehrTuGx5KS2JPejFRGePvBi9fzdmgtBFKuVdx1vsvfjdkj5jVfsMWEEjzMPEtA55orYubtrCZmRr')
        self.assertEqual(w.get_receiving_addresses()[0], 'pPrkEViRxUDMdm2ibuAGpoXp4NYutJcAsB')
        self.assertEqual(w.get_change_addresses()[0], 'pS4ptkwm3fii143QTto68aMVNZXfqVCjCm')

        ks = create_keystore_from_bip32seed(xtype='p2wsh')
        w = WalletIntegrityHelper.create_multisig_wallet([ks], '1of1', config=self.config)
        self.assertEqual(ks.xprv, 'Vprv16YtLrHXxePM6noKqtFtMtmUgBE9bEpF3fPLmpvuPksssLostujtdHBwqhEeVuzESz22UY8hyPx9ed684SQpCmUKSVhpxPFbvVNY7qnviNR')
        self.assertEqual(ks.xpub, 'Vpub5dEvVGKn7251zFq7jXvUmJRbFCk5ka19cxz84LyCp2gGhq4eXJZUomop1qjGt5uFK8kkmQUV8PzJcNM4PZmX2URbDiwJjyuJ8GyFHRrEmmG')
        self.assertEqual(w.get_receiving_addresses()[0], 'tmona1q84x0yrztvcjg88qef4d6978zccxulcmc9y88xcg4ghjdau999x7qg9pur6')
        self.assertEqual(w.get_change_addresses()[0], 'tmona1q0fj5mra96hhnum80kllklc52zqn6kppt3hyzr49yhr3ecr42z3ts4398tn')


class TestWalletSending(TestCaseForTestnet):
    maxDiff = None
    def setUp(self):
        super().setUp()
        self.config = SimpleConfig({'electrum_path': self.electrum_path})

    def create_standard_wallet_from_seed(self, seed_words, *, config=None, gap_limit=2):
        if config is None:
            config = self.config
        ks = keystore.from_seed(seed_words, '', False)
        return WalletIntegrityHelper.create_standard_wallet(ks, gap_limit=gap_limit, config=config)

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_between_p2wpkh_and_compressed_p2pkh(self, mock_save_db):
        wallet1 = self.create_standard_wallet_from_seed('bitter grass shiver impose acquire brush forget axis eager alone wine silver')
        wallet2 = self.create_standard_wallet_from_seed('cycle rocket west magnet parrot shuffle foot correct salt library feed song')

        # bootstrap wallet1
        funding_tx = Transaction('01000000014576dacce264c24d81887642b726f5d64aa7825b21b350c7b75a57f337da6845010000006b483045022100a3f8b6155c71a98ad9986edd6161b20d24fad99b6463c23b463856c0ee54826d02200f606017fd987696ebbe5200daedde922eee264325a184d5bbda965ba5160821012102e5c473c051dae31043c335266d0ef89c1daab2f34d885cc7706b267f3269c609ffffffff0240420f00000000001600148a28bddb7f61864bdcf58b2ad13d5aeb3abc3c42a2ddb90e000000001976a914c384950342cb6f8df55175b48586838b03130fad88ac00000000')
        funding_txid = funding_tx.txid()
        funding_output_value = 1000000
        self.assertEqual('add2535aedcbb5ba79cc2260868bb9e57f328738ca192937f2c92e0e94c19203', funding_txid)
        wallet1.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # wallet1 -> wallet2
        outputs = [PartialTxOutput.from_address_and_value(wallet2.get_receiving_address(), 250000)]
        tx = wallet1.mktx(outputs=outputs, password=None, fee=5000, tx_version=1)

        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        self.assertEqual(wallet1.txin_type, tx.inputs()[0].script_type)
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet1.is_mine(wallet1.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual('010000000001010392c1940e2ec9f2372919ca3887327fe5b98b866022cc79bab5cbed5a53d2ad0000000000feffffff0290d00300000000001976a914ea7804a2c266063572cc009a63dc25dcc0e9d9b588ac285e0b0000000000160014690b59a8140602fb23cc2904ece9cc4daf361052024730440220608a5339ca894592da82119e1e4a1d09335d70a552c683687223b8ed724465e902201b3f0feccf391b1b6257e4b18970ae57d7ca060af2dae519b3690baad2b2a34e0121030faee9b4a25b7db82023ca989192712cdd4cb53d3d9338591c7909e581ae1c0c00000000',
                         str(tx_copy))
        self.assertEqual('3c06ae4d9be8226a472b3e7f7c127c7e3016f525d658d26106b80b4c7e3228e2', tx_copy.txid())
        self.assertEqual('d8d930ae91dce73118c3fffabbdfcfb87f5d91673fb4c7dfd0fbe7cf03bf426b', tx_copy.wtxid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())

        wallet1.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)  # TX_HEIGHT_UNCONF_PARENT but nvm
        wallet2.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)

        # wallet2 -> wallet1
        outputs = [PartialTxOutput.from_address_and_value(wallet1.get_receiving_address(), 100000)]
        tx = wallet2.mktx(outputs=outputs, password=None, fee=5000, tx_version=1)

        self.assertTrue(tx.is_complete())
        self.assertFalse(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        self.assertEqual(wallet2.txin_type, tx.inputs()[0].script_type)
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet2.is_mine(wallet2.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual('0100000001e228327e4c0bb80661d258d625f516307e7c127c7f3e2b476a22e89b4dae063c000000006a47304402200c7b06ff882db5ffe9d6e2a3cc2cabf5cd1b4224f1453d1e3dadd13b3d391e2c02201d23fde8482b05837f27d43021d17a1be2ee619dfc889ee80d4c2761e7c7ffb20121030b482838721a38d94847699fed8818b5c5f56500ef72f13489e365b65e5749cffeffffff02a086010000000000160014284520c815980d426264766d8d930013dd20aa6068360200000000001976a914ca4c60999c46c2108326590b125aefd476dcb11888ac00000000',
                         str(tx_copy))
        self.assertEqual('4ff22c31dd884dedbb905fae275508d1f7bb4948c1c979d2567132848fdff24a', tx_copy.txid())
        self.assertEqual('4ff22c31dd884dedbb905fae275508d1f7bb4948c1c979d2567132848fdff24a', tx_copy.wtxid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())

        wallet1.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        wallet2.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)

        # wallet level checks
        self.assertEqual((0, funding_output_value - 250000 - 5000 + 100000, 0), wallet1.get_balance())
        self.assertEqual((0, 250000 - 5000 - 100000, 0), wallet2.get_balance())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_between_p2sh_2of3_and_uncompressed_p2pkh(self, mock_save_db):
        wallet1a = WalletIntegrityHelper.create_multisig_wallet(
            [
                keystore.from_seed('blast uniform dragon fiscal ensure vast young utility dinosaur abandon rookie sure', '', True),
                keystore.from_xpub('tpubD6NzVbkrYhZ4YTPEgwk4zzr8wyo7pXGmbbVUnfYNtx6SgAMF5q3LN3Kch58P9hxGNsTmP7Dn49nnrmpE6upoRb1Xojg12FGLuLHkVpVtS44'),
                keystore.from_xpub('tpubD6NzVbkrYhZ4XJzYkhsCbDCcZRmDAKSD7bXi9mdCni7acVt45fxbTVZyU6jRGh29ULKTjoapkfFsSJvQHitcVKbQgzgkkYsAmaovcro7Mhf')
            ],
            '2of3', gap_limit=2,
            config=self.config
        )
        wallet1b = WalletIntegrityHelper.create_multisig_wallet(
            [
                keystore.from_seed('cycle rocket west magnet parrot shuffle foot correct salt library feed song', '', True),
                keystore.from_xpub('tpubD6NzVbkrYhZ4YTPEgwk4zzr8wyo7pXGmbbVUnfYNtx6SgAMF5q3LN3Kch58P9hxGNsTmP7Dn49nnrmpE6upoRb1Xojg12FGLuLHkVpVtS44'),
                keystore.from_xpub('tpubD6NzVbkrYhZ4YARFMEZPckrqJkw59GZD1PXtQnw14ukvWDofR7Z1HMeSCxfYEZVvg4VdZ8zGok5VxHwdrLqew5cMdQntWc5mT7mh1CSgrnX')
            ],
            '2of3', gap_limit=2,
            config=self.config
        )
        # ^ third seed: ghost into match ivory badge robot record tackle radar elbow traffic loud
        wallet2 = self.create_standard_wallet_from_seed('powerful random nobody notice nothing important anyway look away hidden message over')

        # bootstrap wallet1
        funding_tx = Transaction('010000000001014121f99dc02f0364d2dab3d08905ff4c36fc76c55437fd90b769c35cc18618280100000000fdffffff02d4c22d00000000001600143fd1bc5d32245850c8cb5be5b09c73ccbb9a0f75001bb7000000000017a91480c2353f6a7bc3c71e99e062655b19adb3dd2e4887024830450221008781c78df0c9d4b5ea057333195d5d76bc29494d773f14fa80e27d2f288b2c360220762531614799b6f0fb8d539b18cb5232ab4253dd4385435157b28a44ff63810d0121033de77d21926e09efd04047ae2d39dbd3fb9db446e8b7ed53e0f70f9c9478f735dac11300')
        funding_txid = funding_tx.txid()
        funding_output_value = 12000000
        self.assertEqual('b25cd55687c9e528c2cfd546054f35fb6741f7cf32d600f07dfecdf2e1d42071', funding_txid)
        wallet1a.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # wallet1 -> wallet2
        outputs = [PartialTxOutput.from_address_and_value(wallet2.get_receiving_address(), 370000)]
        tx = wallet1a.mktx(outputs=outputs, password=None, fee=5000, tx_version=1)
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff01007501000000017120d4e1f2cdfe7df000d632cff74167fb354f0546d5cfc228e5c98756d55cb20100000000feffffff0250a50500000000001976a9149cd3dfb0d87a861770ae4e268e74b45335cf00ab88ac2862b1000000000017a9142e517854aa54668128c0e9a3fdd4dec13ad571368700000000000100e0010000000001014121f99dc02f0364d2dab3d08905ff4c36fc76c55437fd90b769c35cc18618280100000000fdffffff02d4c22d00000000001600143fd1bc5d32245850c8cb5be5b09c73ccbb9a0f75001bb7000000000017a91480c2353f6a7bc3c71e99e062655b19adb3dd2e4887024830450221008781c78df0c9d4b5ea057333195d5d76bc29494d773f14fa80e27d2f288b2c360220762531614799b6f0fb8d539b18cb5232ab4253dd4385435157b28a44ff63810d0121033de77d21926e09efd04047ae2d39dbd3fb9db446e8b7ed53e0f70f9c9478f735dac11300220202afb4af9a91264e1c6dce3ebe5312801723270ac0ba8134b7b49129328fcb0f284730440220751ee3599e59debb8b2aeef61bb5f574f26379cd961caf382d711a507bc632390220598d53e62557c4a5ab8cfb2f8948f37cca06a861714b55c781baf2c3d7a580b501010469522102afb4af9a91264e1c6dce3ebe5312801723270ac0ba8134b7b49129328fcb0f2821030b482838721a38d94847699fed8818b5c5f56500ef72f13489e365b65e5749cf2103e5db7969ae2f2576e6a061bf3bb2db16571e77ffb41e0b27170734359235cbce53ae220602afb4af9a91264e1c6dce3ebe5312801723270ac0ba8134b7b49129328fcb0f280c0036e9ac00000000000000002206030b482838721a38d94847699fed8818b5c5f56500ef72f13489e365b65e5749cf0c48adc7a00000000000000000220603e5db7969ae2f2576e6a061bf3bb2db16571e77ffb41e0b27170734359235cbce0cdb692427000000000000000000000100695221022ec6f62b0f3b7c2446f44346bff0a6f06b5fdbc27368be8a36478e0287fe47be21024238f21f90527dc87e945f389f3d1711943b06f0a738d5baab573fc0ab6c98582102b7139e93747d7c77f62af5a38b8a2b009f3456aa94dea9bf21f73a6298c867a253ae2202022ec6f62b0f3b7c2446f44346bff0a6f06b5fdbc27368be8a36478e0287fe47be0cdb69242701000000000000002202024238f21f90527dc87e945f389f3d1711943b06f0a738d5baab573fc0ab6c98580c0036e9ac0100000000000000220202b7139e93747d7c77f62af5a38b8a2b009f3456aa94dea9bf21f73a6298c867a20c48adc7a0010000000000000000",
                         partial_tx)
        tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertFalse(tx.is_complete())
        wallet1b.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertFalse(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        self.assertEqual(wallet1a.txin_type, tx.inputs()[0].script_type)
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet1a.is_mine(wallet1a.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual('01000000017120d4e1f2cdfe7df000d632cff74167fb354f0546d5cfc228e5c98756d55cb201000000fc004730440220751ee3599e59debb8b2aeef61bb5f574f26379cd961caf382d711a507bc632390220598d53e62557c4a5ab8cfb2f8948f37cca06a861714b55c781baf2c3d7a580b501473044022023b55c679397bdf3a04d545adc6193eabc11b3a28850d3d46049a51a30c6732402205dbfdade5620e9072ae4aa7577c5f0fd294f59a6b0064cc7105093c0fe7a6d24014c69522102afb4af9a91264e1c6dce3ebe5312801723270ac0ba8134b7b49129328fcb0f2821030b482838721a38d94847699fed8818b5c5f56500ef72f13489e365b65e5749cf2103e5db7969ae2f2576e6a061bf3bb2db16571e77ffb41e0b27170734359235cbce53aefeffffff0250a50500000000001976a9149cd3dfb0d87a861770ae4e268e74b45335cf00ab88ac2862b1000000000017a9142e517854aa54668128c0e9a3fdd4dec13ad571368700000000',
                         str(tx_copy))
        self.assertEqual('b508ee1908181e55d2a18a5b2a3904dffbc7cb6b6320bbfba4433578d0f7831e', tx_copy.txid())
        self.assertEqual('b508ee1908181e55d2a18a5b2a3904dffbc7cb6b6320bbfba4433578d0f7831e', tx_copy.wtxid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())

        wallet1a.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        wallet2.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)

        # wallet2 -> wallet1
        outputs = [PartialTxOutput.from_address_and_value(wallet1a.get_receiving_address(), 100000)]
        tx = wallet2.mktx(outputs=outputs, password=None, fee=5000, tx_version=1)

        self.assertTrue(tx.is_complete())
        self.assertFalse(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        self.assertEqual(wallet2.txin_type, tx.inputs()[0].script_type)
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet2.is_mine(wallet2.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual('01000000011e83f7d0783543a4fbbb20636bcbc7fbdf04392a5b8aa1d2551e180819ee08b5000000008a473044022007569f938b5d7a7f529ceccc413363d84325c11d589c1897660bebfd5fd1cc4302203ef71fa42f9b31bb1e816af13b0bf725c493a0405433390c783cd9374713c5880141045f7ba332df2a7b4f5d13f246e307c9174cfa9b8b05f3b83410a3c23ef8958d610be285963d67c7bc1feb082f168fa9877c25999963ff8b56b242a852b23e25edfeffffff02a08601000000000017a914efe136b8275f49bc0f9871eebb9a48d0516229fd87280b0400000000001976a914ca14915184a2662b5d1505ce7142c8ca066c70e288ac00000000',
                         str(tx_copy))
        self.assertEqual('30f6eec4db5e6b1dfe572dfbc7077661df9a15a2a1b7701612b906d3e1bee3d8', tx_copy.txid())
        self.assertEqual('30f6eec4db5e6b1dfe572dfbc7077661df9a15a2a1b7701612b906d3e1bee3d8', tx_copy.wtxid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())

        wallet1a.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        wallet2.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)

        # wallet level checks
        self.assertEqual((0, funding_output_value - 370000 - 5000 + 100000, 0), wallet1a.get_balance())
        self.assertEqual((0, 370000 - 5000 - 100000, 0), wallet2.get_balance())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_between_p2wsh_2of3_and_p2wsh_p2sh_2of2(self, mock_save_db):
        wallet1a = WalletIntegrityHelper.create_multisig_wallet(
            [
                keystore.from_seed('bitter grass shiver impose acquire brush forget axis eager alone wine silver', '', True),
                keystore.from_xpub('Vpub5fcdcgEwTJmbmqAktuK8Kyq92fMf7sWkcP6oqAii2tG47dNbfkGEGUbfS9NuZaRywLkHE6EmUksrqo32ZL3ouLN1HTar6oRiHpDzKMAF1tf'),
                keystore.from_xpub('Vpub5fjkKyYnvSS4wBuakWTkNvZDaBM2vQ1MeXWq368VJHNr2eT8efqhpmZ6UUkb7s2dwCXv2Vuggjdhk4vZVyiAQTwUftvff73XcUGq2NQmWra')
            ],
            '2of3', gap_limit=2,
            config=self.config
        )
        wallet1b = WalletIntegrityHelper.create_multisig_wallet(
            [
                keystore.from_seed('snow nest raise royal more walk demise rotate smooth spirit canyon gun', '', True),
                keystore.from_xpub('Vpub5fjkKyYnvSS4wBuakWTkNvZDaBM2vQ1MeXWq368VJHNr2eT8efqhpmZ6UUkb7s2dwCXv2Vuggjdhk4vZVyiAQTwUftvff73XcUGq2NQmWra'),
                keystore.from_xpub('Vpub5gSKXzxK7FeKQedu2q1z9oJWxqvX72AArW3HSWpEhc8othDH8xMDu28gr7gf17sp492BuJod8Tn7anjvJrKpETwqnQqX7CS8fcYyUtedEMk')
            ],
            '2of3', gap_limit=2,
            config=self.config
        )
        # ^ third seed: hedgehog sunset update estate number jungle amount piano friend donate upper wool
        wallet2a = WalletIntegrityHelper.create_multisig_wallet(
            [
                # bip39: finish seminar arrange erosion sunny coil insane together pretty lunch lunch rose, der: m/1234'/1'/0', p2wsh-p2sh multisig
                keystore.from_xprv('Uprv9CvELvByqm8k2dpecJVjgLMX1z5DufEjY4fBC5YvdGF5WjGCa7GVJJ2fYni1tyuF7Hw83E6W2ZBjAhaFLZv2ri3rEsubkCd5avg4EHKoDBN'),
                keystore.from_xpub('Upub5Qb8ik4Cnu8g97KLXKgVXHqY6tH8emQvqtBncjSKsyfTZuorPtTZgX7ovKKZHuuVGBVd1MTTBkWez1XXt2weN1sWBz6SfgRPQYEkNgz81QF')
            ],
            '2of2', gap_limit=2,
            config=self.config
        )
        wallet2b = WalletIntegrityHelper.create_multisig_wallet(
            [
                # bip39: square page wood spy oil story rebel give milk screen slide shuffle, der: m/1234'/1'/0', p2wsh-p2sh multisig
                keystore.from_xprv('Uprv9BbnKEXJxXaNvdEsRJ9VA9toYrSeFJh5UfGBpM2iKe8Uh7UhrM9K8ioL53s8gvCoGfirHHaqpABDAE7VUNw8LNU1DMJKVoWyeNKu9XcDC19'),
                keystore.from_xpub('Upub5RuakRisg8h3F7u7iL2k3UJFa1uiK7xauHamzTxYBbn4PXbM7eajr6M9Q2VCr6cVGhfhqWQqxnABvtSATuVM1xzxk4nA189jJwzaMn1QX7V')
            ],
            '2of2', gap_limit=2,
            config=self.config
        )

        # bootstrap wallet1
        funding_tx = Transaction('01000000000101a41aae475d026c9255200082c7fad26dc47771275b0afba238dccda98a597bd20000000000fdffffff02400d0300000000002200203c43ac80d6e3015cf378bf6bac0c22456723d6050bef324ec641e7762440c63c9dcd410000000000160014824626055515f3ed1d2cfc9152d2e70685c71e8f02483045022100b9f39fad57d07ce1e18251424034f21f10f20e59931041b5167ae343ce973cf602200fefb727fa0ffd25b353f1bcdae2395898fe407b692c62f5885afbf52fa06f5701210301a28f68511ace43114b674371257bb599fd2c686c4b19544870b1799c954b40e9c11300')
        funding_txid = funding_tx.txid()
        funding_output_value = 200000
        self.assertEqual('d2bd6c9d332db8e2c50aa521cd50f963fba214645aab2f7556e061a412103e21', funding_txid)
        wallet1a.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # wallet1 -> wallet2
        outputs = [PartialTxOutput.from_address_and_value(wallet2a.get_receiving_address(), 165000)]
        tx = wallet1a.mktx(outputs=outputs, password=None, fee=5000, tx_version=1)
        txid = tx.txid()
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff0100530100000001213e1012a461e056752fab5a6414a2fb63f950cd21a50ac5e2b82d339d6cbdd20000000000feffffff01888402000000000017a914187842cea9c15989a51ce7ca889a08b824bf87438700000000000100eb01000000000101a41aae475d026c9255200082c7fad26dc47771275b0afba238dccda98a597bd20000000000fdffffff02400d0300000000002200203c43ac80d6e3015cf378bf6bac0c22456723d6050bef324ec641e7762440c63c9dcd410000000000160014824626055515f3ed1d2cfc9152d2e70685c71e8f02483045022100b9f39fad57d07ce1e18251424034f21f10f20e59931041b5167ae343ce973cf602200fefb727fa0ffd25b353f1bcdae2395898fe407b692c62f5885afbf52fa06f5701210301a28f68511ace43114b674371257bb599fd2c686c4b19544870b1799c954b40e9c1130022020223f815ab09f6bfc8519165c5232947ae89d9d43d678fb3486f3b28382a2371fa47304402204ae66130e7debd700d9530bb70d84a7945f45a2ddd34b502d2e457a28a08a1d902200aad10ae659652eb9db926aa5424e8d485ef66b8181491ec7f28f07a04e2fa790101056952210223f815ab09f6bfc8519165c5232947ae89d9d43d678fb3486f3b28382a2371fa210273c529c2c9a99592f2066cebc2172a48991af2b471cb726b9df78c6497ce984e2102aa8fc578b445a1e4257be6b978fcece92980def98dce0e1eb89e7364635ae94153ae22060223f815ab09f6bfc8519165c5232947ae89d9d43d678fb3486f3b28382a2371fa10b2e35a7d01000080000000000000000022060273c529c2c9a99592f2066cebc2172a48991af2b471cb726b9df78c6497ce984e1053b77ddb010000800000000000000000220602aa8fc578b445a1e4257be6b978fcece92980def98dce0e1eb89e7364635ae9411043067d630100008000000000000000000000",
                         partial_tx)
        tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertEqual(txid, tx.txid())
        self.assertFalse(tx.is_complete())
        wallet1b.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        self.assertEqual(wallet1a.txin_type, tx.inputs()[0].script_type)
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet1a.is_mine(wallet1a.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual('01000000000101213e1012a461e056752fab5a6414a2fb63f950cd21a50ac5e2b82d339d6cbdd20000000000feffffff01888402000000000017a914187842cea9c15989a51ce7ca889a08b824bf874387040047304402204ae66130e7debd700d9530bb70d84a7945f45a2ddd34b502d2e457a28a08a1d902200aad10ae659652eb9db926aa5424e8d485ef66b8181491ec7f28f07a04e2fa7901473044022014b5e75ebfeeee7bdd07caf39854f3cf050021bd4b5e6e130a2f08b0dc42367502200d370121a04964803570cfccba070d1c4397ed4a1b4e9df60913b822dde5470b016952210223f815ab09f6bfc8519165c5232947ae89d9d43d678fb3486f3b28382a2371fa210273c529c2c9a99592f2066cebc2172a48991af2b471cb726b9df78c6497ce984e2102aa8fc578b445a1e4257be6b978fcece92980def98dce0e1eb89e7364635ae94153ae00000000',
                         str(tx_copy))
        self.assertEqual('13925a2d2e743b24c8e2e69d2d386fb048c289227514b9264d160e1ca93ee9ec', tx_copy.txid())
        self.assertEqual('f19a281486eea910d6d43b44f7f3a3e1f1ffacb1c965a061a7ba38f2c2aa7cad', tx_copy.wtxid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())
        self.assertEqual(txid, tx_copy.txid())

        wallet1a.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        wallet2a.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)

        # wallet2 -> wallet1
        outputs = [PartialTxOutput.from_address_and_value(wallet1a.get_receiving_address(), 100000)]
        tx = wallet2a.mktx(outputs=outputs, password=None, fee=5000, tx_version=1)
        txid = tx.txid()
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff01007e0100000001ece93ea91c0e164d26b914752289c248b06f382d9de6e2c8243b742e2d5a92130000000000feffffff0260ea00000000000017a9143025051b6b5ccd4baf30dfe2de8aa84f0dd567ed87a086010000000000220020f7b6b30c3073ae2680a7e90c589bbfec5303331be68bbab843eed5d51ba0123900000000000100fd510101000000000101213e1012a461e056752fab5a6414a2fb63f950cd21a50ac5e2b82d339d6cbdd20000000000feffffff01888402000000000017a914187842cea9c15989a51ce7ca889a08b824bf874387040047304402204ae66130e7debd700d9530bb70d84a7945f45a2ddd34b502d2e457a28a08a1d902200aad10ae659652eb9db926aa5424e8d485ef66b8181491ec7f28f07a04e2fa7901473044022014b5e75ebfeeee7bdd07caf39854f3cf050021bd4b5e6e130a2f08b0dc42367502200d370121a04964803570cfccba070d1c4397ed4a1b4e9df60913b822dde5470b016952210223f815ab09f6bfc8519165c5232947ae89d9d43d678fb3486f3b28382a2371fa210273c529c2c9a99592f2066cebc2172a48991af2b471cb726b9df78c6497ce984e2102aa8fc578b445a1e4257be6b978fcece92980def98dce0e1eb89e7364635ae94153ae00000000220202119f899075a131d4d519d4cdcf5de5907dc2df3b93d54b53ded852211d2b6cb1473044022003b515c7f2ae53f8bb0d5f80192b5692ab0e9c9e1258162a7761ee72a8afbdcd022041924bc3d8d96261d8f69703082916cec574666f9128935b8cf6f4737eba22d90101042200204311edae835c7a5aa712c8ca644180f13a3b2f3b420fa879b181474724d6163c010547522102119f899075a131d4d519d4cdcf5de5907dc2df3b93d54b53ded852211d2b6cb12102fdb0f6775d4b6619257c43343ba5e7807b0164f1eb3f00f2b594ab9e53ab812652ae220602119f899075a131d4d519d4cdcf5de5907dc2df3b93d54b53ded852211d2b6cb10cd1dbcc210000000000000000220602fdb0f6775d4b6619257c43343ba5e7807b0164f1eb3f00f2b594ab9e53ab81260c17cea9140000000000000000000100220020717ab7037b81797cb3e192a8a1b4d88083444bbfcd26934cadf3bcf890f14e05010147522102987c184fcd8ace2e2a314250e04a15a4b8c885fb4eb778ab82c45838bcbcbdde21034084c4a0493c248783e60d8415cd30b3ba2c3b7a79201e38b953adea2bc44f9952ae220202987c184fcd8ace2e2a314250e04a15a4b8c885fb4eb778ab82c45838bcbcbdde0c17cea91401000000000000002202034084c4a0493c248783e60d8415cd30b3ba2c3b7a79201e38b953adea2bc44f990cd1dbcc2101000000000000000000",
                         partial_tx)
        tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertEqual(txid, tx.txid())
        self.assertFalse(tx.is_complete())
        wallet2b.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        self.assertEqual(wallet2a.txin_type, tx.inputs()[0].script_type)
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet2a.is_mine(wallet2a.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual('01000000000101ece93ea91c0e164d26b914752289c248b06f382d9de6e2c8243b742e2d5a921300000000232200204311edae835c7a5aa712c8ca644180f13a3b2f3b420fa879b181474724d6163cfeffffff0260ea00000000000017a9143025051b6b5ccd4baf30dfe2de8aa84f0dd567ed87a086010000000000220020f7b6b30c3073ae2680a7e90c589bbfec5303331be68bbab843eed5d51ba012390400473044022003b515c7f2ae53f8bb0d5f80192b5692ab0e9c9e1258162a7761ee72a8afbdcd022041924bc3d8d96261d8f69703082916cec574666f9128935b8cf6f4737eba22d9014730440220747496ed03a497a7bb6535d4df9b41c52196f33fe28620c4b2b3ab9d464d7736022049fd83b50560910e75f8ea02df48b13ac8055f645a6a2ec8790ae9b42a0da3d90147522102119f899075a131d4d519d4cdcf5de5907dc2df3b93d54b53ded852211d2b6cb12102fdb0f6775d4b6619257c43343ba5e7807b0164f1eb3f00f2b594ab9e53ab812652ae00000000',
                         str(tx_copy))
        self.assertEqual('84ca34186bcc6d7c7f15efac53bbd37e9a7136a290a9b5b0caf031c7eb68d922', tx_copy.txid())
        self.assertEqual('749f7830d9f8b6a25fe87ccc3450a82fb8bfe506bac500a3a65d9d9e43780dca', tx_copy.wtxid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())
        self.assertEqual(txid, tx_copy.txid())

        wallet1a.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        wallet2a.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)

        # wallet level checks
        self.assertEqual((0, funding_output_value - 165000 - 35000 + 100000, 0), wallet1a.get_balance())
        self.assertEqual((0, 165000 - 5000 - 100000, 0), wallet2a.get_balance())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_between_p2sh_1of2_and_p2wpkh_p2sh(self, mock_save_db):
        wallet1a = WalletIntegrityHelper.create_multisig_wallet(
            [
                keystore.from_seed('phone guilt ancient scan defy gasp off rotate approve ill word exchange', '', True),
                keystore.from_xpub('tpubD6NzVbkrYhZ4YPZ3ntVjqSCxiUUv2jikrUBU73Q3iJ7Y8iR41oYf991L5fanv7ciHjbjokdK2bjYqg1BzEUDxucU9qM5WRdBiY738wmgLP4')
            ],
            '1of2', gap_limit=2,
            config=self.config
        )
        # ^ second seed: kingdom now gift initial age right velvet exotic harbor enforce kingdom kick
        wallet2 = WalletIntegrityHelper.create_standard_wallet(
            # bip39: uniform tank success logic lesson awesome stove elegant regular desert drip device, der: m/49'/1'/0'
            keystore.from_xprv('uprv91HGbrNZTK4x8u22nbdYGzEuWPxjaHMREUi7CNhY64KsG5ZGnVM99uCa16EMSfrnaPTFxjbRdBZ2WiBkokoM8anzAy3Vpc52o88WPkitnxi'),
            gap_limit=2,
            config=self.config
        )

        # bootstrap wallet1
        funding_tx = Transaction('010000000001027e20990282eb29588375ad04936e1e991af3bc5b9c6f1ab62eca8c25becaef6a01000000171600140e6a17fadc8bafba830f3467a889f6b211d69a00fdffffff51847fd6bcbdfd1d1ea2c2d95c2d8de1e34c5f2bd9493e88a96a4e229f564e800100000017160014ecdf9fa06856f9643b1a73144bc76c24c67774a6fdffffff021e8501000000000017a91451991bfa68fbcb1e28aa0b1e060b7d24003352e38700093d000000000017a914b0b9f31bace76cdfae2c14abc03e223403d7dc4b870247304402205e19721b92c6afd70cd932acb50815a36ee32ab46a934147d62f02c13aeacf4702207289c4a4131ef86e27058ff70b6cb6bf0e8e81c6cbab6dddd7b0a9bc732960e4012103fe504411c21f7663caa0bbf28931f03fae7e0def7bc54851e0194dfb1e2c85ef02483045022100e969b65096fba4f8b24eb5bc622d2282076241621f3efe922cc2067f7a8a6be702203ec4047dd2a71b9c83eb6a0875a6d66b4d65864637576c06ed029d3d1a8654b0012102bbc8100dca67ba0297aba51296a4184d714204a5fc2eda34708360f37019a3dccfcc1300')
        funding_txid = funding_tx.txid()
        funding_output_value = 4000000
        self.assertEqual('1137c12de4ce0f5b08de8846ba14c0814351a7f0f31457c8ea51a5d4b3c891a3', funding_txid)
        wallet1a.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # wallet1 -> wallet2
        outputs = [PartialTxOutput.from_address_and_value(wallet2.get_receiving_address(), 1000000)]
        tx = wallet1a.mktx(outputs=outputs, password=None, fee=5000, tx_version=1)

        self.assertTrue(tx.is_complete())
        self.assertFalse(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        self.assertEqual(wallet1a.txin_type, tx.inputs()[0].script_type)
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet1a.is_mine(wallet1a.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual('0100000001a391c8b3d4a551eac85714f3f0a7514381c014ba4688de085b0fcee42dc1371101000000910047304402204f1e1821b93b80a2033d3045325fe5c123d7ef54c2050aa356712eb32111ee670220039825c63cfe5879e808bf95aa365967d06a5f4072154955448becb65b8c5926014751210245c90e040d4f9d1fc136b3d4d6b7535bbb5df2bd27666c21977042cc1e05b5b02103c9a6bebfce6294488315e58137a279b2efe09f1f528ecf93b40675ded3cf0e5f52aefeffffff0240420f000000000017a9149573eb50f3136dff141ac304190f41c8becc92ce8738b32d000000000017a914b815d1b430ae9b632e3834ed537f7956325ee2a98700000000',
                         str(tx_copy))
        self.assertEqual('4649d6b6f8f967a84309de15c6d7403e628aa92ecb4f4d6d21299156fddff9e6', tx_copy.txid())
        self.assertEqual('4649d6b6f8f967a84309de15c6d7403e628aa92ecb4f4d6d21299156fddff9e6', tx_copy.wtxid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())

        wallet1a.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        wallet2.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)

        # wallet2 -> wallet1
        outputs = [PartialTxOutput.from_address_and_value(wallet1a.get_receiving_address(), 300000)]
        tx = wallet2.mktx(outputs=outputs, password=None, fee=5000, tx_version=1)

        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        self.assertEqual(wallet2.txin_type, tx.inputs()[0].script_type)
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet2.is_mine(wallet2.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual('01000000000101e6f9dffd569129216d4d4fcb2ea98a623e40d7c615de0943a867f9f8b6d6494600000000171600149fad840ed174584ee054bd26f3e411817338c5edfeffffff02e09304000000000017a9145ae3933a6e13100f301f23227b98b0bdb5d16b8487d89a0a000000000017a9148ccd0efb2be5b412c4033715f560ed8f446c8ceb8702473044022020a3c46886b72f4ec561c5983a789098202307eae9679ff74fcb0879f65fff1d0220242ec3bfa747c513ef31874670d9c68ad235892588be55564696dd6690952e5a0121038362bbf0b4918b37e9d7c75930ed3a78e3d445724cb5c37ade4a59b6e411fe4e00000000',
                         str(tx_copy))
        self.assertEqual('ae5dcacdf9e3067e18fcfd33582c24f60f844730e7872049bb627796929879ee', tx_copy.txid())
        self.assertEqual('f70bce6418fc44dcab41cbd466086aea54283821487189e4d15c4d1e2d1e267d', tx_copy.wtxid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())

        wallet1a.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        wallet2.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)

        # wallet level checks
        self.assertEqual((0, funding_output_value - 1000000 - 5000 + 300000, 0), wallet1a.get_balance())
        self.assertEqual((0, 1000000 - 5000 - 300000, 0), wallet2.get_balance())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_rbf(self, mock_save_db):
        self.maxDiff = None
        config = SimpleConfig({'electrum_path': self.electrum_path})
        config.set_key('coin_chooser_output_rounding', False)
        for simulate_moving_txs in (False, True):
            with self.subTest(msg="_bump_fee_p2pkh_when_there_is_a_change_address", simulate_moving_txs=simulate_moving_txs):
                self._bump_fee_p2pkh_when_there_is_a_change_address(
                    simulate_moving_txs=simulate_moving_txs,
                    config=config)
            with self.subTest(msg="_bump_fee_p2wpkh_when_there_is_a_change_address", simulate_moving_txs=simulate_moving_txs):
                self._bump_fee_p2wpkh_when_there_is_a_change_address(
                    simulate_moving_txs=simulate_moving_txs,
                    config=config)
            with self.subTest(msg="_bump_fee_p2pkh_when_there_are_two_ismine_outs_one_change_one_recv", simulate_moving_txs=simulate_moving_txs):
                self._bump_fee_p2pkh_when_there_are_two_ismine_outs_one_change_one_recv(
                    simulate_moving_txs=simulate_moving_txs,
                    config=config)
            with self.subTest(msg="_bump_fee_when_user_sends_max", simulate_moving_txs=simulate_moving_txs):
                self._bump_fee_when_user_sends_max(
                    simulate_moving_txs=simulate_moving_txs,
                    config=config)
            with self.subTest(msg="_bump_fee_when_new_inputs_need_to_be_added", simulate_moving_txs=simulate_moving_txs):
                self._bump_fee_when_new_inputs_need_to_be_added(
                    simulate_moving_txs=simulate_moving_txs,
                    config=config)
            with self.subTest(msg="_bump_fee_p2wpkh_when_there_is_only_a_single_output_and_that_is_a_change_address", simulate_moving_txs=simulate_moving_txs):
                self._bump_fee_p2wpkh_when_there_is_only_a_single_output_and_that_is_a_change_address(
                    simulate_moving_txs=simulate_moving_txs,
                    config=config)
            #with self.subTest(msg="_rbf_batching", simulate_moving_txs=simulate_moving_txs):
            #    self._rbf_batching(
            #        simulate_moving_txs=simulate_moving_txs,
            #        config=config)
            with self.subTest(msg="_bump_fee_when_not_all_inputs_are_ismine_subcase_some_outputs_are_ismine_but_not_all", simulate_moving_txs=simulate_moving_txs):
                self._bump_fee_when_not_all_inputs_are_ismine_subcase_some_outputs_are_ismine_but_not_all(
                    simulate_moving_txs=simulate_moving_txs,
                    config=config)
            with self.subTest(msg="_bump_fee_when_not_all_inputs_are_ismine_subcase_all_outputs_are_ismine", simulate_moving_txs=simulate_moving_txs):
                self._bump_fee_when_not_all_inputs_are_ismine_subcase_all_outputs_are_ismine(
                    simulate_moving_txs=simulate_moving_txs,
                    config=config)

    def _bump_fee_p2pkh_when_there_is_a_change_address(self, *, simulate_moving_txs, config):
        wallet = self.create_standard_wallet_from_seed('fold object utility erase deputy output stadium feed stereo usage modify bean',
                                                       config=config)

        # bootstrap wallet
        funding_tx = Transaction('010000000001011f4db0ecd81f4388db316bc16efb4e9daf874cf4950d54ecb4c0fb372433d68500000000171600143d57fd9e88ef0e70cddb0d8b75ef86698cab0d44fdffffff0280969800000000001976a91472e34cebab371967b038ce41d0e8fa1fb983795e88ac86a0ae020000000017a9149188bc82bdcae077060ebb4f02201b73c806edc887024830450221008e0725d531bd7dee4d8d38a0f921d7b1213e5b16c05312a80464ecc2b649598d0220596d309cf66d5f47cb3df558dbb43c5023a7796a80f5a88b023287e45a4db6b9012102c34d61ceafa8c216f01e05707672354f8119334610f7933a3f80dd7fb6290296bd391400')
        funding_txid = funding_tx.txid()
        funding_output_value = 10000000
        self.assertEqual('03052739fcfa2ead5f8e57e26021b0c2c546bcd3d74c6e708d5046dc58d90762', funding_txid)
        wallet.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1q7rl9cxr85962ztnsze089zs8ycv52hk488w4em', 2500000)]
        coins = wallet.get_spendable_coins(domain=None)
        tx = wallet.make_unsigned_transaction(coins=coins, outputs=outputs, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325501
        tx.version = 1
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff01007401000000016207d958dc46508d706e4cd7d3bc46c5c2b02160e2578e5fad2efafc392705030000000000fdffffff02a025260000000000160014f0fe5c1867a174a12e70165e728a072619455ed5585d7200000000001976a914aab9af3fbee0ab4e5c00d53e92f66d4bcb44f1bd88acbd391400000100fa010000000001011f4db0ecd81f4388db316bc16efb4e9daf874cf4950d54ecb4c0fb372433d68500000000171600143d57fd9e88ef0e70cddb0d8b75ef86698cab0d44fdffffff0280969800000000001976a91472e34cebab371967b038ce41d0e8fa1fb983795e88ac86a0ae020000000017a9149188bc82bdcae077060ebb4f02201b73c806edc887024830450221008e0725d531bd7dee4d8d38a0f921d7b1213e5b16c05312a80464ecc2b649598d0220596d309cf66d5f47cb3df558dbb43c5023a7796a80f5a88b023287e45a4db6b9012102c34d61ceafa8c216f01e05707672354f8119334610f7933a3f80dd7fb6290296bd391400220602a807c07bd7975211078e916bdda061d97e98d59a3631a804aada2f9a3f5b587a0c8296e57100000000000000000000220203aa6a5d43c6de66d60f50942cf34f20e02c2c6f55349548fbf2cde5dd5d69b9180c8296e571010000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        wallet.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertFalse(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet.is_mine(wallet.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(tx.txid(), tx_copy.txid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())
        self.assertEqual('01000000016207d958dc46508d706e4cd7d3bc46c5c2b02160e2578e5fad2efafc39270503000000006a4730440220751d2849157c1404b50e4532d7071b1f31de2bfe767597a8ab1090e3873af63002206c2a07a116e01f8964d8f9e496e42ce4db8619eb3b854c3f2900d232a8e1c261012102a807c07bd7975211078e916bdda061d97e98d59a3631a804aada2f9a3f5b587afdffffff02a025260000000000160014f0fe5c1867a174a12e70165e728a072619455ed5585d7200000000001976a914aab9af3fbee0ab4e5c00d53e92f66d4bcb44f1bd88acbd391400',
                         str(tx_copy))
        self.assertEqual('059c17eda7c6ccb43665ed6e86c66ef54a908be23d2c2f6bb835e394a8b16ab9', tx_copy.txid())
        self.assertEqual('059c17eda7c6ccb43665ed6e86c66ef54a908be23d2c2f6bb835e394a8b16ab9', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, funding_output_value - 2500000 - 5000, 0), wallet.get_balance())

        # bump tx TODO monacoin is OK?
        tx = wallet.bump_fee(tx=tx_from_any(tx.serialize()), new_fee_rate=70.0)
        tx.locktime = 1325501
        tx.version = 1
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff01007401000000016207d958dc46508d706e4cd7d3bc46c5c2b02160e2578e5fad2efafc392705030000000000fdffffff02a025260000000000160014f0fe5c1867a174a12e70165e728a072619455ed5e6337200000000001976a914aab9af3fbee0ab4e5c00d53e92f66d4bcb44f1bd88acbd391400000100fa010000000001011f4db0ecd81f4388db316bc16efb4e9daf874cf4950d54ecb4c0fb372433d68500000000171600143d57fd9e88ef0e70cddb0d8b75ef86698cab0d44fdffffff0280969800000000001976a91472e34cebab371967b038ce41d0e8fa1fb983795e88ac86a0ae020000000017a9149188bc82bdcae077060ebb4f02201b73c806edc887024830450221008e0725d531bd7dee4d8d38a0f921d7b1213e5b16c05312a80464ecc2b649598d0220596d309cf66d5f47cb3df558dbb43c5023a7796a80f5a88b023287e45a4db6b9012102c34d61ceafa8c216f01e05707672354f8119334610f7933a3f80dd7fb6290296bd391400220602a807c07bd7975211078e916bdda061d97e98d59a3631a804aada2f9a3f5b587a0c8296e57100000000000000000000220203aa6a5d43c6de66d60f50942cf34f20e02c2c6f55349548fbf2cde5dd5d69b9180c8296e571010000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertFalse(tx.is_complete())

        wallet.sign_transaction(tx, password=None)
        self.assertTrue(tx.is_complete())
        self.assertFalse(tx.is_segwit())
        tx_copy = tx_from_any(tx.serialize())
        self.assertEqual('01000000016207d958dc46508d706e4cd7d3bc46c5c2b02160e2578e5fad2efafc39270503000000006a473044022002a385e9645218af9ec22222743877a64b6a3ad1343e00a0dca876d5f2a54d6e02204e37a917acb1f237c3a068e2e268df4e7a74a4485e87c1feafbd235afc47bf71012102a807c07bd7975211078e916bdda061d97e98d59a3631a804aada2f9a3f5b587afdffffff02a025260000000000160014f0fe5c1867a174a12e70165e728a072619455ed5e6337200000000001976a914aab9af3fbee0ab4e5c00d53e92f66d4bcb44f1bd88acbd391400',
                         str(tx_copy))
        self.assertEqual('5065db7d36dbbd46274acfe6d23ba0cc3179c42656795179042834706264105f', tx_copy.txid())
        self.assertEqual('5065db7d36dbbd46274acfe6d23ba0cc3179c42656795179042834706264105f', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 7_484_390, 0), wallet.get_balance())

    def _bump_fee_p2pkh_when_there_are_two_ismine_outs_one_change_one_recv(self, *, simulate_moving_txs, config):
        """This tests a regression where sometimes we created a replacement tx
        that spent from the original (which is clearly invalid).
        """
        wallet = self.create_standard_wallet_from_seed('amazing vapor slab rib chat cousin east float plug baby session weird',
                                                       config=config)

        # bootstrap wallet
        funding_tx = Transaction('02000000000101a3a9d94039c1051102e36b835764b89985602608a3e121c91cb63d67277355080100000000fdffffff0220a10700000000001976a9143decc30f4f7eec45c5775347050b85a43ac7ee0b88ac203c3500000000001600149d91f0053172fab394d277ae27e9fa5c5a4921090247304402207a2b4abe2c4128fe80db297d636b81487feda2ee3c51a95bc670b7b377b09ca402205147bc550dfdff72e9159554c19045111daf6d95f556a4f4dc370c90aa37a3e0012102cccad56b36e7bd1ae44c37d69019d006d8911b43071725d6dcbbdfcade05650313f71c00')
        funding_txid = funding_tx.txid()
        self.assertEqual('0d98d8615f7b711beff2efcd4cf6b9f7ecd3b16a53fb9374e6a81d852492674e', funding_txid)
        wallet.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        orig_rbf_tx = Transaction('02000000014e679224851da8e67493fb536ab1d3ecf7b9f64ccdeff2ef1b717b5f61d8980d000000006a4730440220361b332f0488501e0605b9a5385edda762e761c00f95195f308e2baea5e12f9d0220051be1c834f0de69ecf084b0311abf541687436cb34311a002efa4f104a722a3012103d4ce4ba5be0b861d2ee7c715b84ab0e791ccd36530bd8652babae37eda693c39fdffffff02bc020000000000001976a914093107975170d4416bd2dad961414ac0a5c9b3de88ac389d0700000000001976a914ac55156f62fa9085c114fc6496aee5ab153cb22888ac13f71c00')
        orig_rbf_txid = orig_rbf_tx.txid()
        self.assertEqual('2bce74c17a2b4c1f57b454604c87006173716e92028de60463182c344f3e2180', orig_rbf_txid)
        wallet.receive_tx_callback(orig_rbf_txid, orig_rbf_tx, TX_HEIGHT_UNCONFIRMED)

        # bump tx
        tx = wallet.bump_fee(tx=tx_from_any(orig_rbf_tx.serialize()), new_fee_rate=200)
        self.assertTrue(not any([txin for txin in tx.inputs() if txin.prevout.txid.hex() == orig_rbf_txid]))
        tx.locktime = 1898260
        tx.version = 2
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff01005502000000014e679224851da8e67493fb536ab1d3ecf7b9f64ccdeff2ef1b717b5f61d8980d0000000000fdffffff01d4ed0600000000001976a914ac55156f62fa9085c114fc6496aee5ab153cb22888ac14f71c00000100e102000000000101a3a9d94039c1051102e36b835764b89985602608a3e121c91cb63d67277355080100000000fdffffff0220a10700000000001976a9143decc30f4f7eec45c5775347050b85a43ac7ee0b88ac203c3500000000001600149d91f0053172fab394d277ae27e9fa5c5a4921090247304402207a2b4abe2c4128fe80db297d636b81487feda2ee3c51a95bc670b7b377b09ca402205147bc550dfdff72e9159554c19045111daf6d95f556a4f4dc370c90aa37a3e0012102cccad56b36e7bd1ae44c37d69019d006d8911b43071725d6dcbbdfcade05650313f71c00220603d4ce4ba5be0b861d2ee7c715b84ab0e791ccd36530bd8652babae37eda693c390c11aad9ae000000000000000000220203feceda5212994b3552847c93288c47490404784d90f1966b7d02e009ba40680e0c11aad9ae000000000100000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertFalse(tx.is_complete())

        wallet.sign_transaction(tx, password=None)
        self.assertTrue(tx.is_complete())
        self.assertFalse(tx.is_segwit())
        tx_copy = tx_from_any(tx.serialize())
        self.assertEqual('02000000014e679224851da8e67493fb536ab1d3ecf7b9f64ccdeff2ef1b717b5f61d8980d000000006a473044022024ce838fb02d482ca33872197175a15fed66cf139ebcdb4cc840e227273a15f70220466306a037f2b9f9702b4a331672efcadde32a4df25dc4e28abd019b68eb2761012103d4ce4ba5be0b861d2ee7c715b84ab0e791ccd36530bd8652babae37eda693c39fdffffff01d4ed0600000000001976a914ac55156f62fa9085c114fc6496aee5ab153cb22888ac14f71c00',
                         str(tx_copy))
        self.assertEqual('198d85f7a2ab342f1d98c6838ef1d68fb79d10cb1c1842a5b152d4fffefbe483', tx_copy.txid())
        self.assertEqual('198d85f7a2ab342f1d98c6838ef1d68fb79d10cb1c1842a5b152d4fffefbe483', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 454100, 0), wallet.get_balance())


    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_cpfp_p2pkh(self, mock_save_db):
        wallet = self.create_standard_wallet_from_seed('fold object utility erase deputy output stadium feed stereo usage modify bean')

        # bootstrap wallet
        funding_tx = Transaction('010000000001010f40064d66d766144e17bb3276d96042fd5aee2196bcce7e415f839e55a83de800000000171600147b6d7c7763b9185b95f367cf28e4dc6d09441e73fdffffff02404b4c00000000001976a9141df43441a3a3ee563e560d3ddc7e07cc9f9c3cdb88ac009871000000000017a9143873281796131b1996d2f94ab265327ee5e9d6e28702473044022029c124e5a1e2c6fa12e45ccdbdddb45fec53f33b982389455b110fdb3fe4173102203b3b7656bca07e4eae3554900aa66200f46fec0af10e83daaa51d9e4e62a26f4012103c8f0460c245c954ef563df3b1743ea23b965f98b120497ac53bd6b8e8e9e0f9bbe391400')
        funding_txid = funding_tx.txid()
        funding_output_value = 5000000
        self.assertEqual('9973bf8918afa349b63934432386f585613b51034db6c8628b61ba2feb8a3668', funding_txid)
        wallet.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # cpfp tx
        tx = wallet.cpfp(funding_tx, fee=50000)
        tx.set_rbf(True)
        tx.locktime = 1325502
        tx.version = 1
        wallet.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertFalse(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        tx_copy = tx_from_any(tx.serialize())

        self.assertEqual(tx.txid(), tx_copy.txid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())
        self.assertEqual('010000000168368aeb2fba618b62c8b64d03513b6185f58623433439b649a3af1889bf7399000000006a473044022014139c4c8dd4148851c1306c4901b759799e87a22885a3c23f6a6472a3c580dd02205df8037a19261a80157143ee61d24b64b8f60c3cb196e36e758920669f88eb56012102a7536f0bfbc60c5a8e86e2b9df26431fc062f9f454016dbc26f2467e0bc98b3ffdffffff01f0874b00000000001976a914aab9af3fbee0ab4e5c00d53e92f66d4bcb44f1bd88acbe391400',
                         str(tx_copy))
        self.assertEqual('c064c0dd89077de615f0ff8a626d4a62092c02649ed8266ed4c54302918e87d5', tx_copy.txid())
        self.assertEqual('c064c0dd89077de615f0ff8a626d4a62092c02649ed8266ed4c54302918e87d5', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, funding_output_value - 50000, 0), wallet.get_balance())

    def _bump_fee_p2wpkh_when_there_is_a_change_address(self, *, simulate_moving_txs, config):
        wallet = self.create_standard_wallet_from_seed('frost repair depend effort salon ring foam oak cancel receive save usage',
                                                       config=config)

        # bootstrap wallet
        funding_tx = Transaction('01000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb391400')
        funding_txid = funding_tx.txid()
        funding_output_value = 12500000
        self.assertEqual('52e669a20a26c8b3df5b41e5e6309b18bcde8e1ad7ea17a18f63b6dc6c8becc0', funding_txid)
        wallet.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1q7rl9cxr85962ztnsze089zs8ycv52hk488w4em', 2500000)]
        coins = wallet.get_spendable_coins(domain=None)
        tx = wallet.make_unsigned_transaction(coins=coins, outputs=outputs, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325499
        tx.version = 1
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100710100000001c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff02a025260000000000160014f0fe5c1867a174a12e70165e728a072619455ed5585d720000000000160014f0fe5c1867a174a12e70165e728a072619455ed5bb391400000100fda20101000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb3914002206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a9039800000080000000000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a9039800000080010000000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a9039800000080010000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        wallet.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet.is_mine(wallet.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(tx.txid(), tx_copy.txid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())
        self.assertEqual('01000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff02a025260000000000160014f0fe5c1867a174a12e70165e728a072619455ed5585d720000000000160014f0fe5c1867a174a12e70165e728a072619455ed50247304402202b34122a1a337a20b6e48d17c90dfba64b1f690a9274bbc4686f46c641d9409f02204a0c6e1e6b487b7da93faa3c80639f62c90f65bae8662583987de8f02369b51c0121028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c5bb391400',
                         str(tx_copy))
        self.assertEqual('ff389af3243e59d9d7f986a95179f62bb06fb7c8e9b5b0e80f13d9cef8213773', tx_copy.txid())
        self.assertEqual('11d7bdde910e115a4246444027edd726a909280a526171abba953a691ec0df6d', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, funding_output_value - 2500000 - 5000, 0), wallet.get_balance())

        # bump tx
        tx = wallet.bump_fee(tx=tx_from_any(tx.serialize()), new_fee_rate=70.0)
        tx.locktime = 1325500
        tx.version = 1
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100710100000001c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff029a12260000000000160014f0fe5c1867a174a12e70165e728a072619455ed5585d720000000000160014f0fe5c1867a174a12e70165e728a072619455ed5bc391400000100fda20101000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb3914002206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a9039800000080000000000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a9039800000080010000000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a9039800000080010000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertFalse(tx.is_complete())

        wallet.sign_transaction(tx, password=None)
        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        tx_copy = tx_from_any(tx.serialize())
        self.assertEqual('01000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff029a12260000000000160014f0fe5c1867a174a12e70165e728a072619455ed5585d720000000000160014f0fe5c1867a174a12e70165e728a072619455ed502473044022025674d60b30e1d2dd8f135a5e1a09d6e42f50b9e1db33ccbf16f172e8d92cafa02200898d6a08ef061f49dd8dcbe969bb0fc9e83ff32da8fe4fae83f1e03b5577fe50121028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c5bc391400',
                         str(tx_copy))
        self.assertEqual('18258a311a6df0961830ea981105c548728f94839128dc469c9a4ad59f013500', tx_copy.txid())
        self.assertEqual('d664edcdb0f5f3a9225884b8f915be8365fae5d787c141902973c9b13ecb48aa', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 9_990_130, 0), wallet.get_balance())

    def _bump_fee_when_not_all_inputs_are_ismine_subcase_some_outputs_are_ismine_but_not_all(self, *, simulate_moving_txs, config):
        class NetworkMock:
            relay_fee = 1000
            async def get_transaction(self, txid, timeout=None):
                if txid == "597098f9077cd2a7bf5bb2a03c9ae5fcd9d1f07c0891cb42cbb129cf9eaf57fd":
                    return "02000000000102a5883f3de780d260e6f26cf85144403c7744a65a44cd38f9ff45aecadf010c540000000000fdffffffbdeb0175b1c51c96843d1952f7e1c49c1703717d7d020048d4de0a8eed94dad50000000000fdffffff03b2a00700000000001600140cd6c9f8ce0aa73d77fcf7f156c74f5cbec6906bb2a00700000000001600146435504ddc95e6019a90bb7dfc7ca81a88a8633106d790000000000016001444bd3017ee214370abf683abaa7f6204c9f40210024730440220652a04a2a301d9a031a034f3ae48174e204e17acf7bfc27f0dcab14243f73e2202207b29e964c434dfb2c515232d36566a40dccd4dd93ccb7fd15260ecbda10f0d9801210231994e564a0530068d17a9b0f85bec58d1352517a2861ea99e5b3070d2c5dbda02473044022072186473874919019da0e3d92b6e0aa4f88cba448ed5434615e5a3c8e2b7c42a02203ec05cef66960d5bc45d0f3d25675190cf8035b11a05ed4b719fd9c3a894899b012102f5fdca8c4e30ba0a1babf9cf9ebe62519b08aead351c349ed1ffc8316c24f542d7f61c00"
                else:
                    raise Exception("unexpected txid")
            def has_internet_connection(self):
                return True
            def run_from_another_thread(self, coro, *, timeout=None):
                loop, stop_loop, loop_thread = create_and_start_event_loop()
                fut = asyncio.run_coroutine_threadsafe(coro, loop)
                try:
                    return fut.result(timeout)
                finally:
                    loop.call_soon_threadsafe(stop_loop.set_result, 1)
                    loop_thread.join(timeout=1)
            def get_local_height(self):
                return 0
            def blockchain(self):
                class BlockchainMock:
                    def is_tip_stale(self):
                        return True
                return BlockchainMock()

        wallet = self.create_standard_wallet_from_seed('mix total present junior leader live state athlete mistake crack wall valve',
                                                       config=config)
        wallet.network = NetworkMock()

        # bootstrap wallet
        funding_tx = Transaction('02000000000101a5883f3de780d260e6f26cf85144403c7744a65a44cd38f9ff45aecadf010c540100000000fdffffff0220a1070000000000160014db44724ac632ae47ee5765954d64796dd5fec72708de3c000000000016001424b32aadb42a89016c4de8f11741c3b29b15f21c02473044022045cc6c1cc875cbb0c0d8fe323dc1de9716e49ed5659741b0fb3dd9a196894066022077c242640071d12ec5763c5870f482a4823d8713e4bd14353dd621ed29a7f96d012102aea8d439a0f79d8b58e8d7bda83009f587e1f3da350adaa484329bf47cd03465fef61c00')
        funding_txid = funding_tx.txid()
        self.assertEqual('08557327673db61cc921e1a30826608599b86457836be3021105c13940d9a9a3', funding_txid)
        wallet.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        orig_rbf_tx = Transaction('02000000000102a3a9d94039c1051102e36b835764b89985602608a3e121c91cb63d67277355080000000000fdfffffffd57af9ecf29b1cb42cb91087cf0d1d9fce59a3ca0b25bbfa7d27c07f99870590200000000fdffffff03b2a00700000000001600145dc80fd43eb70fd21a6c4446e3ce043df94f100cb2a00700000000001600147db4ab480b7d2218fba561ff304178f4afcbc972be358900000000001600149d91f0053172fab394d277ae27e9fa5c5a49210902473044022003999f03be8b9e299b2cd3bc7bce05e273d5d9ce24fc47af8754f26a7a13e13f022004e668499a67061789f6ebd2932c969ece74417ae3f2307bf696428bbed4fe36012102a1c9b25b37aa31ccbb2d72caaffce81ec8253020a74017d92bbfc14a832fc9cb0247304402207121358a66c0e716e2ba2be928076736261c691b4fbf89ea8d255449a4f5837b022042cadf9fe1b4f3c03ede3cef6783b42f0ba319f2e0273b624009cd023488c4c1012103a5ba95fb1e0043428ed70680fc17db254b3f701dfccf91e48090aa17c1b7ea40fef61c00')
        orig_rbf_txid = orig_rbf_tx.txid()
        self.assertEqual('6057690010ddac93a371629e1f41866400623e13a9cd336d280fc3239086a983', orig_rbf_txid)
        wallet.receive_tx_callback(orig_rbf_txid, orig_rbf_tx, TX_HEIGHT_UNCONFIRMED)

        # bump tx
        tx = wallet.bump_fee(tx=tx_from_any(orig_rbf_tx.serialize()), new_fee_rate=70)
        tx.locktime = 1898268
        tx.version = 2
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100b90200000002a3a9d94039c1051102e36b835764b89985602608a3e121c91cb63d67277355080000000000fdfffffffd57af9ecf29b1cb42cb91087cf0d1d9fce59a3ca0b25bbfa7d27c07f99870590200000000fdffffff031660070000000000160014a36590fb127d05cf17a07a84a17f2f2d6cc90a7bb2a00700000000001600147db4ab480b7d2218fba561ff304178f4afcbc972be358900000000001600149d91f0053172fab394d277ae27e9fa5c5a4921091cf71c00000100de02000000000101a5883f3de780d260e6f26cf85144403c7744a65a44cd38f9ff45aecadf010c540100000000fdffffff0220a1070000000000160014db44724ac632ae47ee5765954d64796dd5fec72708de3c000000000016001424b32aadb42a89016c4de8f11741c3b29b15f21c02473044022045cc6c1cc875cbb0c0d8fe323dc1de9716e49ed5659741b0fb3dd9a196894066022077c242640071d12ec5763c5870f482a4823d8713e4bd14353dd621ed29a7f96d012102aea8d439a0f79d8b58e8d7bda83009f587e1f3da350adaa484329bf47cd03465fef61c00220602a1c9b25b37aa31ccbb2d72caaffce81ec8253020a74017d92bbfc14a832fc9cb109c9fff98000000800000000000000000000100fd910102000000000102a5883f3de780d260e6f26cf85144403c7744a65a44cd38f9ff45aecadf010c540000000000fdffffffbdeb0175b1c51c96843d1952f7e1c49c1703717d7d020048d4de0a8eed94dad50000000000fdffffff03b2a00700000000001600140cd6c9f8ce0aa73d77fcf7f156c74f5cbec6906bb2a00700000000001600146435504ddc95e6019a90bb7dfc7ca81a88a8633106d790000000000016001444bd3017ee214370abf683abaa7f6204c9f40210024730440220652a04a2a301d9a031a034f3ae48174e204e17acf7bfc27f0dcab14243f73e2202207b29e964c434dfb2c515232d36566a40dccd4dd93ccb7fd15260ecbda10f0d9801210231994e564a0530068d17a9b0f85bec58d1352517a2861ea99e5b3070d2c5dbda02473044022072186473874919019da0e3d92b6e0aa4f88cba448ed5434615e5a3c8e2b7c42a02203ec05cef66960d5bc45d0f3d25675190cf8035b11a05ed4b719fd9c3a894899b012102f5fdca8c4e30ba0a1babf9cf9ebe62519b08aead351c349ed1ffc8316c24f542d7f61c0000220203b1b437d6d3366441e63e387594ffacb80676d7d518971d1d284b775cd7d8c38b109c9fff98000000800100000000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertFalse(tx.is_complete())

        wallet.sign_transaction(tx, password=None)
        self.assertFalse(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        tx_copy = tx_from_any(tx.serialize())
        self.assertEqual('70736274ff0100b90200000002a3a9d94039c1051102e36b835764b89985602608a3e121c91cb63d67277355080000000000fdfffffffd57af9ecf29b1cb42cb91087cf0d1d9fce59a3ca0b25bbfa7d27c07f99870590200000000fdffffff031660070000000000160014a36590fb127d05cf17a07a84a17f2f2d6cc90a7bb2a00700000000001600147db4ab480b7d2218fba561ff304178f4afcbc972be358900000000001600149d91f0053172fab394d277ae27e9fa5c5a4921091cf71c00000100de02000000000101a5883f3de780d260e6f26cf85144403c7744a65a44cd38f9ff45aecadf010c540100000000fdffffff0220a1070000000000160014db44724ac632ae47ee5765954d64796dd5fec72708de3c000000000016001424b32aadb42a89016c4de8f11741c3b29b15f21c02473044022045cc6c1cc875cbb0c0d8fe323dc1de9716e49ed5659741b0fb3dd9a196894066022077c242640071d12ec5763c5870f482a4823d8713e4bd14353dd621ed29a7f96d012102aea8d439a0f79d8b58e8d7bda83009f587e1f3da350adaa484329bf47cd03465fef61c0001070001086b0247304402201f5ea643f6bc59c96ab8f1a3935b455e8f9395a67b74d618d121d16ae76f7b440220574d05df88740f915798e7993158c08e544801a044d19ef140574da19c1937d7012102a1c9b25b37aa31ccbb2d72caaffce81ec8253020a74017d92bbfc14a832fc9cb000100fd910102000000000102a5883f3de780d260e6f26cf85144403c7744a65a44cd38f9ff45aecadf010c540000000000fdffffffbdeb0175b1c51c96843d1952f7e1c49c1703717d7d020048d4de0a8eed94dad50000000000fdffffff03b2a00700000000001600140cd6c9f8ce0aa73d77fcf7f156c74f5cbec6906bb2a00700000000001600146435504ddc95e6019a90bb7dfc7ca81a88a8633106d790000000000016001444bd3017ee214370abf683abaa7f6204c9f40210024730440220652a04a2a301d9a031a034f3ae48174e204e17acf7bfc27f0dcab14243f73e2202207b29e964c434dfb2c515232d36566a40dccd4dd93ccb7fd15260ecbda10f0d9801210231994e564a0530068d17a9b0f85bec58d1352517a2861ea99e5b3070d2c5dbda02473044022072186473874919019da0e3d92b6e0aa4f88cba448ed5434615e5a3c8e2b7c42a02203ec05cef66960d5bc45d0f3d25675190cf8035b11a05ed4b719fd9c3a894899b012102f5fdca8c4e30ba0a1babf9cf9ebe62519b08aead351c349ed1ffc8316c24f542d7f61c0000220203b1b437d6d3366441e63e387594ffacb80676d7d518971d1d284b775cd7d8c38b109c9fff98000000800100000000000000000000',
                         tx_copy.serialize_as_bytes().hex())
        self.assertEqual('6a8ed07cd97a10ace851b67a65035f04ff477d67cde62bb8679007e87b214e79', tx_copy.txid())

    def _bump_fee_when_not_all_inputs_are_ismine_subcase_all_outputs_are_ismine(self, *, simulate_moving_txs, config):
        class NetworkMock:
            relay_fee = 1000
            async def get_transaction(self, txid, timeout=None):
                if txid == "08557327673db61cc921e1a30826608599b86457836be3021105c13940d9a9a3":
                    return "02000000000101a5883f3de780d260e6f26cf85144403c7744a65a44cd38f9ff45aecadf010c540100000000fdffffff0220a1070000000000160014db44724ac632ae47ee5765954d64796dd5fec72708de3c000000000016001424b32aadb42a89016c4de8f11741c3b29b15f21c02473044022045cc6c1cc875cbb0c0d8fe323dc1de9716e49ed5659741b0fb3dd9a196894066022077c242640071d12ec5763c5870f482a4823d8713e4bd14353dd621ed29a7f96d012102aea8d439a0f79d8b58e8d7bda83009f587e1f3da350adaa484329bf47cd03465fef61c00"
                else:
                    raise Exception("unexpected txid")
            def has_internet_connection(self):
                return True
            def run_from_another_thread(self, coro, *, timeout=None):
                loop, stop_loop, loop_thread = create_and_start_event_loop()
                fut = asyncio.run_coroutine_threadsafe(coro, loop)
                try:
                    return fut.result(timeout)
                finally:
                    loop.call_soon_threadsafe(stop_loop.set_result, 1)
                    loop_thread.join(timeout=1)
            def get_local_height(self):
                return 0
            def blockchain(self):
                class BlockchainMock:
                    def is_tip_stale(self):
                        return True
                return BlockchainMock()

        wallet = self.create_standard_wallet_from_seed(
            'faint orbit extend hope moon head mercy still debate sick cotton path',
            config=config,
            gap_limit=4,
        )
        wallet.network = NetworkMock()

        # bootstrap wallet
        funding_tx = Transaction('02000000000102c247447533b530cacc3e716aae84621857f04a483252374cbdccfdf8b4ef816b0000000000fdffffffc247447533b530cacc3e716aae84621857f04a483252374cbdccfdf8b4ef816b0100000000fdffffff01d63f0f00000000001600141ef4658adb12ec745a1a1fef6ab8897f04bade060247304402201dc5be86749d8ce33571a6f1a2f8bbfceba89b9dbf2b4683e66c8c17cf7df6090220729199516cb894569ebbe3e998d47fc74030231ed30f110c9babd8a9dc361115012102728251a5f5f55375eef3c14fe59ab0755ba4d5f388619895238033ac9b51aad20247304402202e5d416489c20810e96e931b98a84b0c0c4fc32d2d34d3470b7ee16810246a4c022040f86cf8030d2117d6487bbe6e23d68d6d70408b002d8055de1f33d038d3a0550121039c009e7e7dad07e74ec5a8ac9f9e3499420dd9fe9709995525c714170152512620f71c00')
        funding_txid = funding_tx.txid()
        self.assertEqual('59ff0dd3962db651444d9fa6a61311302e47158533714d006e7e024ce45777da', funding_txid)
        wallet.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        orig_rbf_tx = Transaction('02000000000102a3a9d94039c1051102e36b835764b89985602608a3e121c91cb63d67277355080000000000fdffffffda7757e44c027e6e004d71338515472e301113a6a69f4d4451b62d96d30dff590000000000fdffffff02b2a00700000000001600144710cfecc31828d31e68ad101dd022fe091a02b1683f0f00000000001600145fd89e3ff2f32c48d85ac65edb4fdf40112ffdfb02473044022032a64a01b0975b65b0adfee53baa6dfb2ca9917714ae3f3acbe609397cc4912d02207da348511a156f6b6eab9d4c762a421e629784108c61d128ad9409483c1e4819012102a1c9b25b37aa31ccbb2d72caaffce81ec8253020a74017d92bbfc14a832fc9cb024730440220620795910e9d96680a2d869024fc5048cb80d038e60a5b92850de65eb938a49c02201a550737b18eda5f93ce3ce0c5907d7b0a9856bbc3bb81cec14349c5b6c97c08012102999b1062a5acf7071a43fd6f2bd37a4e0f7162182490661949dbeeb7d1b03401eef61c00')
        orig_rbf_txid = orig_rbf_tx.txid()
        self.assertEqual('2dcc543035c90c25734c9381096cc2f211ac1c2467e072170bc9e51e4580029b', orig_rbf_txid)
        wallet.receive_tx_callback(orig_rbf_txid, orig_rbf_tx, TX_HEIGHT_UNCONFIRMED)

        # bump tx
        tx = wallet.bump_fee(tx=tx_from_any(orig_rbf_tx.serialize()), new_fee_rate=50)
        tx.locktime = 1898273
        tx.version = 2
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff01009a0200000002a3a9d94039c1051102e36b835764b89985602608a3e121c91cb63d67277355080000000000fdffffffda7757e44c027e6e004d71338515472e301113a6a69f4d4451b62d96d30dff590000000000fdffffff02bc780700000000001600144710cfecc31828d31e68ad101dd022fe091a02b1683f0f00000000001600145fd89e3ff2f32c48d85ac65edb4fdf40112ffdfb21f71c00000100de02000000000101a5883f3de780d260e6f26cf85144403c7744a65a44cd38f9ff45aecadf010c540100000000fdffffff0220a1070000000000160014db44724ac632ae47ee5765954d64796dd5fec72708de3c000000000016001424b32aadb42a89016c4de8f11741c3b29b15f21c02473044022045cc6c1cc875cbb0c0d8fe323dc1de9716e49ed5659741b0fb3dd9a196894066022077c242640071d12ec5763c5870f482a4823d8713e4bd14353dd621ed29a7f96d012102aea8d439a0f79d8b58e8d7bda83009f587e1f3da350adaa484329bf47cd03465fef61c00000100fd530102000000000102c247447533b530cacc3e716aae84621857f04a483252374cbdccfdf8b4ef816b0000000000fdffffffc247447533b530cacc3e716aae84621857f04a483252374cbdccfdf8b4ef816b0100000000fdffffff01d63f0f00000000001600141ef4658adb12ec745a1a1fef6ab8897f04bade060247304402201dc5be86749d8ce33571a6f1a2f8bbfceba89b9dbf2b4683e66c8c17cf7df6090220729199516cb894569ebbe3e998d47fc74030231ed30f110c9babd8a9dc361115012102728251a5f5f55375eef3c14fe59ab0755ba4d5f388619895238033ac9b51aad20247304402202e5d416489c20810e96e931b98a84b0c0c4fc32d2d34d3470b7ee16810246a4c022040f86cf8030d2117d6487bbe6e23d68d6d70408b002d8055de1f33d038d3a0550121039c009e7e7dad07e74ec5a8ac9f9e3499420dd9fe9709995525c714170152512620f71c00220602999b1062a5acf7071a43fd6f2bd37a4e0f7162182490661949dbeeb7d1b0340110277f031200000080000000000000000000220202519a4072fd8c29362693439f441bd7a45c0d8dea26ce88872a4bca7e5d07cb4510277f03120000008000000000020000000022020314c9b46fce4c6111e4bbe89bb06b3dd29c6cbac586a4914bb18fe8bb7e0a463c10277f031200000080000000000100000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertFalse(tx.is_complete())

        wallet.sign_transaction(tx, password=None)
        self.assertFalse(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        tx_copy = tx_from_any(tx.serialize())
        self.assertEqual('70736274ff01009a0200000002a3a9d94039c1051102e36b835764b89985602608a3e121c91cb63d67277355080000000000fdffffffda7757e44c027e6e004d71338515472e301113a6a69f4d4451b62d96d30dff590000000000fdffffff02bc780700000000001600144710cfecc31828d31e68ad101dd022fe091a02b1683f0f00000000001600145fd89e3ff2f32c48d85ac65edb4fdf40112ffdfb21f71c00000100de02000000000101a5883f3de780d260e6f26cf85144403c7744a65a44cd38f9ff45aecadf010c540100000000fdffffff0220a1070000000000160014db44724ac632ae47ee5765954d64796dd5fec72708de3c000000000016001424b32aadb42a89016c4de8f11741c3b29b15f21c02473044022045cc6c1cc875cbb0c0d8fe323dc1de9716e49ed5659741b0fb3dd9a196894066022077c242640071d12ec5763c5870f482a4823d8713e4bd14353dd621ed29a7f96d012102aea8d439a0f79d8b58e8d7bda83009f587e1f3da350adaa484329bf47cd03465fef61c00000100fd530102000000000102c247447533b530cacc3e716aae84621857f04a483252374cbdccfdf8b4ef816b0000000000fdffffffc247447533b530cacc3e716aae84621857f04a483252374cbdccfdf8b4ef816b0100000000fdffffff01d63f0f00000000001600141ef4658adb12ec745a1a1fef6ab8897f04bade060247304402201dc5be86749d8ce33571a6f1a2f8bbfceba89b9dbf2b4683e66c8c17cf7df6090220729199516cb894569ebbe3e998d47fc74030231ed30f110c9babd8a9dc361115012102728251a5f5f55375eef3c14fe59ab0755ba4d5f388619895238033ac9b51aad20247304402202e5d416489c20810e96e931b98a84b0c0c4fc32d2d34d3470b7ee16810246a4c022040f86cf8030d2117d6487bbe6e23d68d6d70408b002d8055de1f33d038d3a0550121039c009e7e7dad07e74ec5a8ac9f9e3499420dd9fe9709995525c714170152512620f71c0001070001086b0247304402206842258bbe37829facadef81fa17eb1c97e6f9a4c66717c0cea37b61c9be804902203d291a2c9e3df57e3422f9b90589c2350f0168867c3320e994258169b8da402b012102999b1062a5acf7071a43fd6f2bd37a4e0f7162182490661949dbeeb7d1b0340100220202519a4072fd8c29362693439f441bd7a45c0d8dea26ce88872a4bca7e5d07cb4510277f03120000008000000000020000000022020314c9b46fce4c6111e4bbe89bb06b3dd29c6cbac586a4914bb18fe8bb7e0a463c10277f031200000080000000000100000000',
                         tx_copy.serialize_as_bytes().hex())
        self.assertEqual('b46cdce7e7564dfd09618ab9008ec3a921c6372f3dcdab2f6094735b024485f0', tx_copy.txid())


    def _bump_fee_p2wpkh_when_there_is_only_a_single_output_and_that_is_a_change_address(self, *, simulate_moving_txs, config):
        wallet = self.create_standard_wallet_from_seed('frost repair depend effort salon ring foam oak cancel receive save usage',
                                                       config=config)

        # bootstrap wallet
        funding_tx = Transaction('01000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb391400')
        funding_txid = funding_tx.txid()
        funding_output_value = 10000000
        self.assertEqual('52e669a20a26c8b3df5b41e5e6309b18bcde8e1ad7ea17a18f63b6dc6c8becc0', funding_txid)
        wallet.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1q7rl9cxr85962ztnsze089zs8ycv52hk488w4em', '!')]
        coins = wallet.get_spendable_coins(domain=None)
        tx = wallet.make_unsigned_transaction(coins=coins, outputs=outputs, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325499
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100520200000001c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff01f882980000000000160014f0fe5c1867a174a12e70165e728a072619455ed5bb391400000100fda20101000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb3914002206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a9039800000080000000000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a9039800000080010000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        wallet.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet.is_mine(wallet.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(tx.txid(), tx_copy.txid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())
        self.assertEqual('02000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff01f882980000000000160014f0fe5c1867a174a12e70165e728a072619455ed50247304402201050a398878098e695e2fcef181383d529d0bd0c959554bc01c35cc1791dd83b02202a193fbc77ab47879093d01c131fd4f2c80dd76750b7f0be027751ca970b84a50121028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c5bb391400',
                         str(tx_copy))
        self.assertEqual('839b4d7ec2480975126ffa0c2a4552a85dd43435b23b375536391943e1f27074', tx_copy.txid())
        self.assertEqual('b6fc78267494951771d935ef0338f50b13e62258e54265ad4989fe9ffe98b018', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, funding_output_value - 5000, 0), wallet.get_balance())

        # bump tx
        tx = wallet.bump_fee(tx=tx_from_any(tx.serialize()), new_fee_rate=75)
        tx.locktime = 1325500
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100520200000001c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff014676980000000000160014f0fe5c1867a174a12e70165e728a072619455ed5bc391400000100fda20101000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb3914002206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a9039800000080000000000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a9039800000080010000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertFalse(tx.is_complete())

        wallet.sign_transaction(tx, password=None)
        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        tx_copy = tx_from_any(tx.serialize())
        self.assertEqual('02000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff014676980000000000160014f0fe5c1867a174a12e70165e728a072619455ed502473044022008bcb6fab261e9f4d5ccdd11c389b0620de1a1f493e97df6ec83f0c1a261e96c02205e352d3096cc68d4b1279f05dd4a2b1f9d1134dd01f761d01e21f4a88e608cca0121028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c5bc391400',
                         str(tx_copy))
        self.assertEqual('0787da6829907ede8a322273d19ba47943ac234ad7fd1cb1821f6a0e78fcc003', tx_copy.txid())
        self.assertEqual('65760ae60ed5feedfd10a9198b44e483ea64dcfa116d32cf247f45d474ee5ce0', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 9_991_750, 0), wallet.get_balance())

    def _bump_fee_when_user_sends_max(self, *, simulate_moving_txs, config):
        wallet = self.create_standard_wallet_from_seed('frost repair depend effort salon ring foam oak cancel receive save usage',
                                                       config=config)

        # bootstrap wallet
        funding_tx = Transaction('01000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb391400')
        funding_txid = funding_tx.txid()
        self.assertEqual('52e669a20a26c8b3df5b41e5e6309b18bcde8e1ad7ea17a18f63b6dc6c8becc0', funding_txid)
        wallet.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1q7rl9cxr85962ztnsze089zs8ycv52hk488w4em', '!')]
        coins = wallet.get_spendable_coins(domain=None)
        tx = wallet.make_unsigned_transaction(coins=coins, outputs=outputs, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325499
        tx.version = 1
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100520100000001c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff01f882980000000000160014f0fe5c1867a174a12e70165e728a072619455ed5bb391400000100fda20101000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb3914002206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a9039800000080000000000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a9039800000080010000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        wallet.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet.is_mine(wallet.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(tx.txid(), tx_copy.txid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())
        self.assertEqual('01000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff01f882980000000000160014f0fe5c1867a174a12e70165e728a072619455ed502473044022043385f12b2b5c14086e9c77d6bcb63fcdd88a1510f0db592ea9fc3baff9ba5da02204447991604078e5397e4a6f8d07f919fbc05a3dfcf7c36a796755e6bf6853bf90121028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c5bb391400',
                         str(tx_copy))
        self.assertEqual('43ea6fbf29e5eb87a5566d38e6239177529d928fe201509526384a07ce292022', tx_copy.txid())
        self.assertEqual('31dc70f33d13aa611d4d2d2b813a71f9f071e85af1e7d2f17de4727b5af694dd', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 9_995_000, 0), wallet.get_balance())

        # bump tx
        tx = wallet.bump_fee(tx=tx_from_any(tx.serialize()), new_fee_rate=70.0)
        tx.locktime = 1325500
        tx.version = 1
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100520100000001c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff016c78980000000000160014f0fe5c1867a174a12e70165e728a072619455ed5bc391400000100fda20101000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb3914002206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a9039800000080000000000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a9039800000080010000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertFalse(tx.is_complete())

        wallet.sign_transaction(tx, password=None)
        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        tx_copy = tx_from_any(tx.serialize())
        self.assertEqual('01000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff016c78980000000000160014f0fe5c1867a174a12e70165e728a072619455ed502473044022035098c48b634370daa187a48b3d8cf531de84882b25c1b3816f1b47b65b2903c022053743dc3d6393a3987386faacde1d08df7796a4055fb28797fdc65f4a7c47b1d0121028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c5bc391400',
                         str(tx_copy))
        self.assertEqual('564b5617823c211b8169e83276168d20274ba474b61404cd5dfed7c5ef3d51b7', tx_copy.txid())
        self.assertEqual('436edb20372abf0d8d7737fd9e017116589ef5cfb0e10e503bae998a921f3418', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 9_992_300, 0), wallet.get_balance())

    def _bump_fee_when_new_inputs_need_to_be_added(self, *, simulate_moving_txs, config):
        wallet = self.create_standard_wallet_from_seed('frost repair depend effort salon ring foam oak cancel receive save usage',
                                                       config=config)

        # bootstrap wallet (incoming funding_tx1)
        funding_tx1 = Transaction('01000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb391400')
        funding_txid1 = funding_tx1.txid()
        #funding_output_value = 10_000_000
        self.assertEqual('52e669a20a26c8b3df5b41e5e6309b18bcde8e1ad7ea17a18f63b6dc6c8becc0', funding_txid1)
        wallet.receive_tx_callback(funding_txid1, funding_tx1, TX_HEIGHT_UNCONFIRMED)

        # create tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1q7rl9cxr85962ztnsze089zs8ycv52hk488w4em', '!')]
        coins = wallet.get_spendable_coins(domain=None)
        tx = wallet.make_unsigned_transaction(coins=coins, outputs=outputs, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325499
        tx.version = 1
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100520100000001c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff01f882980000000000160014f0fe5c1867a174a12e70165e728a072619455ed5bb391400000100fda20101000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb3914002206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a9039800000080000000000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a9039800000080010000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        wallet.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet.is_mine(wallet.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(tx.txid(), tx_copy.txid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())
        self.assertEqual('01000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff01f882980000000000160014f0fe5c1867a174a12e70165e728a072619455ed502473044022043385f12b2b5c14086e9c77d6bcb63fcdd88a1510f0db592ea9fc3baff9ba5da02204447991604078e5397e4a6f8d07f919fbc05a3dfcf7c36a796755e6bf6853bf90121028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c5bb391400',
                         str(tx_copy))
        self.assertEqual('43ea6fbf29e5eb87a5566d38e6239177529d928fe201509526384a07ce292022', tx_copy.txid())
        self.assertEqual('31dc70f33d13aa611d4d2d2b813a71f9f071e85af1e7d2f17de4727b5af694dd', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 9_995_000, 0), wallet.get_balance())

        # another incoming transaction (funding_tx2)
        funding_tx2 = Transaction('01000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520000000017160014ba9ca815474a674ff1efb3fc82cf0f3460de8c57fdffffff0230390f000000000017a9148b59abaca8215c0d4b18cbbf715550aa2b50c85b87404b4c000000000016001483c3bc7234f17a209cc5dcce14903b54ee4dab9002473044022038a05f7d38bcf810dfebb39f1feda5cc187da4cf5d6e56986957ddcccedc75d302203ab67ccf15431b4e2aeeab1582b9a5a7821e7ac4be8ebf512505dbfdc7e094fd0121032168234e0ba465b8cedc10173ea9391725c0f6d9fa517641af87926626a5144abd391400')
        funding_txid2 = funding_tx2.txid()
        #funding_output_value = 5_000_000
        self.assertEqual('c36a6e1cd54df108e69574f70bc9b88dc13beddc70cfad9feb7f8f6593255d4a', funding_txid2)
        wallet.receive_tx_callback(funding_txid2, funding_tx2, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 14_995_000, 0), wallet.get_balance())

        # bump tx
        tx = wallet.bump_fee(tx=tx_from_any(tx.serialize()), new_fee_rate=70.0)
        tx.locktime = 1325500
        tx.version = 1
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100520100000001c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff016c78980000000000160014f0fe5c1867a174a12e70165e728a072619455ed5bc391400000100fda20101000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb3914002206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a9039800000080000000000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a9039800000080010000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertFalse(tx.is_complete())

        wallet.sign_transaction(tx, password=None)
        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        tx_copy = tx_from_any(tx.serialize())
        self.assertEqual('01000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff016c78980000000000160014f0fe5c1867a174a12e70165e728a072619455ed502473044022035098c48b634370daa187a48b3d8cf531de84882b25c1b3816f1b47b65b2903c022053743dc3d6393a3987386faacde1d08df7796a4055fb28797fdc65f4a7c47b1d0121028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c5bc391400',
                         str(tx_copy))
        self.assertEqual('564b5617823c211b8169e83276168d20274ba474b61404cd5dfed7c5ef3d51b7', tx_copy.txid())
        self.assertEqual('436edb20372abf0d8d7737fd9e017116589ef5cfb0e10e503bae998a921f3418', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 14_992_300, 0), wallet.get_balance())


    def _rbf_batching(self, *, simulate_moving_txs, config):
        wallet = self.create_standard_wallet_from_seed('frost repair depend effort salon ring foam oak cancel receive save usage',
                                                       config=config)
        wallet.config.set_key('batch_rbf', True)

        # bootstrap wallet (incoming funding_tx1)
        funding_tx1 = Transaction('01000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb391400')
        funding_txid1 = funding_tx1.txid()
        #funding_output_value = 10_000_000
        self.assertEqual('52e669a20a26c8b3df5b41e5e6309b18bcde8e1ad7ea17a18f63b6dc6c8becc0', funding_txid1)
        wallet.receive_tx_callback(funding_txid1, funding_tx1, TX_HEIGHT_UNCONFIRMED)

        # create tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1q7rl9cxr85962ztnsze089zs8ycv52hk488w4em', 2_500_000)]
        coins = wallet.get_spendable_coins(domain=None)
        tx = wallet.make_unsigned_transaction(coins=coins, outputs=outputs, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325499
        tx.version = 1
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100720100000001c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff02a02526000000000017a9145a71fc1a7a98ddd67be935ade1600981c0d066f987585d720000000000160014f0fe5c1867a174a12e70165e728a072619455ed5bb391400000100fda20101000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb3914002206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a903980000008000000000000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a9039800000080010000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        wallet.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet.is_mine(wallet.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(tx.txid(), tx_copy.txid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())
        self.assertEqual('01000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff02a02526000000000017a9145a71fc1a7a98ddd67be935ade1600981c0d066f987585d720000000000160014f0fe5c1867a174a12e70165e728a072619455ed50247304402205442705e988abe74bf391b293bb1b886674284a92ed0788c33024f9336d60aef022013a93049d3bed693254cd31a704d70bb988a36750f0b74d0a5b4d9e29c54ca9d0121028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c5bb391400',
                         str(tx_copy))
        self.assertEqual('b019bbad45a46ed25365e46e4cae6428fb12ae425977eb93011ffb294cb4977e', tx_copy.txid())
        self.assertEqual('ba87313e2b3b42f1cc478843d4d53c72d6e06f6c66ac8cfbe2a59cdac2fd532d', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 9_995_000, 0), wallet.get_balance())

        # another incoming transaction (funding_tx2)
        funding_tx2 = Transaction('01000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520000000017160014ba9ca815474a674ff1efb3fc82cf0f3460de8c57fdffffff0230390f000000000017a9148b59abaca8215c0d4b18cbbf715550aa2b50c85b87404b4c000000000016001483c3bc7234f17a209cc5dcce14903b54ee4dab9002473044022038a05f7d38bcf810dfebb39f1feda5cc187da4cf5d6e56986957ddcccedc75d302203ab67ccf15431b4e2aeeab1582b9a5a7821e7ac4be8ebf512505dbfdc7e094fd0121032168234e0ba465b8cedc10173ea9391725c0f6d9fa517641af87926626a5144abd391400')
        funding_txid2 = funding_tx2.txid()
        #funding_output_value = 5_000_000
        self.assertEqual('c36a6e1cd54df108e69574f70bc9b88dc13beddc70cfad9feb7f8f6593255d4a', funding_txid2)
        wallet.receive_tx_callback(funding_txid2, funding_tx2, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 12_495_000, 0), wallet.get_balance())

        # create new tx (output should be batched with existing!)
        # no new input will be needed. just a new output, and change decreased.
        outputs = [PartialTxOutput.from_address_and_value('tb1qy6xmdj96v5dzt3j08hgc05yk3kltqsnmw4r6ry', 2_500_000)]
        coins = wallet.get_spendable_coins(domain=None)
        tx = wallet.make_unsigned_transaction(coins=coins, outputs=outputs, fee=20000)
        tx.set_rbf(True)
        tx.locktime = 1325499
        tx.version = 1
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100910100000001c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff03a025260000000000160014268db6c8ba651a25c64f3dd187d0968dbeb0427ba02526000000000017a9145a71fc1a7a98ddd67be935ade1600981c0d066f98720fd4b0000000000160014f0fe5c1867a174a12e70165e728a072619455ed5bb391400000100fda20101000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb3914002206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a90398000000800000000000000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a9039800000080010000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        wallet.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet.is_mine(wallet.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(tx.txid(), tx_copy.txid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())
        self.assertEqual('01000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff03a025260000000000160014268db6c8ba651a25c64f3dd187d0968dbeb0427ba02526000000000017a9145a71fc1a7a98ddd67be935ade1600981c0d066f98720fd4b0000000000160014f0fe5c1867a174a12e70165e728a072619455ed50247304402206add1d6fc8b5fc6fd1bbf50d06fe432e65b16a9d715dbfe7f2d26473f48a128302207983d8db3508e3b953e6e26581d2bbba5a7ca0ff0dd07361de60977dc61ed1580121028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c5bb391400',
                         str(tx_copy))
        self.assertEqual('21112d35fa08b9577bfe46405ad17720d0fa85bcefab0b0a1cffe79b9d6167c4', tx_copy.txid())
        self.assertEqual('d49ffdaa832a35d88f3f43bcfb08306347c2342200098f450e41ccb289b26db3', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 9_980_000, 0), wallet.get_balance())

        # create new tx (output should be batched with existing!)
        # new input will be needed!
        outputs = [PartialTxOutput.from_address_and_value('2NCVwbmEpvaXKHpXUGJfJr9iB5vtRN3vcut', 6_000_000)]
        coins = wallet.get_spendable_coins(domain=None)
        tx = wallet.make_unsigned_transaction(coins=coins, outputs=outputs, fee=100_000)
        tx.set_rbf(True)
        tx.locktime = 1325499
        tx.version = 1
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100da0100000002c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff4a5d2593658f7feb9fadcf70dced3bc18db8c90bf77495e608f14dd51c6e6ac30100000000fdffffff04a025260000000000160014268db6c8ba651a25c64f3dd187d0968dbeb0427ba02526000000000017a9145a71fc1a7a98ddd67be935ade1600981c0d066f98760823b0000000000160014f0fe5c1867a174a12e70165e728a072619455ed5808d5b000000000017a914d332f2f63019da6f2d23ee77bbe30eed7739790587bb391400000100fda20101000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb3914002206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a90398000000800000000000000000000100f601000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520000000017160014ba9ca815474a674ff1efb3fc82cf0f3460de8c57fdffffff0230390f000000000017a9148b59abaca8215c0d4b18cbbf715550aa2b50c85b87404b4c000000000016001483c3bc7234f17a209cc5dcce14903b54ee4dab9002473044022038a05f7d38bcf810dfebb39f1feda5cc187da4cf5d6e56986957ddcccedc75d302203ab67ccf15431b4e2aeeab1582b9a5a7821e7ac4be8ebf512505dbfdc7e094fd0121032168234e0ba465b8cedc10173ea9391725c0f6d9fa517641af87926626a5144abd391400220602a6ff1ffc189b4776b78e20edca969cc45da3e610cc0cc79925604be43fee469f10e8a90398000000800000000001000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a903980000008001000000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        wallet.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(2, len(tx.inputs()))
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet.is_mine(wallet.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(tx.txid(), tx_copy.txid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())
        self.assertEqual('01000000000102c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff4a5d2593658f7feb9fadcf70dced3bc18db8c90bf77495e608f14dd51c6e6ac30100000000fdffffff04a025260000000000160014268db6c8ba651a25c64f3dd187d0968dbeb0427ba02526000000000017a9145a71fc1a7a98ddd67be935ade1600981c0d066f98760823b0000000000160014f0fe5c1867a174a12e70165e728a072619455ed5808d5b000000000017a914d332f2f63019da6f2d23ee77bbe30eed7739790587024730440220730ac17af4ac14f008ee5d0a7be524d8ca344afc19b548faa9ac8c21a216df81022010d9cc878402103c1dd6b06e97e7910a23b7ec88251627f47ed1d5a8d741beba0121028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c50247304402201005fc1e9091ac36d98b60c1c8b65aada0d4fe4da438d69b3262028644005cfc02207353c987be9e33d1e8702689960df76ac28adacc2f9093d731bc56c9578c5458012102a6ff1ffc189b4776b78e20edca969cc45da3e610cc0cc79925604be43fee469fbb391400',
                         str(tx_copy))
        self.assertEqual('88791bcd352b50592a5521c15595972b14b5d6be165be2df0e57ea19e588c025', tx_copy.txid())
        self.assertEqual('7c5e5bff601e5467036b574b41090681a86de403867dd2b14097920b95e392ed', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 3_900_000, 0), wallet.get_balance())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_cpfp_p2wpkh(self, mock_save_db):
        wallet = self.create_standard_wallet_from_seed('frost repair depend effort salon ring foam oak cancel receive save usage')

        # bootstrap wallet
        funding_tx = Transaction('01000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520000000017160014ba9ca815474a674ff1efb3fc82cf0f3460de8c57fdffffff0230390f000000000017a9148b59abaca8215c0d4b18cbbf715550aa2b50c85b87404b4c000000000016001483c3bc7234f17a209cc5dcce14903b54ee4dab9002473044022038a05f7d38bcf810dfebb39f1feda5cc187da4cf5d6e56986957ddcccedc75d302203ab67ccf15431b4e2aeeab1582b9a5a7821e7ac4be8ebf512505dbfdc7e094fd0121032168234e0ba465b8cedc10173ea9391725c0f6d9fa517641af87926626a5144abd391400')
        funding_txid = funding_tx.txid()
        funding_output_value = 5000000
        self.assertEqual('c36a6e1cd54df108e69574f70bc9b88dc13beddc70cfad9feb7f8f6593255d4a', funding_txid)
        wallet.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # cpfp tx
        tx = wallet.cpfp(funding_tx, fee=50000)
        tx.set_rbf(True)
        tx.locktime = 1325501
        tx.version = 1
        wallet.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        tx_copy = tx_from_any(tx.serialize())

        self.assertEqual(tx.txid(), tx_copy.txid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())
        self.assertEqual('010000000001014a5d2593658f7feb9fadcf70dced3bc18db8c90bf77495e608f14dd51c6e6ac30100000000fdffffff01f0874b0000000000160014f0fe5c1867a174a12e70165e728a072619455ed502473044022029314c8fb5e05dcd6e94d26f7d96bd9824290977bdc0602b2ef1faf8aa7da53c022003c0477a2b45f05ec4e06e4669a9c3a9e8d9ad0ab78ed85a37b93064c5358e9a012102a6ff1ffc189b4776b78e20edca969cc45da3e610cc0cc79925604be43fee469fbd391400',
                         str(tx_copy))
        self.assertEqual('6bb0490b29b65c7292f6bb1715982fe4474417b4fbdcf8a4675a0994ce12d156', tx_copy.txid())
        self.assertEqual('ce94905afcb396d7bc6de28e4d102dcefc85224abae7df16399b2789f5596db8', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, funding_output_value - 50000, 0), wallet.get_balance())

    def test_sweep_p2pk(self):

        class NetworkMock:
            relay_fee = 1000
            async def listunspent_for_scripthash(self, scripthash):
                if scripthash == '460e4fb540b657d775d84ff4955c9b13bd954c2adc26a6b998331343f85b6a45':
                    return [{'tx_hash': 'ac24de8b58e826f60bd7b9ba31670bdfc3e8aedb2f28d0e91599d741569e3429', 'tx_pos': 1, 'height': 1325785, 'value': 1000000}]
                else:
                    return []
            async def get_transaction(self, txid):
                if txid == "ac24de8b58e826f60bd7b9ba31670bdfc3e8aedb2f28d0e91599d741569e3429":
                    return "010000000001021b41471d6af3aa80ebe536dbf4f505a6d46af456131a8e12e1950171959b690e0f00000000fdffffff2ef29833a69863b31e884fc5e6f7b99a23b5601e14f0eb65905faa42fec0776d0000000000fdffffff02f96a070000000000160014e61b989a740056254b5f8061281ac96ca15d35e140420f00000000004341049afa8fb50f52104b381a673c6e4fb7fb54987271d0e948dd9a568bb2af6f9310a7a809ce06e09d1510e5836f20414596232e2c0be63715459fa3cf8e7092af05ac0247304402201fe20012c1c732a6a8f942c4e0feed5ed0bddfb94db736ec3d0c0d38f0f7f46a022021d690e6d2688b90b76002f4c3134981502d666211e85e8a6ca91e78405dfa3801210346fb31136ab48e6c648865264d32004b43643d01f0ba485cffac4bb0b3f739470247304402204a2473ab4b3bfc8e6b1a6b8675dc2c3d115d8c04f5df37f29779dca6d300d9db02205e72ebbccd018c67b86ae4da6b0e6222902a8de85915ed6115330b9328764b370121027a93ffc9444a12d99307318e2e538949072cb35b2aca344b8163795a022414c7d73a1400"
                else:
                    raise Exception("unexpected txid")

        privkeys = ['93NQ7CFbwTPyKDJLXe97jczw33fiLijam2SCZL3Uinz1NSbHrTu', ]
        network = NetworkMock()
        dest_addr = 'tmona1qtuynwzd0d6wptvyqmc6ehkm70zcamxpstvxpnz'
        sweep_coro = sweep(privkeys, network=network, config=self.config, to_address=dest_addr, fee=5000, locktime=1325785, tx_version=1)
        loop = asyncio.get_event_loop()
        tx = loop.run_until_complete(sweep_coro)

        tx_copy = tx_from_any(tx.serialize())
        self.assertEqual('010000000129349e5641d79915e9d0282fdbaee8c3df0b6731bab9d70bf626e8588bde24ac01000000484730440220631ba847b49184781ad0162b9c3ea777abe436b361dabbf7032a81f62e80d5c202200ee882e8c45e89d71bee47f81a2b0b32085137502fec7d019684a708af8ff7f501feffffff01b82e0f00000000001600145f093709af6e9c15b080de359bdb7e78b1dd9830d93a1400',
                         str(tx_copy))
        self.assertEqual('ce4b25302f659eda839ffc9d2d52a2547f7220ad3a02bc1c06a645b34fecd2a9', tx_copy.txid())
        self.assertEqual('ce4b25302f659eda839ffc9d2d52a2547f7220ad3a02bc1c06a645b34fecd2a9', tx_copy.wtxid())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_coinjoin_between_two_p2wpkh_electrum_seeds(self, mock_save_db):
        wallet1 = WalletIntegrityHelper.create_standard_wallet(
            keystore.from_seed('humor argue expand gain goat shiver remove morning security casual leopard degree', ''),
            gap_limit=2,
            config=self.config
        )
        wallet2 = WalletIntegrityHelper.create_standard_wallet(
            keystore.from_seed('couple fade lift useless text thank badge act august roof drastic violin', ''),
            gap_limit=2,
            config=self.config
        )

        # bootstrap wallet1
        funding_tx = Transaction('0200000000010162ecbac2f0c8662f53505d9410fdc56c84c5642ddbd3358d9a27d564e26731130200000000fdffffff02c0d8a70000000000160014aba1c9faecc3f8882e641583e8734a3f9d01b15ab89ed5000000000016001470afbd97b2dc351bd167f714e294b2fd3b60aedf02483045022100c93449989510e279eb14a0193d5c262ae93034b81376a1f6be259c6080d3ba5d0220536ab394f7c20f301d7ec2ef11be6e7b6d492053dce56458931c1b54218ec0fd012103b8f5a11df8e68cf335848e83a41fdad3c7413dc42148248a3799b58c93919ca010851800')
        funding_txid = funding_tx.txid()
        self.assertEqual('d8f8186379085cffc9a3fd747e7a7527435db974d1e2941f52f063be8e4fbdd5', funding_txid)
        wallet1.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # bootstrap wallet2
        funding_tx = Transaction('02000000000101d5bd4f8ebe63f0521f94e2d174b95d4327757a7e74fda3c9ff5c08796318f8d80100000000fdffffff025066350000000000160014e3aa82aa2e754507d5585c0b6db06cc0cb4927b7a037a000000000001600140719d12228c61cab793ecd659c09cfe565a845c302483045022100f42e27519bd2379c22951c16b038fa6d49164fe6802854f2fdc7ee87fe31a8bc02204ea71e9324781b44bf7fea2f318caf3bedc5b497cbd1b4313fa71f833500bcb7012103a7853e1ee02a1629c8e870ec694a1420aeb98e6f5d071815257028f62d6f784169851800')
        funding_txid = funding_tx.txid()
        self.assertEqual('934f26a72c840293f06c37dc10a358df056dfe245cdf072ae836977c0abc46e5', funding_txid)
        wallet2.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # wallet1 creates tx1, with output back to himself
        outputs = [PartialTxOutput.from_address_and_value("tmona1qhye4wfp26kn0l7ynpn5a4hvt539xc3zfeap5he", 10_000_000)]
        tx1 = wallet1.mktx(outputs=outputs, fee=5000, tx_version=2, rbf=True, sign=False)
        tx1.locktime = 1607022
        partial_tx1 = tx1.serialize_as_bytes().hex()
        self.assertEqual("70736274ff0100710200000001d5bd4f8ebe63f0521f94e2d174b95d4327757a7e74fda3c9ff5c08796318f8d80000000000feffffff02b82e0f0000000000160014250dbabd5761d7e0773d6147699938dd08ec2eb88096980000000000160014b93357242ad5a6fff8930ce9dadd8ba44a6c44496e851800000100df0200000000010162ecbac2f0c8662f53505d9410fdc56c84c5642ddbd3358d9a27d564e26731130200000000fdffffff02c0d8a70000000000160014aba1c9faecc3f8882e641583e8734a3f9d01b15ab89ed5000000000016001470afbd97b2dc351bd167f714e294b2fd3b60aedf02483045022100c93449989510e279eb14a0193d5c262ae93034b81376a1f6be259c6080d3ba5d0220536ab394f7c20f301d7ec2ef11be6e7b6d492053dce56458931c1b54218ec0fd012103b8f5a11df8e68cf335848e83a41fdad3c7413dc42148248a3799b58c93919ca01085180022060205e8db1b1906219782fadb18e763c0874a3118a17ce931e01707cbde194e041510775087560000008000000000000000000022020240ef5d2efee3b04b313a254df1b13a0b155451581e73943b21f3346bf6e1ba351077508756000000800100000000000000002202024a410b1212e88573561887b2bc38c90c074e4be425b9f3d971a9207825d9d3c8107750875600000080000000000100000000",
                         partial_tx1)
        tx1.prepare_for_export_for_coinjoin()
        partial_tx1 = tx1.serialize_as_bytes().hex()
        self.assertEqual("70736274ff0100710200000001d5bd4f8ebe63f0521f94e2d174b95d4327757a7e74fda3c9ff5c08796318f8d80000000000feffffff02b82e0f0000000000160014250dbabd5761d7e0773d6147699938dd08ec2eb88096980000000000160014b93357242ad5a6fff8930ce9dadd8ba44a6c44496e851800000100df0200000000010162ecbac2f0c8662f53505d9410fdc56c84c5642ddbd3358d9a27d564e26731130200000000fdffffff02c0d8a70000000000160014aba1c9faecc3f8882e641583e8734a3f9d01b15ab89ed5000000000016001470afbd97b2dc351bd167f714e294b2fd3b60aedf02483045022100c93449989510e279eb14a0193d5c262ae93034b81376a1f6be259c6080d3ba5d0220536ab394f7c20f301d7ec2ef11be6e7b6d492053dce56458931c1b54218ec0fd012103b8f5a11df8e68cf335848e83a41fdad3c7413dc42148248a3799b58c93919ca010851800000000",
                         partial_tx1)

        # wallet2 creates tx2, with output back to himself
        outputs = [PartialTxOutput.from_address_and_value("tmona1qufnj5k2rrsnpjq7fg6d2pq3q9um6skdyjhgqgn", 10_000_000)]
        tx2 = wallet2.mktx(outputs=outputs, fee=5000, tx_version=2, rbf=True, sign=False)
        tx2.locktime = 1607023
        partial_tx2 = tx2.serialize_as_bytes().hex()
        self.assertEqual("70736274ff0100710200000001e546bc0a7c9736e82a07df5c24fe6d05df58a310dc376cf09302842ca7264f930100000000feffffff02988d07000000000016001453675a59be834aa6d139c3ebea56646a9b160c4c8096980000000000160014e2672a59431c261903c9469aa082202f37a859a46f851800000100df02000000000101d5bd4f8ebe63f0521f94e2d174b95d4327757a7e74fda3c9ff5c08796318f8d80100000000fdffffff025066350000000000160014e3aa82aa2e754507d5585c0b6db06cc0cb4927b7a037a000000000001600140719d12228c61cab793ecd659c09cfe565a845c302483045022100f42e27519bd2379c22951c16b038fa6d49164fe6802854f2fdc7ee87fe31a8bc02204ea71e9324781b44bf7fea2f318caf3bedc5b497cbd1b4313fa71f833500bcb7012103a7853e1ee02a1629c8e870ec694a1420aeb98e6f5d071815257028f62d6f784169851800220602275b4fba18bb34e5198a9cfb3e940306658839079b3bda50d504a9cf2bae36f41067f36697000000800000000001000000002202036e4d0a5fb845b2f1c3c868c2ce7212b155b73e91c05be1b7a77c48830831ba4f1067f366970000008001000000000000000022020200062fdea2b0a056b17fa6b91dd87f5b5d838fe1ee84d636a5022f9a340eebcc1067f3669700000080000000000000000000",
                         partial_tx2)

        # wallet2 gets raw partial tx1, merges it into his own tx2
        tx2.join_with_other_psbt(tx_from_any(partial_tx1))
        partial_tx2 = tx2.serialize_as_bytes().hex()
        self.assertEqual("70736274ff0100d80200000002e546bc0a7c9736e82a07df5c24fe6d05df58a310dc376cf09302842ca7264f930100000000feffffffd5bd4f8ebe63f0521f94e2d174b95d4327757a7e74fda3c9ff5c08796318f8d80000000000feffffff04988d07000000000016001453675a59be834aa6d139c3ebea56646a9b160c4cb82e0f0000000000160014250dbabd5761d7e0773d6147699938dd08ec2eb88096980000000000160014b93357242ad5a6fff8930ce9dadd8ba44a6c44498096980000000000160014e2672a59431c261903c9469aa082202f37a859a46f851800000100df02000000000101d5bd4f8ebe63f0521f94e2d174b95d4327757a7e74fda3c9ff5c08796318f8d80100000000fdffffff025066350000000000160014e3aa82aa2e754507d5585c0b6db06cc0cb4927b7a037a000000000001600140719d12228c61cab793ecd659c09cfe565a845c302483045022100f42e27519bd2379c22951c16b038fa6d49164fe6802854f2fdc7ee87fe31a8bc02204ea71e9324781b44bf7fea2f318caf3bedc5b497cbd1b4313fa71f833500bcb7012103a7853e1ee02a1629c8e870ec694a1420aeb98e6f5d071815257028f62d6f784169851800220602275b4fba18bb34e5198a9cfb3e940306658839079b3bda50d504a9cf2bae36f41067f36697000000800000000001000000000100df0200000000010162ecbac2f0c8662f53505d9410fdc56c84c5642ddbd3358d9a27d564e26731130200000000fdffffff02c0d8a70000000000160014aba1c9faecc3f8882e641583e8734a3f9d01b15ab89ed5000000000016001470afbd97b2dc351bd167f714e294b2fd3b60aedf02483045022100c93449989510e279eb14a0193d5c262ae93034b81376a1f6be259c6080d3ba5d0220536ab394f7c20f301d7ec2ef11be6e7b6d492053dce56458931c1b54218ec0fd012103b8f5a11df8e68cf335848e83a41fdad3c7413dc42148248a3799b58c93919ca010851800002202036e4d0a5fb845b2f1c3c868c2ce7212b155b73e91c05be1b7a77c48830831ba4f1067f3669700000080010000000000000000000022020200062fdea2b0a056b17fa6b91dd87f5b5d838fe1ee84d636a5022f9a340eebcc1067f3669700000080000000000000000000",
                         partial_tx2)
        tx2.prepare_for_export_for_coinjoin()
        partial_tx2 = tx2.serialize_as_bytes().hex()
        self.assertEqual("70736274ff0100d80200000002e546bc0a7c9736e82a07df5c24fe6d05df58a310dc376cf09302842ca7264f930100000000feffffffd5bd4f8ebe63f0521f94e2d174b95d4327757a7e74fda3c9ff5c08796318f8d80000000000feffffff04988d07000000000016001453675a59be834aa6d139c3ebea56646a9b160c4cb82e0f0000000000160014250dbabd5761d7e0773d6147699938dd08ec2eb88096980000000000160014b93357242ad5a6fff8930ce9dadd8ba44a6c44498096980000000000160014e2672a59431c261903c9469aa082202f37a859a46f851800000100df02000000000101d5bd4f8ebe63f0521f94e2d174b95d4327757a7e74fda3c9ff5c08796318f8d80100000000fdffffff025066350000000000160014e3aa82aa2e754507d5585c0b6db06cc0cb4927b7a037a000000000001600140719d12228c61cab793ecd659c09cfe565a845c302483045022100f42e27519bd2379c22951c16b038fa6d49164fe6802854f2fdc7ee87fe31a8bc02204ea71e9324781b44bf7fea2f318caf3bedc5b497cbd1b4313fa71f833500bcb7012103a7853e1ee02a1629c8e870ec694a1420aeb98e6f5d071815257028f62d6f784169851800000100df0200000000010162ecbac2f0c8662f53505d9410fdc56c84c5642ddbd3358d9a27d564e26731130200000000fdffffff02c0d8a70000000000160014aba1c9faecc3f8882e641583e8734a3f9d01b15ab89ed5000000000016001470afbd97b2dc351bd167f714e294b2fd3b60aedf02483045022100c93449989510e279eb14a0193d5c262ae93034b81376a1f6be259c6080d3ba5d0220536ab394f7c20f301d7ec2ef11be6e7b6d492053dce56458931c1b54218ec0fd012103b8f5a11df8e68cf335848e83a41fdad3c7413dc42148248a3799b58c93919ca0108518000000000000",
                         partial_tx2)

        # wallet2 signs
        wallet2.sign_transaction(tx2, password=None)
        partial_tx2 = tx2.serialize_as_bytes().hex()
        self.assertEqual("70736274ff0100d80200000002e546bc0a7c9736e82a07df5c24fe6d05df58a310dc376cf09302842ca7264f930100000000feffffffd5bd4f8ebe63f0521f94e2d174b95d4327757a7e74fda3c9ff5c08796318f8d80000000000feffffff04988d07000000000016001453675a59be834aa6d139c3ebea56646a9b160c4cb82e0f0000000000160014250dbabd5761d7e0773d6147699938dd08ec2eb88096980000000000160014b93357242ad5a6fff8930ce9dadd8ba44a6c44498096980000000000160014e2672a59431c261903c9469aa082202f37a859a46f851800000100df02000000000101d5bd4f8ebe63f0521f94e2d174b95d4327757a7e74fda3c9ff5c08796318f8d80100000000fdffffff025066350000000000160014e3aa82aa2e754507d5585c0b6db06cc0cb4927b7a037a000000000001600140719d12228c61cab793ecd659c09cfe565a845c302483045022100f42e27519bd2379c22951c16b038fa6d49164fe6802854f2fdc7ee87fe31a8bc02204ea71e9324781b44bf7fea2f318caf3bedc5b497cbd1b4313fa71f833500bcb7012103a7853e1ee02a1629c8e870ec694a1420aeb98e6f5d071815257028f62d6f78416985180001070001086b0247304402200b74f0de381354b30effbbfada36bcec5cbc2de4eac4d477b96330cce536cba20220390b0eb2492ff6adfe127426b5cd526fb6c0269cf21f5990573a354da30a3fe3012102275b4fba18bb34e5198a9cfb3e940306658839079b3bda50d504a9cf2bae36f4000100df0200000000010162ecbac2f0c8662f53505d9410fdc56c84c5642ddbd3358d9a27d564e26731130200000000fdffffff02c0d8a70000000000160014aba1c9faecc3f8882e641583e8734a3f9d01b15ab89ed5000000000016001470afbd97b2dc351bd167f714e294b2fd3b60aedf02483045022100c93449989510e279eb14a0193d5c262ae93034b81376a1f6be259c6080d3ba5d0220536ab394f7c20f301d7ec2ef11be6e7b6d492053dce56458931c1b54218ec0fd012103b8f5a11df8e68cf335848e83a41fdad3c7413dc42148248a3799b58c93919ca010851800002202036e4d0a5fb845b2f1c3c868c2ce7212b155b73e91c05be1b7a77c48830831ba4f1067f3669700000080010000000000000000000022020200062fdea2b0a056b17fa6b91dd87f5b5d838fe1ee84d636a5022f9a340eebcc1067f3669700000080000000000000000000",
                         partial_tx2)
        tx2.prepare_for_export_for_coinjoin()
        partial_tx2 = tx2.serialize_as_bytes().hex()
        self.assertEqual("70736274ff0100d80200000002e546bc0a7c9736e82a07df5c24fe6d05df58a310dc376cf09302842ca7264f930100000000feffffffd5bd4f8ebe63f0521f94e2d174b95d4327757a7e74fda3c9ff5c08796318f8d80000000000feffffff04988d07000000000016001453675a59be834aa6d139c3ebea56646a9b160c4cb82e0f0000000000160014250dbabd5761d7e0773d6147699938dd08ec2eb88096980000000000160014b93357242ad5a6fff8930ce9dadd8ba44a6c44498096980000000000160014e2672a59431c261903c9469aa082202f37a859a46f851800000100df02000000000101d5bd4f8ebe63f0521f94e2d174b95d4327757a7e74fda3c9ff5c08796318f8d80100000000fdffffff025066350000000000160014e3aa82aa2e754507d5585c0b6db06cc0cb4927b7a037a000000000001600140719d12228c61cab793ecd659c09cfe565a845c302483045022100f42e27519bd2379c22951c16b038fa6d49164fe6802854f2fdc7ee87fe31a8bc02204ea71e9324781b44bf7fea2f318caf3bedc5b497cbd1b4313fa71f833500bcb7012103a7853e1ee02a1629c8e870ec694a1420aeb98e6f5d071815257028f62d6f78416985180001070001086b0247304402200b74f0de381354b30effbbfada36bcec5cbc2de4eac4d477b96330cce536cba20220390b0eb2492ff6adfe127426b5cd526fb6c0269cf21f5990573a354da30a3fe3012102275b4fba18bb34e5198a9cfb3e940306658839079b3bda50d504a9cf2bae36f4000100df0200000000010162ecbac2f0c8662f53505d9410fdc56c84c5642ddbd3358d9a27d564e26731130200000000fdffffff02c0d8a70000000000160014aba1c9faecc3f8882e641583e8734a3f9d01b15ab89ed5000000000016001470afbd97b2dc351bd167f714e294b2fd3b60aedf02483045022100c93449989510e279eb14a0193d5c262ae93034b81376a1f6be259c6080d3ba5d0220536ab394f7c20f301d7ec2ef11be6e7b6d492053dce56458931c1b54218ec0fd012103b8f5a11df8e68cf335848e83a41fdad3c7413dc42148248a3799b58c93919ca0108518000000000000",
                         partial_tx2)

        # wallet1 gets raw partial tx2, and signs
        tx2 = tx_from_any(partial_tx2)
        wallet1.sign_transaction(tx2, password=None)
        tx = tx_from_any(tx2.serialize_as_bytes().hex())  # simulates moving partial txn between cosigners

        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual("02000000000102e546bc0a7c9736e82a07df5c24fe6d05df58a310dc376cf09302842ca7264f930100000000feffffffd5bd4f8ebe63f0521f94e2d174b95d4327757a7e74fda3c9ff5c08796318f8d80000000000feffffff04988d07000000000016001453675a59be834aa6d139c3ebea56646a9b160c4cb82e0f0000000000160014250dbabd5761d7e0773d6147699938dd08ec2eb88096980000000000160014b93357242ad5a6fff8930ce9dadd8ba44a6c44498096980000000000160014e2672a59431c261903c9469aa082202f37a859a40247304402200b74f0de381354b30effbbfada36bcec5cbc2de4eac4d477b96330cce536cba20220390b0eb2492ff6adfe127426b5cd526fb6c0269cf21f5990573a354da30a3fe3012102275b4fba18bb34e5198a9cfb3e940306658839079b3bda50d504a9cf2bae36f4024730440220187bcc891f198e16a273025d593ac25961c8f86fe9b9c9391bf06c151fa9e6e702200f705a8c72945a976132bf75577a9b5e163ac8537fa5417f069f4311ba79faa601210205e8db1b1906219782fadb18e763c0874a3118a17ce931e01707cbde194e04156f851800",
                         str(tx))
        self.assertEqual('f7d120da95a43c4fb38764d48ec1bc7c95c55038ba0cf9be0282a7c5f95ed183', tx.txid())
        self.assertEqual('fb1bffae0e6a4ea2ff3e3cc174f5573d50d67f032253d88693d41c9c43709a61', tx.wtxid())

        wallet1.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        wallet2.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)

        # wallet level checks
        self.assertEqual((0, 10995000, 0), wallet1.get_balance())
        self.assertEqual((0, 10495000, 0), wallet2.get_balance())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_standard_wallet_cannot_sign_multisig_input_even_if_cosigner(self, mock_save_db):
        """Just because our keystore recognizes the pubkeys in a txin, if the prevout does not belong to the wallet,
        then wallet.is_mine and wallet.can_sign should return False (e.g. multisig input for single-sig wallet).
        (see issue #5948)
        """
        wallet_2of2 = WalletIntegrityHelper.create_multisig_wallet(
            [
                # seed: frost repair depend effort salon ring foam oak cancel receive save usage
                # convert_xkey(wallet.get_master_public_key(), "p2wsh")
                keystore.from_xpub('Vpub5gqF73Wpbp9ThwEgZKHLjBDthsatXjajYvrN8CVnkdBYeTR1M1sfZFQqQ5wpKHGhnwKhzgMhaWrtgKG2LthCzxjd653KqKVUAw7UrwYnbKQ'),
                # seed: bitter grass shiver impose acquire brush forget axis eager alone wine silver
                # convert_xkey(wallet.get_master_public_key(), "p2wsh")
                keystore.from_xpub('Vpub5gSKXzxK7FeKNi2WPNW9iuA48SbJRZvKFBwtgucpegMWPdohQPeK2DoR6XFtC7BBLsHhfWDAPKaiecqJ7jTzYSfeg5YATowmPcgCWxARabT')
            ],
            '2of2', gap_limit=2,
            config=self.config
        )
        wallet_frost = self.create_standard_wallet_from_seed('frost repair depend effort salon ring foam oak cancel receive save usage')

        # bootstrap wallet_2of2
        funding_tx = Transaction('020000000001018ed0132bb5f35d097572081524cd5e847c895e765b93d5af46b8a8bef621244a0100000000fdffffff0220a1070000000000220020302981db44eb5dad0dab3987134a985b360ae2227a7e7a10cfe8cffd23bacdc9b07912000000000016001442b423aab2aa803f957084832b10359beaa2469002473044022065c5e28900b4706487223357e8539e176552e3560e2081ac18de7c26e8e420ba02202755c7fc8177ff502634104c090e3fd4c4252bfa8566d4eb6605bb9e236e7839012103b63bbf85ec9e5e312e4d7a2b45e690f48b916a442e787a47a6092d6c052394c5966a1900')
        funding_txid = funding_tx.txid()
        self.assertEqual('0c2f5981981a6cb69d7b729feceb55be7962b16dc41e8aaf64e5203f7cb604d0', funding_txid)
        wallet_2of2.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1qpsecvrqaraqhtw5pdm233kfdet25svpmnq8rp8', 100_000)]
        coins = wallet_2of2.get_spendable_coins(domain=None)
        tx = wallet_2of2.make_unsigned_transaction(coins=coins, outputs=outputs, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1665628

        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff01007d0200000001d004b67c3f20e564af8a1ec46db16279be55ebec9f727b9db66c1a9881592f0c0000000000fdffffff02a0860100000000001600140c33860c1d1f4175ba816ed518d92dcad548303bf806060000000000220020eb428a0bdeca2c1b3731aedb81c0518456875a99755d177d204d6516d8f6b3075c6a1900000100ea020000000001018ed0132bb5f35d097572081524cd5e847c895e765b93d5af46b8a8bef621244a0100000000fdffffff0220a1070000000000220020302981db44eb5dad0dab3987134a985b360ae2227a7e7a10cfe8cffd23bacdc9b07912000000000016001442b423aab2aa803f957084832b10359beaa2469002473044022065c5e28900b4706487223357e8539e176552e3560e2081ac18de7c26e8e420ba02202755c7fc8177ff502634104c090e3fd4c4252bfa8566d4eb6605bb9e236e7839012103b63bbf85ec9e5e312e4d7a2b45e690f48b916a442e787a47a6092d6c052394c5966a19000105475221028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c521030faee9b4a25b7db82023ca989192712cdd4cb53d3d9338591c7909e581ae1c0c52ae2206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a903980000008000000000000000002206030faee9b4a25b7db82023ca989192712cdd4cb53d3d9338591c7909e581ae1c0c10b2e35a7d0000008000000000000000000000010147522102105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea21028584e789e39f41391b2f27852ca18abec06a5411c21be350fed61eec7120de5352ae220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a903980000008001000000000000002202028584e789e39f41391b2f27852ca18abec06a5411c21be350fed61eec7120de5310b2e35a7d00000080010000000000000000",
                         partial_tx)
        tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners

        self.assertFalse(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual('373c1d63519976edeeb8a7186c5d4c4c89e5d4957af6575c9e1cc7dc3804bbda', tx.txid())

        self.assertEqual('tmona1qxq5crk6yadw66rdt8xr3xj5ctvmq4c3z0fl85yx0ar8l6ga6ehyshqct66', tx.inputs()[0].address)
        self.assertEqual('tmona1qpsecvrqaraqhtw5pdm233kfdet25svpmnq8rp8',                     tx.outputs()[0].address)
        self.assertEqual('tmona1qadpg5z77egkpkde34mdcrsz3s3tgwk5ew4w3wlfqf4j3dk8kkvrssy2z2r', tx.outputs()[1].address)

        # check that wallet_frost does not mistakenly think tx is related to it in any way
        tx.add_info_from_wallet(wallet_frost)
        self.assertFalse(wallet_frost.can_sign(tx))
        self.assertFalse(any([wallet_frost.is_mine(txin.address) for txin in tx.inputs()]))
        self.assertFalse(any([wallet_frost.is_mine(txout.address) for txout in tx.outputs()]))

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_dscancel(self, mock_save_db):
        self.maxDiff = None
        config = SimpleConfig({'electrum_path': self.electrum_path})
        config.set_key('coin_chooser_output_rounding', False)

        for simulate_moving_txs in (False, True):
            with self.subTest(msg="_dscancel_when_all_outputs_are_ismine", simulate_moving_txs=simulate_moving_txs):
                self._dscancel_when_all_outputs_are_ismine(
                    simulate_moving_txs=simulate_moving_txs,
                    config=config)
            with self.subTest(msg="_dscancel_p2wpkh_when_there_is_a_change_address", simulate_moving_txs=simulate_moving_txs):
                self._dscancel_p2wpkh_when_there_is_a_change_address(
                    simulate_moving_txs=simulate_moving_txs,
                    config=config)
            with self.subTest(msg="_dscancel_when_user_sends_max", simulate_moving_txs=simulate_moving_txs):
                self._dscancel_when_user_sends_max(
                    simulate_moving_txs=simulate_moving_txs,
                    config=config)
            with self.subTest(msg="_dscancel_when_not_all_inputs_are_ismine", simulate_moving_txs=simulate_moving_txs):
                self._dscancel_when_not_all_inputs_are_ismine(
                    simulate_moving_txs=simulate_moving_txs,
                    config=config)

    def _dscancel_when_all_outputs_are_ismine(self, *, simulate_moving_txs, config):
        wallet = self.create_standard_wallet_from_seed('fold object utility erase deputy output stadium feed stereo usage modify bean',
                                                       config=config)

        # bootstrap wallet
        funding_tx = Transaction('010000000001011f4db0ecd81f4388db316bc16efb4e9daf874cf4950d54ecb4c0fb372433d68500000000171600143d57fd9e88ef0e70cddb0d8b75ef86698cab0d44fdffffff0280969800000000001976a91472e34cebab371967b038ce41d0e8fa1fb983795e88ac86a0ae020000000017a9149188bc82bdcae077060ebb4f02201b73c806edc887024830450221008e0725d531bd7dee4d8d38a0f921d7b1213e5b16c05312a80464ecc2b649598d0220596d309cf66d5f47cb3df558dbb43c5023a7796a80f5a88b023287e45a4db6b9012102c34d61ceafa8c216f01e05707672354f8119334610f7933a3f80dd7fb6290296bd391400')
        funding_txid = funding_tx.txid()
        funding_output_value = 10000000
        self.assertEqual('03052739fcfa2ead5f8e57e26021b0c2c546bcd3d74c6e708d5046dc58d90762', funding_txid)
        wallet.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create tx
        outputs = [PartialTxOutput.from_address_and_value('miFLSDZBXUo4on8PGhTRTAufUn4mP61uoH', '!')]
        coins = wallet.get_spendable_coins(domain=None)
        tx = wallet.make_unsigned_transaction(coins=coins, outputs=outputs, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1859362
        tx.version = 2
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff01005502000000016207d958dc46508d706e4cd7d3bc46c5c2b02160e2578e5fad2efafc392705030000000000fdffffff01f8829800000000001976a9141df43441a3a3ee563e560d3ddc7e07cc9f9c3cdb88ac225f1c00000100fa010000000001011f4db0ecd81f4388db316bc16efb4e9daf874cf4950d54ecb4c0fb372433d68500000000171600143d57fd9e88ef0e70cddb0d8b75ef86698cab0d44fdffffff0280969800000000001976a91472e34cebab371967b038ce41d0e8fa1fb983795e88ac86a0ae020000000017a9149188bc82bdcae077060ebb4f02201b73c806edc887024830450221008e0725d531bd7dee4d8d38a0f921d7b1213e5b16c05312a80464ecc2b649598d0220596d309cf66d5f47cb3df558dbb43c5023a7796a80f5a88b023287e45a4db6b9012102c34d61ceafa8c216f01e05707672354f8119334610f7933a3f80dd7fb6290296bd391400220602a807c07bd7975211078e916bdda061d97e98d59a3631a804aada2f9a3f5b587a0c8296e571000000000000000000220202a7536f0bfbc60c5a8e86e2b9df26431fc062f9f454016dbc26f2467e0bc98b3f0c8296e571000000000100000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        wallet.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertFalse(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet.is_mine(wallet.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(tx.txid(), tx_copy.txid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())
        self.assertEqual('02000000016207d958dc46508d706e4cd7d3bc46c5c2b02160e2578e5fad2efafc39270503000000006a47304402200c1ad6499cfd7a808c2463e211e0aaf503a571c85b679e69af215b76f05ad74d022066fccfec30164ad62686734ec3eca024e33e935b1bf30a98df85d87f01ba1b5f012102a807c07bd7975211078e916bdda061d97e98d59a3631a804aada2f9a3f5b587afdffffff01f8829800000000001976a9141df43441a3a3ee563e560d3ddc7e07cc9f9c3cdb88ac225f1c00',
                         str(tx_copy))
        self.assertEqual('200d5173d3113e9cec7a63e885b64836245572d93b6dda4035f3ed44341b6277', tx_copy.txid())
        self.assertEqual('200d5173d3113e9cec7a63e885b64836245572d93b6dda4035f3ed44341b6277', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, funding_output_value - 5000, 0), wallet.get_balance())

        # cancel tx
        tx_details = wallet.get_tx_info(tx_from_any(tx.serialize()))
        self.assertFalse(tx_details.can_dscancel)

    def _dscancel_p2wpkh_when_there_is_a_change_address(self, *, simulate_moving_txs, config):
        wallet = self.create_standard_wallet_from_seed('frost repair depend effort salon ring foam oak cancel receive save usage',
                                                       config=config)

        # bootstrap wallet
        funding_tx = Transaction('01000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb391400')
        funding_txid = funding_tx.txid()
        funding_output_value = 10000000
        self.assertEqual('52e669a20a26c8b3df5b41e5e6309b18bcde8e1ad7ea17a18f63b6dc6c8becc0', funding_txid)
        wallet.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create tx
        outputs = [PartialTxOutput.from_address_and_value('2N1VTMMFb91SH9SNRAkT7z8otP5eZEct4KL', 2500000)]
        coins = wallet.get_spendable_coins(domain=None)
        tx = wallet.make_unsigned_transaction(coins=coins, outputs=outputs, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325499
        tx.version = 1
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100720100000001c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff02a02526000000000017a9145a71fc1a7a98ddd67be935ade1600981c0d066f987585d720000000000160014f0fe5c1867a174a12e70165e728a072619455ed5bb391400000100fda20101000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb3914002206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a903980000008000000000000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a9039800000080010000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        wallet.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet.is_mine(wallet.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(tx.txid(), tx_copy.txid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())
        self.assertEqual('01000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff02a02526000000000017a9145a71fc1a7a98ddd67be935ade1600981c0d066f987585d720000000000160014f0fe5c1867a174a12e70165e728a072619455ed50247304402205442705e988abe74bf391b293bb1b886674284a92ed0788c33024f9336d60aef022013a93049d3bed693254cd31a704d70bb988a36750f0b74d0a5b4d9e29c54ca9d0121028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c5bb391400',
                         str(tx_copy))
        self.assertEqual('b019bbad45a46ed25365e46e4cae6428fb12ae425977eb93011ffb294cb4977e', tx_copy.txid())
        self.assertEqual('ba87313e2b3b42f1cc478843d4d53c72d6e06f6c66ac8cfbe2a59cdac2fd532d', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, funding_output_value - 2500000 - 5000, 0), wallet.get_balance())

        # cancel tx TODO monacoin is ok?
        tx_details = wallet.get_tx_info(tx_from_any(tx.serialize()))
        self.assertTrue(tx_details.can_dscancel)
        tx = wallet.dscancel(tx=tx_from_any(tx.serialize()), new_fee_rate=70.0)
        tx.locktime = 1859397
        tx.version = 2
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100520200000001c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff010058980000000000160014f0fe5c1867a174a12e70165e728a072619455ed5455f1c00000100fda20101000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb3914002206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a9039800000080000000000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a9039800000080010000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertFalse(tx.is_complete())

        wallet.sign_transaction(tx, password=None)
        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        tx_copy = tx_from_any(tx.serialize())
        self.assertEqual('02000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff010058980000000000160014f0fe5c1867a174a12e70165e728a072619455ed502473044022037ef63671bd3d439901e0ee3a56a561641b4773478579367b090890651238204022057a745f15b7fd71c6cbc1f93c43c642a2426f6703dd2af61c4e64bced59b859d0121028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c5455f1c00',
                         str(tx_copy))
        self.assertEqual('255e050c2112e78c15bb68cf2d6c5b4c07ae56f615be5216dd6fff989abb6c9d', tx_copy.txid())
        self.assertEqual('1835abcab6fd7470193360a8df71fc19c3871b69f94294ea3b957b3a63aa6be1', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 9984000, 0), wallet.get_balance())

    def _dscancel_when_user_sends_max(self, *, simulate_moving_txs, config):
        wallet = self.create_standard_wallet_from_seed('frost repair depend effort salon ring foam oak cancel receive save usage',
                                                       config=config)

        # bootstrap wallet
        funding_tx = Transaction('01000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb391400')
        funding_txid = funding_tx.txid()
        self.assertEqual('52e669a20a26c8b3df5b41e5e6309b18bcde8e1ad7ea17a18f63b6dc6c8becc0', funding_txid)
        wallet.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create tx
        outputs = [PartialTxOutput.from_address_and_value('2N1VTMMFb91SH9SNRAkT7z8otP5eZEct4KL', '!')]
        coins = wallet.get_spendable_coins(domain=None)
        tx = wallet.make_unsigned_transaction(coins=coins, outputs=outputs, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325499
        tx.version = 1
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100530100000001c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff01f88298000000000017a9145a71fc1a7a98ddd67be935ade1600981c0d066f987bb391400000100fda20101000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb3914002206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a903980000008000000000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        wallet.sign_transaction(tx, password=None)

        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        tx_copy = tx_from_any(tx.serialize())
        self.assertTrue(wallet.is_mine(wallet.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(tx.txid(), tx_copy.txid())
        self.assertEqual(tx.wtxid(), tx_copy.wtxid())
        self.assertEqual('01000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff01f88298000000000017a9145a71fc1a7a98ddd67be935ade1600981c0d066f987024730440220520ab41536d5d0fac8ad44e6aa4a8258a266121bab1eb6599f1ee86bbc65719d02205944c2fb765fca4753a850beadac49f5305c6722410c347c08cec4d90e3eb4430121028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c5bb391400',
                         str(tx_copy))
        self.assertEqual('dc4b622f3225f00edb886011fa02b74630cdbc24cebdd3210d5ea3b68bef5cc9', tx_copy.txid())
        self.assertEqual('a00340ee8c90673e05f2cf368601b6bba6a7f0513bd974feb218a326e39b1874', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 0, 0), wallet.get_balance())

        # cancel tx TODO monacoin is ok?
        tx_details = wallet.get_tx_info(tx_from_any(tx.serialize()))
        self.assertTrue(tx_details.can_dscancel)
        tx = wallet.dscancel(tx=tx_from_any(tx.serialize()), new_fee_rate=70.0)
        tx.locktime = 1859455
        tx.version = 2
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100520200000001c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff010058980000000000160014f0fe5c1867a174a12e70165e728a072619455ed57f5f1c00000100fda20101000000000102acd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba020000001716001455c7f5e0631d8e6f5f05dddb9f676cec48845532fdffffffd146691ef6a207b682b13da5f2388b1f0d2a2022c8cfb8dc27b65434ec9ec8f701000000171600147b3be8a7ceaf15f57d7df2a3d216bc3c259e3225fdffffff02a9875b000000000017a914ea5a99f83e71d1c1dfc5d0370e9755567fe4a141878096980000000000160014d4ca56fcbad98fb4dcafdc573a75d6a6fffb09b702483045022100dde1ba0c9a2862a65791b8d91295a6603207fb79635935a67890506c214dd96d022046c6616642ef5971103c1db07ac014e63fa3b0e15c5729eacdd3e77fcb7d2086012103a72410f185401bb5b10aaa30989c272b554dc6d53bda6da85a76f662723421af024730440220033d0be8f74e782fbcec2b396647c7715d2356076b442423f23552b617062312022063c95cafdc6d52ccf55c8ee0f9ceb0f57afb41ea9076eb74fe633f59c50c6377012103b96a4954d834fbcfb2bbf8cf7de7dc2b28bc3d661c1557d1fd1db1bfc123a94abb3914002206028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c510e8a9039800000080000000000000000000220202105dd9133f33cbd4e50443ef9af428c0be61f097f8942aaa916f50b530125aea10e8a9039800000080010000000000000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertFalse(tx.is_complete())

        wallet.sign_transaction(tx, password=None)
        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        tx_copy = tx_from_any(tx.serialize())
        self.assertEqual('02000000000101c0ec8b6cdcb6638fa117ead71a8edebc189b30e6e5415bdfb3c8260aa269e6520100000000fdffffff010058980000000000160014f0fe5c1867a174a12e70165e728a072619455ed502473044022018048f493337f0284fba259471daefd55accf4b3077ccd9c79665c46b5d77f0902206fa55a4ebfbb06b6d03f8638f90ceccace2c7ba5ddc0d7496a13945e7e729a030121028d4c44ca36d2c4bff3813df8d5d3c0278357521ecb892cd694c473c03970e4c57f5f1c00',
                         str(tx_copy))
        self.assertEqual('35e427707955cb3b371861493dddfd763f54f1396a2993471011107c1cd2359a', tx_copy.txid())
        self.assertEqual('983c0def8b4c30bc256151788fb1f0f2fa42651cb2005479694adb4fa76673c2', tx_copy.wtxid())

        wallet.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual((0, 9984000, 0), wallet.get_balance())

    def _dscancel_when_not_all_inputs_are_ismine(self, *, simulate_moving_txs, config):
        class NetworkMock:
            relay_fee = 1000
            async def get_transaction(self, txid, timeout=None):
                if txid == "597098f9077cd2a7bf5bb2a03c9ae5fcd9d1f07c0891cb42cbb129cf9eaf57fd":
                    return "02000000000102a5883f3de780d260e6f26cf85144403c7744a65a44cd38f9ff45aecadf010c540000000000fdffffffbdeb0175b1c51c96843d1952f7e1c49c1703717d7d020048d4de0a8eed94dad50000000000fdffffff03b2a00700000000001600140cd6c9f8ce0aa73d77fcf7f156c74f5cbec6906bb2a00700000000001600146435504ddc95e6019a90bb7dfc7ca81a88a8633106d790000000000016001444bd3017ee214370abf683abaa7f6204c9f40210024730440220652a04a2a301d9a031a034f3ae48174e204e17acf7bfc27f0dcab14243f73e2202207b29e964c434dfb2c515232d36566a40dccd4dd93ccb7fd15260ecbda10f0d9801210231994e564a0530068d17a9b0f85bec58d1352517a2861ea99e5b3070d2c5dbda02473044022072186473874919019da0e3d92b6e0aa4f88cba448ed5434615e5a3c8e2b7c42a02203ec05cef66960d5bc45d0f3d25675190cf8035b11a05ed4b719fd9c3a894899b012102f5fdca8c4e30ba0a1babf9cf9ebe62519b08aead351c349ed1ffc8316c24f542d7f61c00"
                else:
                    raise Exception("unexpected txid")
            def has_internet_connection(self):
                return True
            def run_from_another_thread(self, coro, *, timeout=None):
                loop, stop_loop, loop_thread = create_and_start_event_loop()
                fut = asyncio.run_coroutine_threadsafe(coro, loop)
                try:
                    return fut.result(timeout)
                finally:
                    loop.call_soon_threadsafe(stop_loop.set_result, 1)
                    loop_thread.join(timeout=1)
            def get_local_height(self):
                return 0
            def blockchain(self):
                class BlockchainMock:
                    def is_tip_stale(self):
                        return True
                return BlockchainMock()

        wallet = self.create_standard_wallet_from_seed('mix total present junior leader live state athlete mistake crack wall valve',
                                                       config=config)
        wallet.network = NetworkMock()

        # bootstrap wallet
        funding_tx = Transaction('02000000000101a5883f3de780d260e6f26cf85144403c7744a65a44cd38f9ff45aecadf010c540100000000fdffffff0220a1070000000000160014db44724ac632ae47ee5765954d64796dd5fec72708de3c000000000016001424b32aadb42a89016c4de8f11741c3b29b15f21c02473044022045cc6c1cc875cbb0c0d8fe323dc1de9716e49ed5659741b0fb3dd9a196894066022077c242640071d12ec5763c5870f482a4823d8713e4bd14353dd621ed29a7f96d012102aea8d439a0f79d8b58e8d7bda83009f587e1f3da350adaa484329bf47cd03465fef61c00')
        funding_txid = funding_tx.txid()
        self.assertEqual('08557327673db61cc921e1a30826608599b86457836be3021105c13940d9a9a3', funding_txid)
        wallet.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        orig_rbf_tx = Transaction('02000000000102a3a9d94039c1051102e36b835764b89985602608a3e121c91cb63d67277355080000000000fdfffffffd57af9ecf29b1cb42cb91087cf0d1d9fce59a3ca0b25bbfa7d27c07f99870590200000000fdffffff03b2a00700000000001600145dc80fd43eb70fd21a6c4446e3ce043df94f100cb2a00700000000001600147db4ab480b7d2218fba561ff304178f4afcbc972be358900000000001600149d91f0053172fab394d277ae27e9fa5c5a49210902473044022003999f03be8b9e299b2cd3bc7bce05e273d5d9ce24fc47af8754f26a7a13e13f022004e668499a67061789f6ebd2932c969ece74417ae3f2307bf696428bbed4fe36012102a1c9b25b37aa31ccbb2d72caaffce81ec8253020a74017d92bbfc14a832fc9cb0247304402207121358a66c0e716e2ba2be928076736261c691b4fbf89ea8d255449a4f5837b022042cadf9fe1b4f3c03ede3cef6783b42f0ba319f2e0273b624009cd023488c4c1012103a5ba95fb1e0043428ed70680fc17db254b3f701dfccf91e48090aa17c1b7ea40fef61c00')
        orig_rbf_txid = orig_rbf_tx.txid()
        self.assertEqual('6057690010ddac93a371629e1f41866400623e13a9cd336d280fc3239086a983', orig_rbf_txid)
        wallet.receive_tx_callback(orig_rbf_txid, orig_rbf_tx, TX_HEIGHT_UNCONFIRMED)

        # bump tx
        tx = wallet.dscancel(tx=tx_from_any(orig_rbf_tx.serialize()), new_fee_rate=70)
        tx.locktime = 1898278
        tx.version = 2
        if simulate_moving_txs:
            partial_tx = tx.serialize_as_bytes().hex()
            self.assertEqual("70736274ff0100520200000001a3a9d94039c1051102e36b835764b89985602608a3e121c91cb63d67277355080000000000fdffffff0124750700000000001600145dc80fd43eb70fd21a6c4446e3ce043df94f100c26f71c00000100de02000000000101a5883f3de780d260e6f26cf85144403c7744a65a44cd38f9ff45aecadf010c540100000000fdffffff0220a1070000000000160014db44724ac632ae47ee5765954d64796dd5fec72708de3c000000000016001424b32aadb42a89016c4de8f11741c3b29b15f21c02473044022045cc6c1cc875cbb0c0d8fe323dc1de9716e49ed5659741b0fb3dd9a196894066022077c242640071d12ec5763c5870f482a4823d8713e4bd14353dd621ed29a7f96d012102aea8d439a0f79d8b58e8d7bda83009f587e1f3da350adaa484329bf47cd03465fef61c00220602a1c9b25b37aa31ccbb2d72caaffce81ec8253020a74017d92bbfc14a832fc9cb109c9fff980000008000000000000000000022020353becea8bbfe746452e5d2fa2e0688013e43ca6409c8e30b6cc99e7625ff2265109c9fff9800000080000000000100000000",
                             partial_tx)
            tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertFalse(tx.is_complete())

        wallet.sign_transaction(tx, password=None)
        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        tx_copy = tx_from_any(tx.serialize())
        self.assertEqual('02000000000101a3a9d94039c1051102e36b835764b89985602608a3e121c91cb63d67277355080000000000fdffffff0124750700000000001600145dc80fd43eb70fd21a6c4446e3ce043df94f100c02473044022072e4e256547887230acee6bd30c9f3bb115db6b04e27e106d21bbf5fa650ff4c02206fa894adcf11025bdfdba42906979a2308d241ae1ffcee621266a0cdf9f6049e012102a1c9b25b37aa31ccbb2d72caaffce81ec8253020a74017d92bbfc14a832fc9cb26f71c00',
                         str(tx_copy))
        self.assertEqual('cb37b3fc06e2010ca30da4091ad814e56d58e6f2f3d8e3df2430d8a5d06ce643', tx_copy.txid())


class TestWalletOfflineSigning(TestCaseForTestnet):
    maxDiff = None
    def setUp(self):
        super().setUp()
        self.config = SimpleConfig({'electrum_path': self.electrum_path})

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_offline_old_electrum_seed_online_mpk(self, mock_save_db):
        wallet_offline = WalletIntegrityHelper.create_standard_wallet(
            keystore.from_seed('alone body father children lead goodbye phone twist exist grass kick join', '', False),
            gap_limit=4,
            config=self.config
        )
        wallet_online = WalletIntegrityHelper.create_standard_wallet(
            keystore.from_master_key('cd805ed20aec61c7a8b409c121c6ba60a9221f46d20edbc2be83ebd91460e97937cd7d782e77c1cb08364c6bc1c98bc040fdad53f22f29f7d3a85c8e51f9c875'),
            gap_limit=4,
            config=self.config
        )

        # bootstrap wallet_online
        funding_tx = Transaction('01000000000101161115f8d8110001aa0883989487f9c7a2faf4451038e4305c7594c5236cbb490100000000fdffffff0338117a0000000000160014c1d7b2ded7017cbde837aab36c1e7b2a3952a57800127a00000000001600143e2ab71fc9738ce16fbe6b3b1c210a68c12db84180969800000000001976a91424b64d981d621c227716b51479faf33019371f4688ac0247304402207a5efc6d970f6a5fdcd1933f68b353b4bf2904743f9f1dc3e9177d8754074baf02202eed707e661493bc450357f12cd7a8b8c610c7cb32ded10516c2933a2ba4346a01210287dce03f594fd889726b13a12970237992a0094a5c9f4eebcca6d50d454b39e9ff121600')
        funding_txid = funding_tx.txid()
        self.assertEqual('3b9e0581602f4656cb04633dac13662bc62d9f5191caa15cc901dcc76e430856', funding_txid)
        wallet_online.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create unsigned tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1qtuynwzd0d6wptvyqmc6ehkm70zcamxpstvxpnz', 2500000)]
        tx = wallet_online.mktx(outputs=outputs, password=None, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1446655
        tx.version = 1

        self.assertFalse(tx.is_complete())
        self.assertFalse(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff01007401000000015608436ec7dc01c95ca1ca91519f2dc62b6613ac3d6304cb56462f6081059e3b0200000000fdffffff02a0252600000000001600145f093709af6e9c15b080de359bdb7e78b1dd9830585d7200000000001976a914b6a6bbbc4cf9da58786a8acc58291e218d52130688acff121600000100fd000101000000000101161115f8d8110001aa0883989487f9c7a2faf4451038e4305c7594c5236cbb490100000000fdffffff0338117a0000000000160014c1d7b2ded7017cbde837aab36c1e7b2a3952a57800127a00000000001600143e2ab71fc9738ce16fbe6b3b1c210a68c12db84180969800000000001976a91424b64d981d621c227716b51479faf33019371f4688ac0247304402207a5efc6d970f6a5fdcd1933f68b353b4bf2904743f9f1dc3e9177d8754074baf02202eed707e661493bc450357f12cd7a8b8c610c7cb32ded10516c2933a2ba4346a01210287dce03f594fd889726b13a12970237992a0094a5c9f4eebcca6d50d454b39e9ff121600420604e79eb77f2f3f989f5e9d090bc0af50afeb0d5bd6ec916f2022c5629ed022e84a87584ef647d69f073ea314a0f0c110ebe24ad64bc1922a10819ea264fc3f35f50c343ddcab000000000100000000004202048e2004ca581afcc54a5d9b3b47affdf48b3f89e16d5bd96774fc0f167f2d7873bac6264e3d1f1bb96f64d1530a54e026e0bd7d674151d146fba582e79f4ef5e80c343ddcab010000000000000000",
                         partial_tx)
        tx_copy = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertTrue(wallet_online.is_mine(wallet_online.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(tx.txid(), tx_copy.txid())

        # sign tx
        tx = wallet_offline.sign_transaction(tx_copy, password=None)
        self.assertTrue(tx.is_complete())
        self.assertFalse(tx.is_segwit())
        self.assertEqual('01000000015608436ec7dc01c95ca1ca91519f2dc62b6613ac3d6304cb56462f6081059e3b020000008a473044022040e8b75981d12cab21db007fbb7c6ec795059217199b205e23d213f796f4847b0220122b322b3382aa0763d9cf365c25da094f3e6d88f0e05efedca3aff2bb22c3d0014104e79eb77f2f3f989f5e9d090bc0af50afeb0d5bd6ec916f2022c5629ed022e84a87584ef647d69f073ea314a0f0c110ebe24ad64bc1922a10819ea264fc3f35f5fdffffff02a0252600000000001600145f093709af6e9c15b080de359bdb7e78b1dd9830585d7200000000001976a914b6a6bbbc4cf9da58786a8acc58291e218d52130688acff121600',
                         str(tx))
        self.assertEqual('109fc9506735e2fdc7a3c246dc2b387295e3c60314b7739b0413bc16e7581eba', tx.txid())
        self.assertEqual('109fc9506735e2fdc7a3c246dc2b387295e3c60314b7739b0413bc16e7581eba', tx.wtxid())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_offline_xprv_online_xpub_p2pkh(self, mock_save_db):
        wallet_offline = WalletIntegrityHelper.create_standard_wallet(
            # bip39: "qwe", der: m/44'/1'/0'
            keystore.from_xprv('tprv8gfKwjuAaqtHgqxMh1tosAQ28XvBMkcY5NeFRA3pZMpz6MR4H4YZ3MJM4fvNPnRKeXR1Td2vQGgjorNXfo94WvT5CYDsPAqjHxSn436G1Eu'),
            gap_limit=4,
            config=self.config
        )
        wallet_online = WalletIntegrityHelper.create_standard_wallet(
            keystore.from_xpub('tpubDDMN69wQjDZxaJz9afZQGa48hZS7X5oSegF2hg67yddNvqfpuTN9DqvDEp7YyVf7AzXnqBqHdLhzTAStHvsoMDDb8WoJQzNrcHgDJHVYgQF'),
            gap_limit=4,
            config=self.config
        )

        # bootstrap wallet_online
        funding_tx = Transaction('01000000000116e9c9dac2651672316aab3b9553257b6942c5f762c5d795776d9cfa504f183c000000000000fdffffff8085019852fada9da84b58dcf753d292dde314a19f5a5527f6588fa2566142130000000000fdffffffa4154a48db20ce538b28722a89c6b578bd5b5d60d6d7b52323976339e39405230000000000fdffffff0b5ef43f843a96364aebd708e25ea1bdcf2c7df7d0d995560b8b1be5f357b64f0100000000fdffffffd41dfe1199c76fdb3f20e9947ea31136d032d9da48c5e45d85c8f440e2351a510100000000fdffffff5bd015d17e4a1837b01c24ebb4a6b394e3da96a85442bd7dc6abddfbf16f20510000000000fdffffff13a3e7f80b1bd46e38f2abc9e2f335c18a4b0af1778133c7f1c3caae9504345c0200000000fdffffffdf4fc1ab21bca69d18544ddb10a913cd952dbc730ab3d236dd9471445ff405680100000000fdffffffe0424d78a30d5e60ac6b26e2274d7d6e7c6b78fe0b49bdc3ac4dd2147c9535750100000000fdffffff7ab6dd6b3c0d44b0fef0fdc9ab0ad6eee23eef799eee29c005d52bc4461998760000000000fdffffff48a77e5053a21acdf4f235ce00c82c9bc1704700f54d217f6a30704711b9737d0000000000fdffffff86918b39c1d9bb6f34d9b082182f73cedd15504331164dc2b186e95c568ccb870000000000fdffffff15a847356cbb44be67f345965bb3f2589e2fec1c9a0ada21fd28225dcc602e8f0100000000fdffffff9a2875297f81dfd3b77426d63f621db350c270cc28c634ad86b9969ee33ac6960000000000fdffffffd6eeb1d1833e00967083d1ab86fa5a2e44355bd613d9277135240fe6f60148a20100000000fdffffffd8a6e5a9b68a65ff88220ca33e36faf6f826ae8c5c8a13fe818a5e63828b68a40100000000fdffffff73aab8471f82092e45ed1b1afeffdb49ea1ec74ce4853f971812f6a72a7e85aa0000000000fdffffffacd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba0000000000fdffffff1eddd5e13bef1aba1ff151762b5860837daa9b39db1eae8ea8227c81a5a1c8ba0000000000fdffffff67a096ff7c343d39e96929798097f6d7a61156bbdb905fbe534ba36f273271d40100000000fdffffff109a671eb7daf6dcd07c0ceff99f2de65864ab36d64fb3a890bab951569adeee0100000000fdffffff4f1bdc64da8056d08f79db7f5348d1de55946e57aa7c8279499c703889b6e0fd0200000000fdffffff042f280000000000001600149c756aa33f4f89418b33872a973274b5445c727b80969800000000001600146c540c1c9f546004539f45318b8d9f4d7b4857ef80969800000000001976a91422a6daa4a7b695c8a2dd104d47c5dc73d655c96f88ac809698000000000017a914a6885437e0762013facbda93894202a0fe86e35f8702473044022075ef5f04d7a63347064938e15a0c74277a79e5c9d32a26e39e8a517a44d565cc022015246790fb5b29c9bf3eded1b95699b1635bcfc6d521886fddf1135ba1b988ec012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe02473044022061aa9b0d9649ffd7259bc54b35f678565dbbe11507d348dd8885522eaf1fa70c02202cc79de09e8e63e8d57fde6ef66c079ddac4d9828e1936a9db833d4c142615c3012103a8f58fc1f5625f18293403104874f2d38c9279f777e512570e4199c7d292b81b0247304402207744dc1ab0bf77c081b58540c4321d090c0a24a32742a361aa55ad86f0c7c24e02201a9b0dd78b63b495ab5a0b5b161c54cb085d70683c90e188bb4dc2e41e142f6601210361fb354f8259abfcbfbdda36b7cb4c3b05a3ca3d68dd391fd8376e920d93870d0247304402204803e423c321acc6c12cb0ebf196d2906842fdfed6de977cc78277052ee5f15002200634670c1dc25e6b1787a65d3e09c8e6bb0340238d90b9d98887e8fd53944e080121031104c60d027123bf8676bcaefaa66c001a0d3d379dc4a9492a567a9e1004452d02473044022050e4b5348d30011a22b6ae8b43921d29249d88ea71b1fbaa2d9c22dfdef58b7002201c5d5e143aa8835454f61b0742226ebf8cd466bcc2cdcb1f77b92e473d3b13190121030496b9d49aa8efece4f619876c60a77d2c0dc846390ecdc5d9acbfa1bb3128760247304402204d6a9b986e1a0e3473e8aef84b3eb7052442a76dfd7631e35377f141496a55490220131ab342853c01e31f111436f8461e28bc95883b871ca0e01b5f57146e79d7bb012103262ffbc88e25296056a3c65c880e3686297e07f360e6b80f1219d65b0900e84e02483045022100c8ffacf92efa1dddef7e858a241af7a80adcc2489bcc325195970733b1f35fac022076f40c26023a228041a9665c5290b9918d06f03b716e4d8f6d47e79121c7eb37012102d9ba7e02d7cd7dd24302f823b3114c99da21549c663f72440dc87e8ba412120902483045022100b55545d84e43d001bbc10a981f184e7d3b98a7ed6689863716cab053b3655a2f0220537eb76a695fbe86bf020b4b6f7ae93b506d778bbd0885f0a61067616a2c8bce0121034a57f2fa2c32c9246691f6a922fb1ebdf1468792bae7eff253a99fc9f2a5023902483045022100f1d4408463dbfe257f9f778d5e9c8cdb97c8b1d395dbd2e180bc08cad306492c022002a024e19e1a406eaa24467f033659de09ab58822987281e28bb6359288337bd012103e91daa18d924eea62011ce596e15b6d683975cf724ea5bf69a8e2022c26fc12f0247304402204f1e12b923872f396e5e1a3aa94b0b2e86b4ce448f4349a017631db26d7dff8a022069899a05de2ad2bbd8e0202c56ab1025a7db9a4998eea70744e3c367d2a7eb71012103b0eee86792dbef1d4a49bc4ea32d197c8c15d27e6e0c5c33e58e409e26d4a39a0247304402201787dacdb92e0df6ad90226649f0e8321287d0bd8fddc536a297dd19b5fc103e022001fe89300a76e5b46d0e3f7e39e0ee26cc83b71d59a2a5da1dd7b13350cd0c07012103afb1e43d7ec6b7999ef0f1093069e68fe1dfe5d73fc6cfb4f7a5022f7098758c02483045022100acc1212bba0fe4fcc6c3ae5cf8e25f221f140c8444d3c08dfc53a93630ac25da02203f12982847244bd9421ef340293f3a38d2ab5d028af60769e46fcc7d81312e7e012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024830450221009c04934102402949484b21899271c3991c007b783b8efc85a3c3d24641ac7c24022006fb1895ce969d08a2cb29413e1a85427c7e85426f7a185108ca44b5a0328cb301210360248db4c7d7f76fe231998d2967104fee04df8d8da34f10101cc5523e82648c02483045022100b11fe61b393fa5dbe18ab98f65c249345b429b13f69ee2d1b1335725b24a0e73022010960cdc5565cbc81885c8ed95142435d3c202dfa5a3dc5f50f3914c106335ce0121029c878610c34c21381cda12f6f36ab88bf60f5f496c1b82c357b8ac448713e7b50247304402200ca080db069c15bbf98e1d4dff68d0aea51227ff5d17a8cf67ceae464c22bbb0022051e7331c0918cbb71bb2cef29ca62411454508a16180b0fb5df94248890840df0121028f0be0cde43ff047edbda42c91c37152449d69789eb812bb2e148e4f22472c0f0247304402201fefe258938a2c481d5a745ef3aa8d9f8124bbe7f1f8c693e2ddce4ddc9a927c02204049e0060889ede8fda975edf896c03782d71ba53feb51b04f5ae5897d7431dc012103946730b480f52a43218a9edce240e8b234790e21df5e96482703d81c3c19d3f1024730440220126a6a56dbe69af78d156626fc9cf41d6aac0c07b8b5f0f8491f68db5e89cb5002207ee6ed6f2f41da256f3c1e79679a3de6cf34cc08b940b82be14aefe7da031a6b012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024730440220363204a1586d7f13c148295122cbf9ec7939685e3cadab81d6d9e921436d21b7022044626b8c2bd4aa7c167d74bc4e9eb9d0744e29ce0ad906d78e10d6d854f23d170121037fb9c51716739bb4c146857fab5a783372f72a65987d61f3b58c74360f4328dd0247304402207925a4c2a3a6b76e10558717ee28fcb8c6fde161b9dc6382239af9f372ace99902204a58e31ce0b4a4804a42d2224331289311ded2748062c92c8aca769e81417a4c012102e18a8c235b48e41ef98265a8e07fa005d2602b96d585a61ad67168d74e7391cb02483045022100bbfe060479174a8d846b5a897526003eb2220ba307a5fee6e1e8de3e4e8b38fd02206723857301d447f67ac98a5a5c2b80ef6820e98fae213db1720f93d91161803b01210386728e2ac3ecee15f58d0505ee26f86a68f08c702941ffaf2fb7213e5026aea10247304402203a2613ae68f697eb02b5b7d18e3c4236966dac2b3a760e3021197d76e9ad4239022046f9067d3df650fcabbdfd250308c64f90757dec86f0b08813c979a42d06a6ec012102a1d7ee1cb4dc502f899aaafae0a2eb6cbf80d9a1073ae60ddcaabc3b1d1f15df02483045022100ab1bea2cc5388428fd126c7801550208701e21564bd4bd00cfd4407cfafc1acd0220508ee587f080f3c80a5c0b2175b58edd84b755e659e2135b3152044d75ebc4b501210236dd1b7f27a296447d0eb3750e1bdb2d53af50b31a72a45511dc1ec3fe7a684a19391400')
        funding_txid = funding_tx.txid()
        self.assertEqual('98574bc5f6e75769eb0c93d41453cc1dfbd15c14e63cc3c42f37cdbd08858762', funding_txid)
        wallet_online.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create unsigned tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1qtuynwzd0d6wptvyqmc6ehkm70zcamxpstvxpnz', 2500000)]
        tx = wallet_online.mktx(outputs=outputs, password=None, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325340
        tx.version = 1

        self.assertFalse(tx.is_complete())
        self.assertFalse(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))

        orig_tx = tx
        for uses_qr_code in (False, True):
            with self.subTest(msg="uses_qr_code", uses_qr_code=uses_qr_code):
                tx = copy.deepcopy(orig_tx)
                if uses_qr_code:
                    partial_tx = tx.to_qr_data()
                    self.assertEqual("8VXO.MYW+UE2.+5LGGVQP.$087REZNQ8:6*U1CLU+NW7:.T7K04HTV.JW78BXOF$IM*4YYL6LWVSZ4QA0Q-1*8W38XJH833$K5H0:T+8TF$5J+VLN/XS$+5CD.MGA.9FFFBXR-ZIYDQ7YFU40T4HQFHPZQ*WFJ$N87OBL.CEPHQH/C8BOWP-2SYLX:6TXZTUKCOBF:3AMVI.XLS--TYQ6F.:J*7Q0:QO:N:EDCMRP:-Y82O-$CNC0AIOYA$9+X5K8.59JN$P5T00$VDYVOFEXTL816*TKVE$5T+ENQ4RL2XZH/Y3WA96LKCZY5IEKUSDSJTHH+7.Y/DF7.:5/0FEFZBAQAEEZ5Y1+UY5DT9GIJ.AAPB.BNPLZ/17SK$-G52+A",
                                     partial_tx)
                else:
                    partial_tx = tx.serialize_as_bytes().hex()
                    self.assertEqual("70736274ff010074010000000162878508bdcd372fc4c33ce6145cd1fb1dcc5314d4930ceb6957e7f6c54b57980200000000fdffffff02a0252600000000001600145f093709af6e9c15b080de359bdb7e78b1dd9830585d7200000000001976a9149b308d0b3efd4e3469441bc83c3521afde4072b988ac1c391400000100fd4c0d01000000000116e9c9dac2651672316aab3b9553257b6942c5f762c5d795776d9cfa504f183c000000000000fdffffff8085019852fada9da84b58dcf753d292dde314a19f5a5527f6588fa2566142130000000000fdffffffa4154a48db20ce538b28722a89c6b578bd5b5d60d6d7b52323976339e39405230000000000fdffffff0b5ef43f843a96364aebd708e25ea1bdcf2c7df7d0d995560b8b1be5f357b64f0100000000fdffffffd41dfe1199c76fdb3f20e9947ea31136d032d9da48c5e45d85c8f440e2351a510100000000fdffffff5bd015d17e4a1837b01c24ebb4a6b394e3da96a85442bd7dc6abddfbf16f20510000000000fdffffff13a3e7f80b1bd46e38f2abc9e2f335c18a4b0af1778133c7f1c3caae9504345c0200000000fdffffffdf4fc1ab21bca69d18544ddb10a913cd952dbc730ab3d236dd9471445ff405680100000000fdffffffe0424d78a30d5e60ac6b26e2274d7d6e7c6b78fe0b49bdc3ac4dd2147c9535750100000000fdffffff7ab6dd6b3c0d44b0fef0fdc9ab0ad6eee23eef799eee29c005d52bc4461998760000000000fdffffff48a77e5053a21acdf4f235ce00c82c9bc1704700f54d217f6a30704711b9737d0000000000fdffffff86918b39c1d9bb6f34d9b082182f73cedd15504331164dc2b186e95c568ccb870000000000fdffffff15a847356cbb44be67f345965bb3f2589e2fec1c9a0ada21fd28225dcc602e8f0100000000fdffffff9a2875297f81dfd3b77426d63f621db350c270cc28c634ad86b9969ee33ac6960000000000fdffffffd6eeb1d1833e00967083d1ab86fa5a2e44355bd613d9277135240fe6f60148a20100000000fdffffffd8a6e5a9b68a65ff88220ca33e36faf6f826ae8c5c8a13fe818a5e63828b68a40100000000fdffffff73aab8471f82092e45ed1b1afeffdb49ea1ec74ce4853f971812f6a72a7e85aa0000000000fdffffffacd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba0000000000fdffffff1eddd5e13bef1aba1ff151762b5860837daa9b39db1eae8ea8227c81a5a1c8ba0000000000fdffffff67a096ff7c343d39e96929798097f6d7a61156bbdb905fbe534ba36f273271d40100000000fdffffff109a671eb7daf6dcd07c0ceff99f2de65864ab36d64fb3a890bab951569adeee0100000000fdffffff4f1bdc64da8056d08f79db7f5348d1de55946e57aa7c8279499c703889b6e0fd0200000000fdffffff042f280000000000001600149c756aa33f4f89418b33872a973274b5445c727b80969800000000001600146c540c1c9f546004539f45318b8d9f4d7b4857ef80969800000000001976a91422a6daa4a7b695c8a2dd104d47c5dc73d655c96f88ac809698000000000017a914a6885437e0762013facbda93894202a0fe86e35f8702473044022075ef5f04d7a63347064938e15a0c74277a79e5c9d32a26e39e8a517a44d565cc022015246790fb5b29c9bf3eded1b95699b1635bcfc6d521886fddf1135ba1b988ec012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe02473044022061aa9b0d9649ffd7259bc54b35f678565dbbe11507d348dd8885522eaf1fa70c02202cc79de09e8e63e8d57fde6ef66c079ddac4d9828e1936a9db833d4c142615c3012103a8f58fc1f5625f18293403104874f2d38c9279f777e512570e4199c7d292b81b0247304402207744dc1ab0bf77c081b58540c4321d090c0a24a32742a361aa55ad86f0c7c24e02201a9b0dd78b63b495ab5a0b5b161c54cb085d70683c90e188bb4dc2e41e142f6601210361fb354f8259abfcbfbdda36b7cb4c3b05a3ca3d68dd391fd8376e920d93870d0247304402204803e423c321acc6c12cb0ebf196d2906842fdfed6de977cc78277052ee5f15002200634670c1dc25e6b1787a65d3e09c8e6bb0340238d90b9d98887e8fd53944e080121031104c60d027123bf8676bcaefaa66c001a0d3d379dc4a9492a567a9e1004452d02473044022050e4b5348d30011a22b6ae8b43921d29249d88ea71b1fbaa2d9c22dfdef58b7002201c5d5e143aa8835454f61b0742226ebf8cd466bcc2cdcb1f77b92e473d3b13190121030496b9d49aa8efece4f619876c60a77d2c0dc846390ecdc5d9acbfa1bb3128760247304402204d6a9b986e1a0e3473e8aef84b3eb7052442a76dfd7631e35377f141496a55490220131ab342853c01e31f111436f8461e28bc95883b871ca0e01b5f57146e79d7bb012103262ffbc88e25296056a3c65c880e3686297e07f360e6b80f1219d65b0900e84e02483045022100c8ffacf92efa1dddef7e858a241af7a80adcc2489bcc325195970733b1f35fac022076f40c26023a228041a9665c5290b9918d06f03b716e4d8f6d47e79121c7eb37012102d9ba7e02d7cd7dd24302f823b3114c99da21549c663f72440dc87e8ba412120902483045022100b55545d84e43d001bbc10a981f184e7d3b98a7ed6689863716cab053b3655a2f0220537eb76a695fbe86bf020b4b6f7ae93b506d778bbd0885f0a61067616a2c8bce0121034a57f2fa2c32c9246691f6a922fb1ebdf1468792bae7eff253a99fc9f2a5023902483045022100f1d4408463dbfe257f9f778d5e9c8cdb97c8b1d395dbd2e180bc08cad306492c022002a024e19e1a406eaa24467f033659de09ab58822987281e28bb6359288337bd012103e91daa18d924eea62011ce596e15b6d683975cf724ea5bf69a8e2022c26fc12f0247304402204f1e12b923872f396e5e1a3aa94b0b2e86b4ce448f4349a017631db26d7dff8a022069899a05de2ad2bbd8e0202c56ab1025a7db9a4998eea70744e3c367d2a7eb71012103b0eee86792dbef1d4a49bc4ea32d197c8c15d27e6e0c5c33e58e409e26d4a39a0247304402201787dacdb92e0df6ad90226649f0e8321287d0bd8fddc536a297dd19b5fc103e022001fe89300a76e5b46d0e3f7e39e0ee26cc83b71d59a2a5da1dd7b13350cd0c07012103afb1e43d7ec6b7999ef0f1093069e68fe1dfe5d73fc6cfb4f7a5022f7098758c02483045022100acc1212bba0fe4fcc6c3ae5cf8e25f221f140c8444d3c08dfc53a93630ac25da02203f12982847244bd9421ef340293f3a38d2ab5d028af60769e46fcc7d81312e7e012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024830450221009c04934102402949484b21899271c3991c007b783b8efc85a3c3d24641ac7c24022006fb1895ce969d08a2cb29413e1a85427c7e85426f7a185108ca44b5a0328cb301210360248db4c7d7f76fe231998d2967104fee04df8d8da34f10101cc5523e82648c02483045022100b11fe61b393fa5dbe18ab98f65c249345b429b13f69ee2d1b1335725b24a0e73022010960cdc5565cbc81885c8ed95142435d3c202dfa5a3dc5f50f3914c106335ce0121029c878610c34c21381cda12f6f36ab88bf60f5f496c1b82c357b8ac448713e7b50247304402200ca080db069c15bbf98e1d4dff68d0aea51227ff5d17a8cf67ceae464c22bbb0022051e7331c0918cbb71bb2cef29ca62411454508a16180b0fb5df94248890840df0121028f0be0cde43ff047edbda42c91c37152449d69789eb812bb2e148e4f22472c0f0247304402201fefe258938a2c481d5a745ef3aa8d9f8124bbe7f1f8c693e2ddce4ddc9a927c02204049e0060889ede8fda975edf896c03782d71ba53feb51b04f5ae5897d7431dc012103946730b480f52a43218a9edce240e8b234790e21df5e96482703d81c3c19d3f1024730440220126a6a56dbe69af78d156626fc9cf41d6aac0c07b8b5f0f8491f68db5e89cb5002207ee6ed6f2f41da256f3c1e79679a3de6cf34cc08b940b82be14aefe7da031a6b012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024730440220363204a1586d7f13c148295122cbf9ec7939685e3cadab81d6d9e921436d21b7022044626b8c2bd4aa7c167d74bc4e9eb9d0744e29ce0ad906d78e10d6d854f23d170121037fb9c51716739bb4c146857fab5a783372f72a65987d61f3b58c74360f4328dd0247304402207925a4c2a3a6b76e10558717ee28fcb8c6fde161b9dc6382239af9f372ace99902204a58e31ce0b4a4804a42d2224331289311ded2748062c92c8aca769e81417a4c012102e18a8c235b48e41ef98265a8e07fa005d2602b96d585a61ad67168d74e7391cb02483045022100bbfe060479174a8d846b5a897526003eb2220ba307a5fee6e1e8de3e4e8b38fd02206723857301d447f67ac98a5a5c2b80ef6820e98fae213db1720f93d91161803b01210386728e2ac3ecee15f58d0505ee26f86a68f08c702941ffaf2fb7213e5026aea10247304402203a2613ae68f697eb02b5b7d18e3c4236966dac2b3a760e3021197d76e9ad4239022046f9067d3df650fcabbdfd250308c64f90757dec86f0b08813c979a42d06a6ec012102a1d7ee1cb4dc502f899aaafae0a2eb6cbf80d9a1073ae60ddcaabc3b1d1f15df02483045022100ab1bea2cc5388428fd126c7801550208701e21564bd4bd00cfd4407cfafc1acd0220508ee587f080f3c80a5c0b2175b58edd84b755e659e2135b3152044d75ebc4b501210236dd1b7f27a296447d0eb3750e1bdb2d53af50b31a72a45511dc1ec3fe7a684a19391400220602ab053d10eda769fab03ab52ee4f1692730288751369643290a8506e31d1e80f00c233d2ae40000000002000000000022020327295144ffff9943356c2d6625f5e2d6411bab77fd56dce571fda6234324e3d90c233d2ae4010000000000000000",
                                     partial_tx)
                tx_copy = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
                self.assertTrue(wallet_online.is_mine(wallet_online.get_txin_address(tx_copy.inputs()[0])))
                self.assertEqual(tx.txid(), tx_copy.txid())

                # sign tx
                tx = wallet_offline.sign_transaction(tx_copy, password=None)
                self.assertTrue(tx.is_complete())
                self.assertFalse(tx.is_segwit())
                self.assertEqual('389584c974b14c05b2dcc8c5f4384209af1d7f4f094406e8d7d357033a3e821a', tx.txid())
                self.assertEqual('389584c974b14c05b2dcc8c5f4384209af1d7f4f094406e8d7d357033a3e821a', tx.wtxid())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_offline_xprv_online_xpub_p2wpkh_p2sh(self, mock_save_db):
        wallet_offline = WalletIntegrityHelper.create_standard_wallet(
            # bip39: "qwe", der: m/49'/1'/0'
            keystore.from_xprv('uprv8zHHrMQMQ26utWwNJ5MK2SXpB9hbmy7pbPaneii69xT8cZTyFpxQFxkknGWKP8dxBTZhzy7yP6cCnLrRCQjzJDk3G61SjZpxhFQuB2NR8a5'),
            gap_limit=4,
            config=self.config
        )
        wallet_online = WalletIntegrityHelper.create_standard_wallet(
            keystore.from_xpub('upub5DGeFrwFEPfD711qQ6tKPaUYjBY6BRqfxcWPT77hiHz7VMo7oNGeom5EdXoKXEazePyoN3ueJMqHBfp3MwmsaD8k9dFHoa8KGeVXev7Pbg2'),
            gap_limit=4,
            config=self.config
        )

        # bootstrap wallet_online
        funding_tx = Transaction('01000000000116e9c9dac2651672316aab3b9553257b6942c5f762c5d795776d9cfa504f183c000000000000fdffffff8085019852fada9da84b58dcf753d292dde314a19f5a5527f6588fa2566142130000000000fdffffffa4154a48db20ce538b28722a89c6b578bd5b5d60d6d7b52323976339e39405230000000000fdffffff0b5ef43f843a96364aebd708e25ea1bdcf2c7df7d0d995560b8b1be5f357b64f0100000000fdffffffd41dfe1199c76fdb3f20e9947ea31136d032d9da48c5e45d85c8f440e2351a510100000000fdffffff5bd015d17e4a1837b01c24ebb4a6b394e3da96a85442bd7dc6abddfbf16f20510000000000fdffffff13a3e7f80b1bd46e38f2abc9e2f335c18a4b0af1778133c7f1c3caae9504345c0200000000fdffffffdf4fc1ab21bca69d18544ddb10a913cd952dbc730ab3d236dd9471445ff405680100000000fdffffffe0424d78a30d5e60ac6b26e2274d7d6e7c6b78fe0b49bdc3ac4dd2147c9535750100000000fdffffff7ab6dd6b3c0d44b0fef0fdc9ab0ad6eee23eef799eee29c005d52bc4461998760000000000fdffffff48a77e5053a21acdf4f235ce00c82c9bc1704700f54d217f6a30704711b9737d0000000000fdffffff86918b39c1d9bb6f34d9b082182f73cedd15504331164dc2b186e95c568ccb870000000000fdffffff15a847356cbb44be67f345965bb3f2589e2fec1c9a0ada21fd28225dcc602e8f0100000000fdffffff9a2875297f81dfd3b77426d63f621db350c270cc28c634ad86b9969ee33ac6960000000000fdffffffd6eeb1d1833e00967083d1ab86fa5a2e44355bd613d9277135240fe6f60148a20100000000fdffffffd8a6e5a9b68a65ff88220ca33e36faf6f826ae8c5c8a13fe818a5e63828b68a40100000000fdffffff73aab8471f82092e45ed1b1afeffdb49ea1ec74ce4853f971812f6a72a7e85aa0000000000fdffffffacd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba0000000000fdffffff1eddd5e13bef1aba1ff151762b5860837daa9b39db1eae8ea8227c81a5a1c8ba0000000000fdffffff67a096ff7c343d39e96929798097f6d7a61156bbdb905fbe534ba36f273271d40100000000fdffffff109a671eb7daf6dcd07c0ceff99f2de65864ab36d64fb3a890bab951569adeee0100000000fdffffff4f1bdc64da8056d08f79db7f5348d1de55946e57aa7c8279499c703889b6e0fd0200000000fdffffff042f280000000000001600149c756aa33f4f89418b33872a973274b5445c727b80969800000000001600146c540c1c9f546004539f45318b8d9f4d7b4857ef80969800000000001976a91422a6daa4a7b695c8a2dd104d47c5dc73d655c96f88ac809698000000000017a914a6885437e0762013facbda93894202a0fe86e35f8702473044022075ef5f04d7a63347064938e15a0c74277a79e5c9d32a26e39e8a517a44d565cc022015246790fb5b29c9bf3eded1b95699b1635bcfc6d521886fddf1135ba1b988ec012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe02473044022061aa9b0d9649ffd7259bc54b35f678565dbbe11507d348dd8885522eaf1fa70c02202cc79de09e8e63e8d57fde6ef66c079ddac4d9828e1936a9db833d4c142615c3012103a8f58fc1f5625f18293403104874f2d38c9279f777e512570e4199c7d292b81b0247304402207744dc1ab0bf77c081b58540c4321d090c0a24a32742a361aa55ad86f0c7c24e02201a9b0dd78b63b495ab5a0b5b161c54cb085d70683c90e188bb4dc2e41e142f6601210361fb354f8259abfcbfbdda36b7cb4c3b05a3ca3d68dd391fd8376e920d93870d0247304402204803e423c321acc6c12cb0ebf196d2906842fdfed6de977cc78277052ee5f15002200634670c1dc25e6b1787a65d3e09c8e6bb0340238d90b9d98887e8fd53944e080121031104c60d027123bf8676bcaefaa66c001a0d3d379dc4a9492a567a9e1004452d02473044022050e4b5348d30011a22b6ae8b43921d29249d88ea71b1fbaa2d9c22dfdef58b7002201c5d5e143aa8835454f61b0742226ebf8cd466bcc2cdcb1f77b92e473d3b13190121030496b9d49aa8efece4f619876c60a77d2c0dc846390ecdc5d9acbfa1bb3128760247304402204d6a9b986e1a0e3473e8aef84b3eb7052442a76dfd7631e35377f141496a55490220131ab342853c01e31f111436f8461e28bc95883b871ca0e01b5f57146e79d7bb012103262ffbc88e25296056a3c65c880e3686297e07f360e6b80f1219d65b0900e84e02483045022100c8ffacf92efa1dddef7e858a241af7a80adcc2489bcc325195970733b1f35fac022076f40c26023a228041a9665c5290b9918d06f03b716e4d8f6d47e79121c7eb37012102d9ba7e02d7cd7dd24302f823b3114c99da21549c663f72440dc87e8ba412120902483045022100b55545d84e43d001bbc10a981f184e7d3b98a7ed6689863716cab053b3655a2f0220537eb76a695fbe86bf020b4b6f7ae93b506d778bbd0885f0a61067616a2c8bce0121034a57f2fa2c32c9246691f6a922fb1ebdf1468792bae7eff253a99fc9f2a5023902483045022100f1d4408463dbfe257f9f778d5e9c8cdb97c8b1d395dbd2e180bc08cad306492c022002a024e19e1a406eaa24467f033659de09ab58822987281e28bb6359288337bd012103e91daa18d924eea62011ce596e15b6d683975cf724ea5bf69a8e2022c26fc12f0247304402204f1e12b923872f396e5e1a3aa94b0b2e86b4ce448f4349a017631db26d7dff8a022069899a05de2ad2bbd8e0202c56ab1025a7db9a4998eea70744e3c367d2a7eb71012103b0eee86792dbef1d4a49bc4ea32d197c8c15d27e6e0c5c33e58e409e26d4a39a0247304402201787dacdb92e0df6ad90226649f0e8321287d0bd8fddc536a297dd19b5fc103e022001fe89300a76e5b46d0e3f7e39e0ee26cc83b71d59a2a5da1dd7b13350cd0c07012103afb1e43d7ec6b7999ef0f1093069e68fe1dfe5d73fc6cfb4f7a5022f7098758c02483045022100acc1212bba0fe4fcc6c3ae5cf8e25f221f140c8444d3c08dfc53a93630ac25da02203f12982847244bd9421ef340293f3a38d2ab5d028af60769e46fcc7d81312e7e012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024830450221009c04934102402949484b21899271c3991c007b783b8efc85a3c3d24641ac7c24022006fb1895ce969d08a2cb29413e1a85427c7e85426f7a185108ca44b5a0328cb301210360248db4c7d7f76fe231998d2967104fee04df8d8da34f10101cc5523e82648c02483045022100b11fe61b393fa5dbe18ab98f65c249345b429b13f69ee2d1b1335725b24a0e73022010960cdc5565cbc81885c8ed95142435d3c202dfa5a3dc5f50f3914c106335ce0121029c878610c34c21381cda12f6f36ab88bf60f5f496c1b82c357b8ac448713e7b50247304402200ca080db069c15bbf98e1d4dff68d0aea51227ff5d17a8cf67ceae464c22bbb0022051e7331c0918cbb71bb2cef29ca62411454508a16180b0fb5df94248890840df0121028f0be0cde43ff047edbda42c91c37152449d69789eb812bb2e148e4f22472c0f0247304402201fefe258938a2c481d5a745ef3aa8d9f8124bbe7f1f8c693e2ddce4ddc9a927c02204049e0060889ede8fda975edf896c03782d71ba53feb51b04f5ae5897d7431dc012103946730b480f52a43218a9edce240e8b234790e21df5e96482703d81c3c19d3f1024730440220126a6a56dbe69af78d156626fc9cf41d6aac0c07b8b5f0f8491f68db5e89cb5002207ee6ed6f2f41da256f3c1e79679a3de6cf34cc08b940b82be14aefe7da031a6b012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024730440220363204a1586d7f13c148295122cbf9ec7939685e3cadab81d6d9e921436d21b7022044626b8c2bd4aa7c167d74bc4e9eb9d0744e29ce0ad906d78e10d6d854f23d170121037fb9c51716739bb4c146857fab5a783372f72a65987d61f3b58c74360f4328dd0247304402207925a4c2a3a6b76e10558717ee28fcb8c6fde161b9dc6382239af9f372ace99902204a58e31ce0b4a4804a42d2224331289311ded2748062c92c8aca769e81417a4c012102e18a8c235b48e41ef98265a8e07fa005d2602b96d585a61ad67168d74e7391cb02483045022100bbfe060479174a8d846b5a897526003eb2220ba307a5fee6e1e8de3e4e8b38fd02206723857301d447f67ac98a5a5c2b80ef6820e98fae213db1720f93d91161803b01210386728e2ac3ecee15f58d0505ee26f86a68f08c702941ffaf2fb7213e5026aea10247304402203a2613ae68f697eb02b5b7d18e3c4236966dac2b3a760e3021197d76e9ad4239022046f9067d3df650fcabbdfd250308c64f90757dec86f0b08813c979a42d06a6ec012102a1d7ee1cb4dc502f899aaafae0a2eb6cbf80d9a1073ae60ddcaabc3b1d1f15df02483045022100ab1bea2cc5388428fd126c7801550208701e21564bd4bd00cfd4407cfafc1acd0220508ee587f080f3c80a5c0b2175b58edd84b755e659e2135b3152044d75ebc4b501210236dd1b7f27a296447d0eb3750e1bdb2d53af50b31a72a45511dc1ec3fe7a684a19391400')
        funding_txid = funding_tx.txid()
        self.assertEqual('98574bc5f6e75769eb0c93d41453cc1dfbd15c14e63cc3c42f37cdbd08858762', funding_txid)
        wallet_online.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create unsigned tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1qtuynwzd0d6wptvyqmc6ehkm70zcamxpstvxpnz', 2500000)]
        tx = wallet_online.mktx(outputs=outputs, password=None, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325341
        tx.version = 1

        self.assertFalse(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff010072010000000162878508bdcd372fc4c33ce6145cd1fb1dcc5314d4930ceb6957e7f6c54b57980300000000fdffffff02a0252600000000001600145f093709af6e9c15b080de359bdb7e78b1dd9830585d72000000000017a914191e7373ae7b4829532220e8f281f4581ed52638871d391400000100fd4c0d01000000000116e9c9dac2651672316aab3b9553257b6942c5f762c5d795776d9cfa504f183c000000000000fdffffff8085019852fada9da84b58dcf753d292dde314a19f5a5527f6588fa2566142130000000000fdffffffa4154a48db20ce538b28722a89c6b578bd5b5d60d6d7b52323976339e39405230000000000fdffffff0b5ef43f843a96364aebd708e25ea1bdcf2c7df7d0d995560b8b1be5f357b64f0100000000fdffffffd41dfe1199c76fdb3f20e9947ea31136d032d9da48c5e45d85c8f440e2351a510100000000fdffffff5bd015d17e4a1837b01c24ebb4a6b394e3da96a85442bd7dc6abddfbf16f20510000000000fdffffff13a3e7f80b1bd46e38f2abc9e2f335c18a4b0af1778133c7f1c3caae9504345c0200000000fdffffffdf4fc1ab21bca69d18544ddb10a913cd952dbc730ab3d236dd9471445ff405680100000000fdffffffe0424d78a30d5e60ac6b26e2274d7d6e7c6b78fe0b49bdc3ac4dd2147c9535750100000000fdffffff7ab6dd6b3c0d44b0fef0fdc9ab0ad6eee23eef799eee29c005d52bc4461998760000000000fdffffff48a77e5053a21acdf4f235ce00c82c9bc1704700f54d217f6a30704711b9737d0000000000fdffffff86918b39c1d9bb6f34d9b082182f73cedd15504331164dc2b186e95c568ccb870000000000fdffffff15a847356cbb44be67f345965bb3f2589e2fec1c9a0ada21fd28225dcc602e8f0100000000fdffffff9a2875297f81dfd3b77426d63f621db350c270cc28c634ad86b9969ee33ac6960000000000fdffffffd6eeb1d1833e00967083d1ab86fa5a2e44355bd613d9277135240fe6f60148a20100000000fdffffffd8a6e5a9b68a65ff88220ca33e36faf6f826ae8c5c8a13fe818a5e63828b68a40100000000fdffffff73aab8471f82092e45ed1b1afeffdb49ea1ec74ce4853f971812f6a72a7e85aa0000000000fdffffffacd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba0000000000fdffffff1eddd5e13bef1aba1ff151762b5860837daa9b39db1eae8ea8227c81a5a1c8ba0000000000fdffffff67a096ff7c343d39e96929798097f6d7a61156bbdb905fbe534ba36f273271d40100000000fdffffff109a671eb7daf6dcd07c0ceff99f2de65864ab36d64fb3a890bab951569adeee0100000000fdffffff4f1bdc64da8056d08f79db7f5348d1de55946e57aa7c8279499c703889b6e0fd0200000000fdffffff042f280000000000001600149c756aa33f4f89418b33872a973274b5445c727b80969800000000001600146c540c1c9f546004539f45318b8d9f4d7b4857ef80969800000000001976a91422a6daa4a7b695c8a2dd104d47c5dc73d655c96f88ac809698000000000017a914a6885437e0762013facbda93894202a0fe86e35f8702473044022075ef5f04d7a63347064938e15a0c74277a79e5c9d32a26e39e8a517a44d565cc022015246790fb5b29c9bf3eded1b95699b1635bcfc6d521886fddf1135ba1b988ec012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe02473044022061aa9b0d9649ffd7259bc54b35f678565dbbe11507d348dd8885522eaf1fa70c02202cc79de09e8e63e8d57fde6ef66c079ddac4d9828e1936a9db833d4c142615c3012103a8f58fc1f5625f18293403104874f2d38c9279f777e512570e4199c7d292b81b0247304402207744dc1ab0bf77c081b58540c4321d090c0a24a32742a361aa55ad86f0c7c24e02201a9b0dd78b63b495ab5a0b5b161c54cb085d70683c90e188bb4dc2e41e142f6601210361fb354f8259abfcbfbdda36b7cb4c3b05a3ca3d68dd391fd8376e920d93870d0247304402204803e423c321acc6c12cb0ebf196d2906842fdfed6de977cc78277052ee5f15002200634670c1dc25e6b1787a65d3e09c8e6bb0340238d90b9d98887e8fd53944e080121031104c60d027123bf8676bcaefaa66c001a0d3d379dc4a9492a567a9e1004452d02473044022050e4b5348d30011a22b6ae8b43921d29249d88ea71b1fbaa2d9c22dfdef58b7002201c5d5e143aa8835454f61b0742226ebf8cd466bcc2cdcb1f77b92e473d3b13190121030496b9d49aa8efece4f619876c60a77d2c0dc846390ecdc5d9acbfa1bb3128760247304402204d6a9b986e1a0e3473e8aef84b3eb7052442a76dfd7631e35377f141496a55490220131ab342853c01e31f111436f8461e28bc95883b871ca0e01b5f57146e79d7bb012103262ffbc88e25296056a3c65c880e3686297e07f360e6b80f1219d65b0900e84e02483045022100c8ffacf92efa1dddef7e858a241af7a80adcc2489bcc325195970733b1f35fac022076f40c26023a228041a9665c5290b9918d06f03b716e4d8f6d47e79121c7eb37012102d9ba7e02d7cd7dd24302f823b3114c99da21549c663f72440dc87e8ba412120902483045022100b55545d84e43d001bbc10a981f184e7d3b98a7ed6689863716cab053b3655a2f0220537eb76a695fbe86bf020b4b6f7ae93b506d778bbd0885f0a61067616a2c8bce0121034a57f2fa2c32c9246691f6a922fb1ebdf1468792bae7eff253a99fc9f2a5023902483045022100f1d4408463dbfe257f9f778d5e9c8cdb97c8b1d395dbd2e180bc08cad306492c022002a024e19e1a406eaa24467f033659de09ab58822987281e28bb6359288337bd012103e91daa18d924eea62011ce596e15b6d683975cf724ea5bf69a8e2022c26fc12f0247304402204f1e12b923872f396e5e1a3aa94b0b2e86b4ce448f4349a017631db26d7dff8a022069899a05de2ad2bbd8e0202c56ab1025a7db9a4998eea70744e3c367d2a7eb71012103b0eee86792dbef1d4a49bc4ea32d197c8c15d27e6e0c5c33e58e409e26d4a39a0247304402201787dacdb92e0df6ad90226649f0e8321287d0bd8fddc536a297dd19b5fc103e022001fe89300a76e5b46d0e3f7e39e0ee26cc83b71d59a2a5da1dd7b13350cd0c07012103afb1e43d7ec6b7999ef0f1093069e68fe1dfe5d73fc6cfb4f7a5022f7098758c02483045022100acc1212bba0fe4fcc6c3ae5cf8e25f221f140c8444d3c08dfc53a93630ac25da02203f12982847244bd9421ef340293f3a38d2ab5d028af60769e46fcc7d81312e7e012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024830450221009c04934102402949484b21899271c3991c007b783b8efc85a3c3d24641ac7c24022006fb1895ce969d08a2cb29413e1a85427c7e85426f7a185108ca44b5a0328cb301210360248db4c7d7f76fe231998d2967104fee04df8d8da34f10101cc5523e82648c02483045022100b11fe61b393fa5dbe18ab98f65c249345b429b13f69ee2d1b1335725b24a0e73022010960cdc5565cbc81885c8ed95142435d3c202dfa5a3dc5f50f3914c106335ce0121029c878610c34c21381cda12f6f36ab88bf60f5f496c1b82c357b8ac448713e7b50247304402200ca080db069c15bbf98e1d4dff68d0aea51227ff5d17a8cf67ceae464c22bbb0022051e7331c0918cbb71bb2cef29ca62411454508a16180b0fb5df94248890840df0121028f0be0cde43ff047edbda42c91c37152449d69789eb812bb2e148e4f22472c0f0247304402201fefe258938a2c481d5a745ef3aa8d9f8124bbe7f1f8c693e2ddce4ddc9a927c02204049e0060889ede8fda975edf896c03782d71ba53feb51b04f5ae5897d7431dc012103946730b480f52a43218a9edce240e8b234790e21df5e96482703d81c3c19d3f1024730440220126a6a56dbe69af78d156626fc9cf41d6aac0c07b8b5f0f8491f68db5e89cb5002207ee6ed6f2f41da256f3c1e79679a3de6cf34cc08b940b82be14aefe7da031a6b012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024730440220363204a1586d7f13c148295122cbf9ec7939685e3cadab81d6d9e921436d21b7022044626b8c2bd4aa7c167d74bc4e9eb9d0744e29ce0ad906d78e10d6d854f23d170121037fb9c51716739bb4c146857fab5a783372f72a65987d61f3b58c74360f4328dd0247304402207925a4c2a3a6b76e10558717ee28fcb8c6fde161b9dc6382239af9f372ace99902204a58e31ce0b4a4804a42d2224331289311ded2748062c92c8aca769e81417a4c012102e18a8c235b48e41ef98265a8e07fa005d2602b96d585a61ad67168d74e7391cb02483045022100bbfe060479174a8d846b5a897526003eb2220ba307a5fee6e1e8de3e4e8b38fd02206723857301d447f67ac98a5a5c2b80ef6820e98fae213db1720f93d91161803b01210386728e2ac3ecee15f58d0505ee26f86a68f08c702941ffaf2fb7213e5026aea10247304402203a2613ae68f697eb02b5b7d18e3c4236966dac2b3a760e3021197d76e9ad4239022046f9067d3df650fcabbdfd250308c64f90757dec86f0b08813c979a42d06a6ec012102a1d7ee1cb4dc502f899aaafae0a2eb6cbf80d9a1073ae60ddcaabc3b1d1f15df02483045022100ab1bea2cc5388428fd126c7801550208701e21564bd4bd00cfd4407cfafc1acd0220508ee587f080f3c80a5c0b2175b58edd84b755e659e2135b3152044d75ebc4b501210236dd1b7f27a296447d0eb3750e1bdb2d53af50b31a72a45511dc1ec3fe7a684a193914000104160014105db4dae7e5b8dd4dda7b7d3b1e588c9bf26f192206030dddd5d3c31738ca2d8b25391f648af6a8b08e6961e8f56d4173d03e9db82d3e0c105d19280000000002000000000001001600144f485261505d5cbd33dce02a723776c99240c28722020211ab9359cc49c95b3b9a87ee95fd4edf0cecce862f9e9f86ff63e10880baaba80c105d1928010000000000000000",
                         partial_tx)
        tx_copy = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertTrue(wallet_online.is_mine(wallet_online.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual('b048784d34798ebc536d794599ca3c01f8bc3e1e1f7e0ce2a87e53b36727b774', tx_copy.txid())
        self.assertEqual(tx.txid(), tx_copy.txid())

        # sign tx
        tx = wallet_offline.sign_transaction(tx_copy, password=None)
        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual('b048784d34798ebc536d794599ca3c01f8bc3e1e1f7e0ce2a87e53b36727b774', tx.txid())
        self.assertEqual('e12c16660436a6d995c7f1dc924cba2d79d0216812ef802cfc5388a377834aa6', tx.wtxid())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_offline_xprv_online_xpub_p2wpkh(self, mock_save_db):
        wallet_offline = WalletIntegrityHelper.create_standard_wallet(
            # bip39: "qwe", der: m/84'/1'/0'
            keystore.from_xprv('vprv9K9hbuA23Bidgj1KRSHUZMa59jJLeZBpXPVn4RP7sBLArNhZxJjw4AX7aQmVTErDt4YFC11ptMLjbwxgrsH8GLQ1cx77KggWeVPeDBjr9xM'),
            gap_limit=4,
            config=self.config
        )
        wallet_online = WalletIntegrityHelper.create_standard_wallet(
            keystore.from_xpub('vpub5Y941QgusZGvuD5nXTpUvVWohm8q41uftcRNronjRWs9jB2iVr4BbxqbRfAoQjWHgJtDCQEXChgfsPbEuBnidtkFztZSD3zDKTrtwXa2LCa'),
            gap_limit=4,
            config=self.config
        )

        # bootstrap wallet_online
        funding_tx = Transaction('01000000000116e9c9dac2651672316aab3b9553257b6942c5f762c5d795776d9cfa504f183c000000000000fdffffff8085019852fada9da84b58dcf753d292dde314a19f5a5527f6588fa2566142130000000000fdffffffa4154a48db20ce538b28722a89c6b578bd5b5d60d6d7b52323976339e39405230000000000fdffffff0b5ef43f843a96364aebd708e25ea1bdcf2c7df7d0d995560b8b1be5f357b64f0100000000fdffffffd41dfe1199c76fdb3f20e9947ea31136d032d9da48c5e45d85c8f440e2351a510100000000fdffffff5bd015d17e4a1837b01c24ebb4a6b394e3da96a85442bd7dc6abddfbf16f20510000000000fdffffff13a3e7f80b1bd46e38f2abc9e2f335c18a4b0af1778133c7f1c3caae9504345c0200000000fdffffffdf4fc1ab21bca69d18544ddb10a913cd952dbc730ab3d236dd9471445ff405680100000000fdffffffe0424d78a30d5e60ac6b26e2274d7d6e7c6b78fe0b49bdc3ac4dd2147c9535750100000000fdffffff7ab6dd6b3c0d44b0fef0fdc9ab0ad6eee23eef799eee29c005d52bc4461998760000000000fdffffff48a77e5053a21acdf4f235ce00c82c9bc1704700f54d217f6a30704711b9737d0000000000fdffffff86918b39c1d9bb6f34d9b082182f73cedd15504331164dc2b186e95c568ccb870000000000fdffffff15a847356cbb44be67f345965bb3f2589e2fec1c9a0ada21fd28225dcc602e8f0100000000fdffffff9a2875297f81dfd3b77426d63f621db350c270cc28c634ad86b9969ee33ac6960000000000fdffffffd6eeb1d1833e00967083d1ab86fa5a2e44355bd613d9277135240fe6f60148a20100000000fdffffffd8a6e5a9b68a65ff88220ca33e36faf6f826ae8c5c8a13fe818a5e63828b68a40100000000fdffffff73aab8471f82092e45ed1b1afeffdb49ea1ec74ce4853f971812f6a72a7e85aa0000000000fdffffffacd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba0000000000fdffffff1eddd5e13bef1aba1ff151762b5860837daa9b39db1eae8ea8227c81a5a1c8ba0000000000fdffffff67a096ff7c343d39e96929798097f6d7a61156bbdb905fbe534ba36f273271d40100000000fdffffff109a671eb7daf6dcd07c0ceff99f2de65864ab36d64fb3a890bab951569adeee0100000000fdffffff4f1bdc64da8056d08f79db7f5348d1de55946e57aa7c8279499c703889b6e0fd0200000000fdffffff042f280000000000001600149c756aa33f4f89418b33872a973274b5445c727b80969800000000001600146c540c1c9f546004539f45318b8d9f4d7b4857ef80969800000000001976a91422a6daa4a7b695c8a2dd104d47c5dc73d655c96f88ac809698000000000017a914a6885437e0762013facbda93894202a0fe86e35f8702473044022075ef5f04d7a63347064938e15a0c74277a79e5c9d32a26e39e8a517a44d565cc022015246790fb5b29c9bf3eded1b95699b1635bcfc6d521886fddf1135ba1b988ec012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe02473044022061aa9b0d9649ffd7259bc54b35f678565dbbe11507d348dd8885522eaf1fa70c02202cc79de09e8e63e8d57fde6ef66c079ddac4d9828e1936a9db833d4c142615c3012103a8f58fc1f5625f18293403104874f2d38c9279f777e512570e4199c7d292b81b0247304402207744dc1ab0bf77c081b58540c4321d090c0a24a32742a361aa55ad86f0c7c24e02201a9b0dd78b63b495ab5a0b5b161c54cb085d70683c90e188bb4dc2e41e142f6601210361fb354f8259abfcbfbdda36b7cb4c3b05a3ca3d68dd391fd8376e920d93870d0247304402204803e423c321acc6c12cb0ebf196d2906842fdfed6de977cc78277052ee5f15002200634670c1dc25e6b1787a65d3e09c8e6bb0340238d90b9d98887e8fd53944e080121031104c60d027123bf8676bcaefaa66c001a0d3d379dc4a9492a567a9e1004452d02473044022050e4b5348d30011a22b6ae8b43921d29249d88ea71b1fbaa2d9c22dfdef58b7002201c5d5e143aa8835454f61b0742226ebf8cd466bcc2cdcb1f77b92e473d3b13190121030496b9d49aa8efece4f619876c60a77d2c0dc846390ecdc5d9acbfa1bb3128760247304402204d6a9b986e1a0e3473e8aef84b3eb7052442a76dfd7631e35377f141496a55490220131ab342853c01e31f111436f8461e28bc95883b871ca0e01b5f57146e79d7bb012103262ffbc88e25296056a3c65c880e3686297e07f360e6b80f1219d65b0900e84e02483045022100c8ffacf92efa1dddef7e858a241af7a80adcc2489bcc325195970733b1f35fac022076f40c26023a228041a9665c5290b9918d06f03b716e4d8f6d47e79121c7eb37012102d9ba7e02d7cd7dd24302f823b3114c99da21549c663f72440dc87e8ba412120902483045022100b55545d84e43d001bbc10a981f184e7d3b98a7ed6689863716cab053b3655a2f0220537eb76a695fbe86bf020b4b6f7ae93b506d778bbd0885f0a61067616a2c8bce0121034a57f2fa2c32c9246691f6a922fb1ebdf1468792bae7eff253a99fc9f2a5023902483045022100f1d4408463dbfe257f9f778d5e9c8cdb97c8b1d395dbd2e180bc08cad306492c022002a024e19e1a406eaa24467f033659de09ab58822987281e28bb6359288337bd012103e91daa18d924eea62011ce596e15b6d683975cf724ea5bf69a8e2022c26fc12f0247304402204f1e12b923872f396e5e1a3aa94b0b2e86b4ce448f4349a017631db26d7dff8a022069899a05de2ad2bbd8e0202c56ab1025a7db9a4998eea70744e3c367d2a7eb71012103b0eee86792dbef1d4a49bc4ea32d197c8c15d27e6e0c5c33e58e409e26d4a39a0247304402201787dacdb92e0df6ad90226649f0e8321287d0bd8fddc536a297dd19b5fc103e022001fe89300a76e5b46d0e3f7e39e0ee26cc83b71d59a2a5da1dd7b13350cd0c07012103afb1e43d7ec6b7999ef0f1093069e68fe1dfe5d73fc6cfb4f7a5022f7098758c02483045022100acc1212bba0fe4fcc6c3ae5cf8e25f221f140c8444d3c08dfc53a93630ac25da02203f12982847244bd9421ef340293f3a38d2ab5d028af60769e46fcc7d81312e7e012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024830450221009c04934102402949484b21899271c3991c007b783b8efc85a3c3d24641ac7c24022006fb1895ce969d08a2cb29413e1a85427c7e85426f7a185108ca44b5a0328cb301210360248db4c7d7f76fe231998d2967104fee04df8d8da34f10101cc5523e82648c02483045022100b11fe61b393fa5dbe18ab98f65c249345b429b13f69ee2d1b1335725b24a0e73022010960cdc5565cbc81885c8ed95142435d3c202dfa5a3dc5f50f3914c106335ce0121029c878610c34c21381cda12f6f36ab88bf60f5f496c1b82c357b8ac448713e7b50247304402200ca080db069c15bbf98e1d4dff68d0aea51227ff5d17a8cf67ceae464c22bbb0022051e7331c0918cbb71bb2cef29ca62411454508a16180b0fb5df94248890840df0121028f0be0cde43ff047edbda42c91c37152449d69789eb812bb2e148e4f22472c0f0247304402201fefe258938a2c481d5a745ef3aa8d9f8124bbe7f1f8c693e2ddce4ddc9a927c02204049e0060889ede8fda975edf896c03782d71ba53feb51b04f5ae5897d7431dc012103946730b480f52a43218a9edce240e8b234790e21df5e96482703d81c3c19d3f1024730440220126a6a56dbe69af78d156626fc9cf41d6aac0c07b8b5f0f8491f68db5e89cb5002207ee6ed6f2f41da256f3c1e79679a3de6cf34cc08b940b82be14aefe7da031a6b012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024730440220363204a1586d7f13c148295122cbf9ec7939685e3cadab81d6d9e921436d21b7022044626b8c2bd4aa7c167d74bc4e9eb9d0744e29ce0ad906d78e10d6d854f23d170121037fb9c51716739bb4c146857fab5a783372f72a65987d61f3b58c74360f4328dd0247304402207925a4c2a3a6b76e10558717ee28fcb8c6fde161b9dc6382239af9f372ace99902204a58e31ce0b4a4804a42d2224331289311ded2748062c92c8aca769e81417a4c012102e18a8c235b48e41ef98265a8e07fa005d2602b96d585a61ad67168d74e7391cb02483045022100bbfe060479174a8d846b5a897526003eb2220ba307a5fee6e1e8de3e4e8b38fd02206723857301d447f67ac98a5a5c2b80ef6820e98fae213db1720f93d91161803b01210386728e2ac3ecee15f58d0505ee26f86a68f08c702941ffaf2fb7213e5026aea10247304402203a2613ae68f697eb02b5b7d18e3c4236966dac2b3a760e3021197d76e9ad4239022046f9067d3df650fcabbdfd250308c64f90757dec86f0b08813c979a42d06a6ec012102a1d7ee1cb4dc502f899aaafae0a2eb6cbf80d9a1073ae60ddcaabc3b1d1f15df02483045022100ab1bea2cc5388428fd126c7801550208701e21564bd4bd00cfd4407cfafc1acd0220508ee587f080f3c80a5c0b2175b58edd84b755e659e2135b3152044d75ebc4b501210236dd1b7f27a296447d0eb3750e1bdb2d53af50b31a72a45511dc1ec3fe7a684a19391400')
        funding_txid = funding_tx.txid()
        self.assertEqual('98574bc5f6e75769eb0c93d41453cc1dfbd15c14e63cc3c42f37cdbd08858762', funding_txid)
        wallet_online.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create unsigned tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1qtuynwzd0d6wptvyqmc6ehkm70zcamxpstvxpnz', 2500000)]
        tx = wallet_online.mktx(outputs=outputs, password=None, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325341
        tx.version = 1

        self.assertFalse(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))

        orig_tx = tx
        for uses_qr_code in (False, True):
            with self.subTest(msg="uses_qr_code", uses_qr_code=uses_qr_code):
                tx = copy.deepcopy(orig_tx)
                if uses_qr_code:
                    partial_tx = tx.to_qr_data()
                    self.assertEqual("FP:A9SADM6+OGU/3KZ/RCI$7/Y2R7OZYNZXB1.$0Y9K69-BXZZ1EAWLM0/*SYX7G:1/0N9+E5YWF0KRPK/Y-GJSJ7TM/A0N0RSQ4O$-QN+I5H7S-TXY5DQT+P4N43/Q7VW$EDNG5W5ZA1-OCZ.RW2ZY1PQ2WEIG7T8TS13RL5P.J2HU2SGTL-QPLE+N.J8LCNCH65S8A0Y*4EVP*80JG4FFJ+MU5/E7VJU0UQ*GC+GW1OP08GN5VT*SB$O2/XH7S/S/HOCRCGUPKOL$M2LMO6L.K$O$$2S0JILB.09MY0XRXQPLH.RW073006LI4NP9E5N4GJWXJCVGX*6H.C1$$CR+J.GNQ299+N/M-K-9-MJRU0T5M4T/T8W-8",
                                     partial_tx)
                else:
                    partial_tx = tx.serialize_as_bytes().hex()
                    self.assertEqual("70736274ff010071010000000162878508bdcd372fc4c33ce6145cd1fb1dcc5314d4930ceb6957e7f6c54b57980100000000fdffffff02a0252600000000001600145f093709af6e9c15b080de359bdb7e78b1dd9830585d7200000000001600145543fe1a1364b806b27a5c9dc92ac9bbf0d42aa31d391400000100fd4c0d01000000000116e9c9dac2651672316aab3b9553257b6942c5f762c5d795776d9cfa504f183c000000000000fdffffff8085019852fada9da84b58dcf753d292dde314a19f5a5527f6588fa2566142130000000000fdffffffa4154a48db20ce538b28722a89c6b578bd5b5d60d6d7b52323976339e39405230000000000fdffffff0b5ef43f843a96364aebd708e25ea1bdcf2c7df7d0d995560b8b1be5f357b64f0100000000fdffffffd41dfe1199c76fdb3f20e9947ea31136d032d9da48c5e45d85c8f440e2351a510100000000fdffffff5bd015d17e4a1837b01c24ebb4a6b394e3da96a85442bd7dc6abddfbf16f20510000000000fdffffff13a3e7f80b1bd46e38f2abc9e2f335c18a4b0af1778133c7f1c3caae9504345c0200000000fdffffffdf4fc1ab21bca69d18544ddb10a913cd952dbc730ab3d236dd9471445ff405680100000000fdffffffe0424d78a30d5e60ac6b26e2274d7d6e7c6b78fe0b49bdc3ac4dd2147c9535750100000000fdffffff7ab6dd6b3c0d44b0fef0fdc9ab0ad6eee23eef799eee29c005d52bc4461998760000000000fdffffff48a77e5053a21acdf4f235ce00c82c9bc1704700f54d217f6a30704711b9737d0000000000fdffffff86918b39c1d9bb6f34d9b082182f73cedd15504331164dc2b186e95c568ccb870000000000fdffffff15a847356cbb44be67f345965bb3f2589e2fec1c9a0ada21fd28225dcc602e8f0100000000fdffffff9a2875297f81dfd3b77426d63f621db350c270cc28c634ad86b9969ee33ac6960000000000fdffffffd6eeb1d1833e00967083d1ab86fa5a2e44355bd613d9277135240fe6f60148a20100000000fdffffffd8a6e5a9b68a65ff88220ca33e36faf6f826ae8c5c8a13fe818a5e63828b68a40100000000fdffffff73aab8471f82092e45ed1b1afeffdb49ea1ec74ce4853f971812f6a72a7e85aa0000000000fdffffffacd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba0000000000fdffffff1eddd5e13bef1aba1ff151762b5860837daa9b39db1eae8ea8227c81a5a1c8ba0000000000fdffffff67a096ff7c343d39e96929798097f6d7a61156bbdb905fbe534ba36f273271d40100000000fdffffff109a671eb7daf6dcd07c0ceff99f2de65864ab36d64fb3a890bab951569adeee0100000000fdffffff4f1bdc64da8056d08f79db7f5348d1de55946e57aa7c8279499c703889b6e0fd0200000000fdffffff042f280000000000001600149c756aa33f4f89418b33872a973274b5445c727b80969800000000001600146c540c1c9f546004539f45318b8d9f4d7b4857ef80969800000000001976a91422a6daa4a7b695c8a2dd104d47c5dc73d655c96f88ac809698000000000017a914a6885437e0762013facbda93894202a0fe86e35f8702473044022075ef5f04d7a63347064938e15a0c74277a79e5c9d32a26e39e8a517a44d565cc022015246790fb5b29c9bf3eded1b95699b1635bcfc6d521886fddf1135ba1b988ec012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe02473044022061aa9b0d9649ffd7259bc54b35f678565dbbe11507d348dd8885522eaf1fa70c02202cc79de09e8e63e8d57fde6ef66c079ddac4d9828e1936a9db833d4c142615c3012103a8f58fc1f5625f18293403104874f2d38c9279f777e512570e4199c7d292b81b0247304402207744dc1ab0bf77c081b58540c4321d090c0a24a32742a361aa55ad86f0c7c24e02201a9b0dd78b63b495ab5a0b5b161c54cb085d70683c90e188bb4dc2e41e142f6601210361fb354f8259abfcbfbdda36b7cb4c3b05a3ca3d68dd391fd8376e920d93870d0247304402204803e423c321acc6c12cb0ebf196d2906842fdfed6de977cc78277052ee5f15002200634670c1dc25e6b1787a65d3e09c8e6bb0340238d90b9d98887e8fd53944e080121031104c60d027123bf8676bcaefaa66c001a0d3d379dc4a9492a567a9e1004452d02473044022050e4b5348d30011a22b6ae8b43921d29249d88ea71b1fbaa2d9c22dfdef58b7002201c5d5e143aa8835454f61b0742226ebf8cd466bcc2cdcb1f77b92e473d3b13190121030496b9d49aa8efece4f619876c60a77d2c0dc846390ecdc5d9acbfa1bb3128760247304402204d6a9b986e1a0e3473e8aef84b3eb7052442a76dfd7631e35377f141496a55490220131ab342853c01e31f111436f8461e28bc95883b871ca0e01b5f57146e79d7bb012103262ffbc88e25296056a3c65c880e3686297e07f360e6b80f1219d65b0900e84e02483045022100c8ffacf92efa1dddef7e858a241af7a80adcc2489bcc325195970733b1f35fac022076f40c26023a228041a9665c5290b9918d06f03b716e4d8f6d47e79121c7eb37012102d9ba7e02d7cd7dd24302f823b3114c99da21549c663f72440dc87e8ba412120902483045022100b55545d84e43d001bbc10a981f184e7d3b98a7ed6689863716cab053b3655a2f0220537eb76a695fbe86bf020b4b6f7ae93b506d778bbd0885f0a61067616a2c8bce0121034a57f2fa2c32c9246691f6a922fb1ebdf1468792bae7eff253a99fc9f2a5023902483045022100f1d4408463dbfe257f9f778d5e9c8cdb97c8b1d395dbd2e180bc08cad306492c022002a024e19e1a406eaa24467f033659de09ab58822987281e28bb6359288337bd012103e91daa18d924eea62011ce596e15b6d683975cf724ea5bf69a8e2022c26fc12f0247304402204f1e12b923872f396e5e1a3aa94b0b2e86b4ce448f4349a017631db26d7dff8a022069899a05de2ad2bbd8e0202c56ab1025a7db9a4998eea70744e3c367d2a7eb71012103b0eee86792dbef1d4a49bc4ea32d197c8c15d27e6e0c5c33e58e409e26d4a39a0247304402201787dacdb92e0df6ad90226649f0e8321287d0bd8fddc536a297dd19b5fc103e022001fe89300a76e5b46d0e3f7e39e0ee26cc83b71d59a2a5da1dd7b13350cd0c07012103afb1e43d7ec6b7999ef0f1093069e68fe1dfe5d73fc6cfb4f7a5022f7098758c02483045022100acc1212bba0fe4fcc6c3ae5cf8e25f221f140c8444d3c08dfc53a93630ac25da02203f12982847244bd9421ef340293f3a38d2ab5d028af60769e46fcc7d81312e7e012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024830450221009c04934102402949484b21899271c3991c007b783b8efc85a3c3d24641ac7c24022006fb1895ce969d08a2cb29413e1a85427c7e85426f7a185108ca44b5a0328cb301210360248db4c7d7f76fe231998d2967104fee04df8d8da34f10101cc5523e82648c02483045022100b11fe61b393fa5dbe18ab98f65c249345b429b13f69ee2d1b1335725b24a0e73022010960cdc5565cbc81885c8ed95142435d3c202dfa5a3dc5f50f3914c106335ce0121029c878610c34c21381cda12f6f36ab88bf60f5f496c1b82c357b8ac448713e7b50247304402200ca080db069c15bbf98e1d4dff68d0aea51227ff5d17a8cf67ceae464c22bbb0022051e7331c0918cbb71bb2cef29ca62411454508a16180b0fb5df94248890840df0121028f0be0cde43ff047edbda42c91c37152449d69789eb812bb2e148e4f22472c0f0247304402201fefe258938a2c481d5a745ef3aa8d9f8124bbe7f1f8c693e2ddce4ddc9a927c02204049e0060889ede8fda975edf896c03782d71ba53feb51b04f5ae5897d7431dc012103946730b480f52a43218a9edce240e8b234790e21df5e96482703d81c3c19d3f1024730440220126a6a56dbe69af78d156626fc9cf41d6aac0c07b8b5f0f8491f68db5e89cb5002207ee6ed6f2f41da256f3c1e79679a3de6cf34cc08b940b82be14aefe7da031a6b012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024730440220363204a1586d7f13c148295122cbf9ec7939685e3cadab81d6d9e921436d21b7022044626b8c2bd4aa7c167d74bc4e9eb9d0744e29ce0ad906d78e10d6d854f23d170121037fb9c51716739bb4c146857fab5a783372f72a65987d61f3b58c74360f4328dd0247304402207925a4c2a3a6b76e10558717ee28fcb8c6fde161b9dc6382239af9f372ace99902204a58e31ce0b4a4804a42d2224331289311ded2748062c92c8aca769e81417a4c012102e18a8c235b48e41ef98265a8e07fa005d2602b96d585a61ad67168d74e7391cb02483045022100bbfe060479174a8d846b5a897526003eb2220ba307a5fee6e1e8de3e4e8b38fd02206723857301d447f67ac98a5a5c2b80ef6820e98fae213db1720f93d91161803b01210386728e2ac3ecee15f58d0505ee26f86a68f08c702941ffaf2fb7213e5026aea10247304402203a2613ae68f697eb02b5b7d18e3c4236966dac2b3a760e3021197d76e9ad4239022046f9067d3df650fcabbdfd250308c64f90757dec86f0b08813c979a42d06a6ec012102a1d7ee1cb4dc502f899aaafae0a2eb6cbf80d9a1073ae60ddcaabc3b1d1f15df02483045022100ab1bea2cc5388428fd126c7801550208701e21564bd4bd00cfd4407cfafc1acd0220508ee587f080f3c80a5c0b2175b58edd84b755e659e2135b3152044d75ebc4b501210236dd1b7f27a296447d0eb3750e1bdb2d53af50b31a72a45511dc1ec3fe7a684a19391400220603fd88f32a81e812af0187677fc0e7ac9b7fb63ca68c2d98c2afbcf99aa311ac060cdf758ae500000000020000000000220202ac05f54ef082ac98302d57d532e728653565bd55f46fcf03cacbddb168fd6c760cdf758ae5010000000000000000",
                                     partial_tx)
                tx_copy = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
                self.assertTrue(wallet_online.is_mine(wallet_online.get_txin_address(tx_copy.inputs()[0])))

                self.assertEqual('3258b25342b0668dec540fea26ffa270ec3b9ae24f6cf5a25d18698fab5db4d6', tx_copy.txid())
                self.assertEqual(tx.txid(), tx_copy.txid())

                # sign tx
                tx = wallet_offline.sign_transaction(tx_copy, password=None)
                self.assertTrue(tx.is_complete())
                self.assertTrue(tx.is_segwit())
                self.assertEqual('3258b25342b0668dec540fea26ffa270ec3b9ae24f6cf5a25d18698fab5db4d6', tx.txid())
                self.assertEqual('bf6f891366f32b1daf09ffccdfc29f7a7fee9261321be17aed17143ee02813e1', tx.wtxid())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_offline_signing_beyond_gap_limit(self, mock_save_db):
        wallet_offline = WalletIntegrityHelper.create_standard_wallet(
            # bip39: "qwe", der: m/84'/1'/0'
            keystore.from_xprv('vprv9K9hbuA23Bidgj1KRSHUZMa59jJLeZBpXPVn4RP7sBLArNhZxJjw4AX7aQmVTErDt4YFC11ptMLjbwxgrsH8GLQ1cx77KggWeVPeDBjr9xM'),
            gap_limit=1,  # gap limit of offline wallet intentionally set too low
            config=self.config
        )
        wallet_online = WalletIntegrityHelper.create_standard_wallet(
            keystore.from_xpub('vpub5Y941QgusZGvuD5nXTpUvVWohm8q41uftcRNronjRWs9jB2iVr4BbxqbRfAoQjWHgJtDCQEXChgfsPbEuBnidtkFztZSD3zDKTrtwXa2LCa'),
            gap_limit=4,
            config=self.config
        )

        # bootstrap wallet_online
        funding_tx = Transaction('01000000000116e9c9dac2651672316aab3b9553257b6942c5f762c5d795776d9cfa504f183c000000000000fdffffff8085019852fada9da84b58dcf753d292dde314a19f5a5527f6588fa2566142130000000000fdffffffa4154a48db20ce538b28722a89c6b578bd5b5d60d6d7b52323976339e39405230000000000fdffffff0b5ef43f843a96364aebd708e25ea1bdcf2c7df7d0d995560b8b1be5f357b64f0100000000fdffffffd41dfe1199c76fdb3f20e9947ea31136d032d9da48c5e45d85c8f440e2351a510100000000fdffffff5bd015d17e4a1837b01c24ebb4a6b394e3da96a85442bd7dc6abddfbf16f20510000000000fdffffff13a3e7f80b1bd46e38f2abc9e2f335c18a4b0af1778133c7f1c3caae9504345c0200000000fdffffffdf4fc1ab21bca69d18544ddb10a913cd952dbc730ab3d236dd9471445ff405680100000000fdffffffe0424d78a30d5e60ac6b26e2274d7d6e7c6b78fe0b49bdc3ac4dd2147c9535750100000000fdffffff7ab6dd6b3c0d44b0fef0fdc9ab0ad6eee23eef799eee29c005d52bc4461998760000000000fdffffff48a77e5053a21acdf4f235ce00c82c9bc1704700f54d217f6a30704711b9737d0000000000fdffffff86918b39c1d9bb6f34d9b082182f73cedd15504331164dc2b186e95c568ccb870000000000fdffffff15a847356cbb44be67f345965bb3f2589e2fec1c9a0ada21fd28225dcc602e8f0100000000fdffffff9a2875297f81dfd3b77426d63f621db350c270cc28c634ad86b9969ee33ac6960000000000fdffffffd6eeb1d1833e00967083d1ab86fa5a2e44355bd613d9277135240fe6f60148a20100000000fdffffffd8a6e5a9b68a65ff88220ca33e36faf6f826ae8c5c8a13fe818a5e63828b68a40100000000fdffffff73aab8471f82092e45ed1b1afeffdb49ea1ec74ce4853f971812f6a72a7e85aa0000000000fdffffffacd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba0000000000fdffffff1eddd5e13bef1aba1ff151762b5860837daa9b39db1eae8ea8227c81a5a1c8ba0000000000fdffffff67a096ff7c343d39e96929798097f6d7a61156bbdb905fbe534ba36f273271d40100000000fdffffff109a671eb7daf6dcd07c0ceff99f2de65864ab36d64fb3a890bab951569adeee0100000000fdffffff4f1bdc64da8056d08f79db7f5348d1de55946e57aa7c8279499c703889b6e0fd0200000000fdffffff042f280000000000001600149c756aa33f4f89418b33872a973274b5445c727b80969800000000001600146c540c1c9f546004539f45318b8d9f4d7b4857ef80969800000000001976a91422a6daa4a7b695c8a2dd104d47c5dc73d655c96f88ac809698000000000017a914a6885437e0762013facbda93894202a0fe86e35f8702473044022075ef5f04d7a63347064938e15a0c74277a79e5c9d32a26e39e8a517a44d565cc022015246790fb5b29c9bf3eded1b95699b1635bcfc6d521886fddf1135ba1b988ec012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe02473044022061aa9b0d9649ffd7259bc54b35f678565dbbe11507d348dd8885522eaf1fa70c02202cc79de09e8e63e8d57fde6ef66c079ddac4d9828e1936a9db833d4c142615c3012103a8f58fc1f5625f18293403104874f2d38c9279f777e512570e4199c7d292b81b0247304402207744dc1ab0bf77c081b58540c4321d090c0a24a32742a361aa55ad86f0c7c24e02201a9b0dd78b63b495ab5a0b5b161c54cb085d70683c90e188bb4dc2e41e142f6601210361fb354f8259abfcbfbdda36b7cb4c3b05a3ca3d68dd391fd8376e920d93870d0247304402204803e423c321acc6c12cb0ebf196d2906842fdfed6de977cc78277052ee5f15002200634670c1dc25e6b1787a65d3e09c8e6bb0340238d90b9d98887e8fd53944e080121031104c60d027123bf8676bcaefaa66c001a0d3d379dc4a9492a567a9e1004452d02473044022050e4b5348d30011a22b6ae8b43921d29249d88ea71b1fbaa2d9c22dfdef58b7002201c5d5e143aa8835454f61b0742226ebf8cd466bcc2cdcb1f77b92e473d3b13190121030496b9d49aa8efece4f619876c60a77d2c0dc846390ecdc5d9acbfa1bb3128760247304402204d6a9b986e1a0e3473e8aef84b3eb7052442a76dfd7631e35377f141496a55490220131ab342853c01e31f111436f8461e28bc95883b871ca0e01b5f57146e79d7bb012103262ffbc88e25296056a3c65c880e3686297e07f360e6b80f1219d65b0900e84e02483045022100c8ffacf92efa1dddef7e858a241af7a80adcc2489bcc325195970733b1f35fac022076f40c26023a228041a9665c5290b9918d06f03b716e4d8f6d47e79121c7eb37012102d9ba7e02d7cd7dd24302f823b3114c99da21549c663f72440dc87e8ba412120902483045022100b55545d84e43d001bbc10a981f184e7d3b98a7ed6689863716cab053b3655a2f0220537eb76a695fbe86bf020b4b6f7ae93b506d778bbd0885f0a61067616a2c8bce0121034a57f2fa2c32c9246691f6a922fb1ebdf1468792bae7eff253a99fc9f2a5023902483045022100f1d4408463dbfe257f9f778d5e9c8cdb97c8b1d395dbd2e180bc08cad306492c022002a024e19e1a406eaa24467f033659de09ab58822987281e28bb6359288337bd012103e91daa18d924eea62011ce596e15b6d683975cf724ea5bf69a8e2022c26fc12f0247304402204f1e12b923872f396e5e1a3aa94b0b2e86b4ce448f4349a017631db26d7dff8a022069899a05de2ad2bbd8e0202c56ab1025a7db9a4998eea70744e3c367d2a7eb71012103b0eee86792dbef1d4a49bc4ea32d197c8c15d27e6e0c5c33e58e409e26d4a39a0247304402201787dacdb92e0df6ad90226649f0e8321287d0bd8fddc536a297dd19b5fc103e022001fe89300a76e5b46d0e3f7e39e0ee26cc83b71d59a2a5da1dd7b13350cd0c07012103afb1e43d7ec6b7999ef0f1093069e68fe1dfe5d73fc6cfb4f7a5022f7098758c02483045022100acc1212bba0fe4fcc6c3ae5cf8e25f221f140c8444d3c08dfc53a93630ac25da02203f12982847244bd9421ef340293f3a38d2ab5d028af60769e46fcc7d81312e7e012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024830450221009c04934102402949484b21899271c3991c007b783b8efc85a3c3d24641ac7c24022006fb1895ce969d08a2cb29413e1a85427c7e85426f7a185108ca44b5a0328cb301210360248db4c7d7f76fe231998d2967104fee04df8d8da34f10101cc5523e82648c02483045022100b11fe61b393fa5dbe18ab98f65c249345b429b13f69ee2d1b1335725b24a0e73022010960cdc5565cbc81885c8ed95142435d3c202dfa5a3dc5f50f3914c106335ce0121029c878610c34c21381cda12f6f36ab88bf60f5f496c1b82c357b8ac448713e7b50247304402200ca080db069c15bbf98e1d4dff68d0aea51227ff5d17a8cf67ceae464c22bbb0022051e7331c0918cbb71bb2cef29ca62411454508a16180b0fb5df94248890840df0121028f0be0cde43ff047edbda42c91c37152449d69789eb812bb2e148e4f22472c0f0247304402201fefe258938a2c481d5a745ef3aa8d9f8124bbe7f1f8c693e2ddce4ddc9a927c02204049e0060889ede8fda975edf896c03782d71ba53feb51b04f5ae5897d7431dc012103946730b480f52a43218a9edce240e8b234790e21df5e96482703d81c3c19d3f1024730440220126a6a56dbe69af78d156626fc9cf41d6aac0c07b8b5f0f8491f68db5e89cb5002207ee6ed6f2f41da256f3c1e79679a3de6cf34cc08b940b82be14aefe7da031a6b012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024730440220363204a1586d7f13c148295122cbf9ec7939685e3cadab81d6d9e921436d21b7022044626b8c2bd4aa7c167d74bc4e9eb9d0744e29ce0ad906d78e10d6d854f23d170121037fb9c51716739bb4c146857fab5a783372f72a65987d61f3b58c74360f4328dd0247304402207925a4c2a3a6b76e10558717ee28fcb8c6fde161b9dc6382239af9f372ace99902204a58e31ce0b4a4804a42d2224331289311ded2748062c92c8aca769e81417a4c012102e18a8c235b48e41ef98265a8e07fa005d2602b96d585a61ad67168d74e7391cb02483045022100bbfe060479174a8d846b5a897526003eb2220ba307a5fee6e1e8de3e4e8b38fd02206723857301d447f67ac98a5a5c2b80ef6820e98fae213db1720f93d91161803b01210386728e2ac3ecee15f58d0505ee26f86a68f08c702941ffaf2fb7213e5026aea10247304402203a2613ae68f697eb02b5b7d18e3c4236966dac2b3a760e3021197d76e9ad4239022046f9067d3df650fcabbdfd250308c64f90757dec86f0b08813c979a42d06a6ec012102a1d7ee1cb4dc502f899aaafae0a2eb6cbf80d9a1073ae60ddcaabc3b1d1f15df02483045022100ab1bea2cc5388428fd126c7801550208701e21564bd4bd00cfd4407cfafc1acd0220508ee587f080f3c80a5c0b2175b58edd84b755e659e2135b3152044d75ebc4b501210236dd1b7f27a296447d0eb3750e1bdb2d53af50b31a72a45511dc1ec3fe7a684a19391400')
        funding_txid = funding_tx.txid()
        self.assertEqual('98574bc5f6e75769eb0c93d41453cc1dfbd15c14e63cc3c42f37cdbd08858762', funding_txid)
        wallet_online.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create unsigned tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1qtuynwzd0d6wptvyqmc6ehkm70zcamxpstvxpnz', 2500000)]
        tx = wallet_online.mktx(outputs=outputs, password=None, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325341
        tx.version = 1

        self.assertFalse(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual(1, len(tx.inputs()))
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff010071010000000162878508bdcd372fc4c33ce6145cd1fb1dcc5314d4930ceb6957e7f6c54b57980100000000fdffffff02a0252600000000001600145f093709af6e9c15b080de359bdb7e78b1dd9830585d7200000000001600145543fe1a1364b806b27a5c9dc92ac9bbf0d42aa31d391400000100fd4c0d01000000000116e9c9dac2651672316aab3b9553257b6942c5f762c5d795776d9cfa504f183c000000000000fdffffff8085019852fada9da84b58dcf753d292dde314a19f5a5527f6588fa2566142130000000000fdffffffa4154a48db20ce538b28722a89c6b578bd5b5d60d6d7b52323976339e39405230000000000fdffffff0b5ef43f843a96364aebd708e25ea1bdcf2c7df7d0d995560b8b1be5f357b64f0100000000fdffffffd41dfe1199c76fdb3f20e9947ea31136d032d9da48c5e45d85c8f440e2351a510100000000fdffffff5bd015d17e4a1837b01c24ebb4a6b394e3da96a85442bd7dc6abddfbf16f20510000000000fdffffff13a3e7f80b1bd46e38f2abc9e2f335c18a4b0af1778133c7f1c3caae9504345c0200000000fdffffffdf4fc1ab21bca69d18544ddb10a913cd952dbc730ab3d236dd9471445ff405680100000000fdffffffe0424d78a30d5e60ac6b26e2274d7d6e7c6b78fe0b49bdc3ac4dd2147c9535750100000000fdffffff7ab6dd6b3c0d44b0fef0fdc9ab0ad6eee23eef799eee29c005d52bc4461998760000000000fdffffff48a77e5053a21acdf4f235ce00c82c9bc1704700f54d217f6a30704711b9737d0000000000fdffffff86918b39c1d9bb6f34d9b082182f73cedd15504331164dc2b186e95c568ccb870000000000fdffffff15a847356cbb44be67f345965bb3f2589e2fec1c9a0ada21fd28225dcc602e8f0100000000fdffffff9a2875297f81dfd3b77426d63f621db350c270cc28c634ad86b9969ee33ac6960000000000fdffffffd6eeb1d1833e00967083d1ab86fa5a2e44355bd613d9277135240fe6f60148a20100000000fdffffffd8a6e5a9b68a65ff88220ca33e36faf6f826ae8c5c8a13fe818a5e63828b68a40100000000fdffffff73aab8471f82092e45ed1b1afeffdb49ea1ec74ce4853f971812f6a72a7e85aa0000000000fdffffffacd6459dec7c3c51048eb112630da756f5d4cb4752b8d39aa325407ae0885cba0000000000fdffffff1eddd5e13bef1aba1ff151762b5860837daa9b39db1eae8ea8227c81a5a1c8ba0000000000fdffffff67a096ff7c343d39e96929798097f6d7a61156bbdb905fbe534ba36f273271d40100000000fdffffff109a671eb7daf6dcd07c0ceff99f2de65864ab36d64fb3a890bab951569adeee0100000000fdffffff4f1bdc64da8056d08f79db7f5348d1de55946e57aa7c8279499c703889b6e0fd0200000000fdffffff042f280000000000001600149c756aa33f4f89418b33872a973274b5445c727b80969800000000001600146c540c1c9f546004539f45318b8d9f4d7b4857ef80969800000000001976a91422a6daa4a7b695c8a2dd104d47c5dc73d655c96f88ac809698000000000017a914a6885437e0762013facbda93894202a0fe86e35f8702473044022075ef5f04d7a63347064938e15a0c74277a79e5c9d32a26e39e8a517a44d565cc022015246790fb5b29c9bf3eded1b95699b1635bcfc6d521886fddf1135ba1b988ec012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe02473044022061aa9b0d9649ffd7259bc54b35f678565dbbe11507d348dd8885522eaf1fa70c02202cc79de09e8e63e8d57fde6ef66c079ddac4d9828e1936a9db833d4c142615c3012103a8f58fc1f5625f18293403104874f2d38c9279f777e512570e4199c7d292b81b0247304402207744dc1ab0bf77c081b58540c4321d090c0a24a32742a361aa55ad86f0c7c24e02201a9b0dd78b63b495ab5a0b5b161c54cb085d70683c90e188bb4dc2e41e142f6601210361fb354f8259abfcbfbdda36b7cb4c3b05a3ca3d68dd391fd8376e920d93870d0247304402204803e423c321acc6c12cb0ebf196d2906842fdfed6de977cc78277052ee5f15002200634670c1dc25e6b1787a65d3e09c8e6bb0340238d90b9d98887e8fd53944e080121031104c60d027123bf8676bcaefaa66c001a0d3d379dc4a9492a567a9e1004452d02473044022050e4b5348d30011a22b6ae8b43921d29249d88ea71b1fbaa2d9c22dfdef58b7002201c5d5e143aa8835454f61b0742226ebf8cd466bcc2cdcb1f77b92e473d3b13190121030496b9d49aa8efece4f619876c60a77d2c0dc846390ecdc5d9acbfa1bb3128760247304402204d6a9b986e1a0e3473e8aef84b3eb7052442a76dfd7631e35377f141496a55490220131ab342853c01e31f111436f8461e28bc95883b871ca0e01b5f57146e79d7bb012103262ffbc88e25296056a3c65c880e3686297e07f360e6b80f1219d65b0900e84e02483045022100c8ffacf92efa1dddef7e858a241af7a80adcc2489bcc325195970733b1f35fac022076f40c26023a228041a9665c5290b9918d06f03b716e4d8f6d47e79121c7eb37012102d9ba7e02d7cd7dd24302f823b3114c99da21549c663f72440dc87e8ba412120902483045022100b55545d84e43d001bbc10a981f184e7d3b98a7ed6689863716cab053b3655a2f0220537eb76a695fbe86bf020b4b6f7ae93b506d778bbd0885f0a61067616a2c8bce0121034a57f2fa2c32c9246691f6a922fb1ebdf1468792bae7eff253a99fc9f2a5023902483045022100f1d4408463dbfe257f9f778d5e9c8cdb97c8b1d395dbd2e180bc08cad306492c022002a024e19e1a406eaa24467f033659de09ab58822987281e28bb6359288337bd012103e91daa18d924eea62011ce596e15b6d683975cf724ea5bf69a8e2022c26fc12f0247304402204f1e12b923872f396e5e1a3aa94b0b2e86b4ce448f4349a017631db26d7dff8a022069899a05de2ad2bbd8e0202c56ab1025a7db9a4998eea70744e3c367d2a7eb71012103b0eee86792dbef1d4a49bc4ea32d197c8c15d27e6e0c5c33e58e409e26d4a39a0247304402201787dacdb92e0df6ad90226649f0e8321287d0bd8fddc536a297dd19b5fc103e022001fe89300a76e5b46d0e3f7e39e0ee26cc83b71d59a2a5da1dd7b13350cd0c07012103afb1e43d7ec6b7999ef0f1093069e68fe1dfe5d73fc6cfb4f7a5022f7098758c02483045022100acc1212bba0fe4fcc6c3ae5cf8e25f221f140c8444d3c08dfc53a93630ac25da02203f12982847244bd9421ef340293f3a38d2ab5d028af60769e46fcc7d81312e7e012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024830450221009c04934102402949484b21899271c3991c007b783b8efc85a3c3d24641ac7c24022006fb1895ce969d08a2cb29413e1a85427c7e85426f7a185108ca44b5a0328cb301210360248db4c7d7f76fe231998d2967104fee04df8d8da34f10101cc5523e82648c02483045022100b11fe61b393fa5dbe18ab98f65c249345b429b13f69ee2d1b1335725b24a0e73022010960cdc5565cbc81885c8ed95142435d3c202dfa5a3dc5f50f3914c106335ce0121029c878610c34c21381cda12f6f36ab88bf60f5f496c1b82c357b8ac448713e7b50247304402200ca080db069c15bbf98e1d4dff68d0aea51227ff5d17a8cf67ceae464c22bbb0022051e7331c0918cbb71bb2cef29ca62411454508a16180b0fb5df94248890840df0121028f0be0cde43ff047edbda42c91c37152449d69789eb812bb2e148e4f22472c0f0247304402201fefe258938a2c481d5a745ef3aa8d9f8124bbe7f1f8c693e2ddce4ddc9a927c02204049e0060889ede8fda975edf896c03782d71ba53feb51b04f5ae5897d7431dc012103946730b480f52a43218a9edce240e8b234790e21df5e96482703d81c3c19d3f1024730440220126a6a56dbe69af78d156626fc9cf41d6aac0c07b8b5f0f8491f68db5e89cb5002207ee6ed6f2f41da256f3c1e79679a3de6cf34cc08b940b82be14aefe7da031a6b012102801bc7170efb82c490e243204d86970f15966aa3bce6a06bef5c09a83a5bfffe024730440220363204a1586d7f13c148295122cbf9ec7939685e3cadab81d6d9e921436d21b7022044626b8c2bd4aa7c167d74bc4e9eb9d0744e29ce0ad906d78e10d6d854f23d170121037fb9c51716739bb4c146857fab5a783372f72a65987d61f3b58c74360f4328dd0247304402207925a4c2a3a6b76e10558717ee28fcb8c6fde161b9dc6382239af9f372ace99902204a58e31ce0b4a4804a42d2224331289311ded2748062c92c8aca769e81417a4c012102e18a8c235b48e41ef98265a8e07fa005d2602b96d585a61ad67168d74e7391cb02483045022100bbfe060479174a8d846b5a897526003eb2220ba307a5fee6e1e8de3e4e8b38fd02206723857301d447f67ac98a5a5c2b80ef6820e98fae213db1720f93d91161803b01210386728e2ac3ecee15f58d0505ee26f86a68f08c702941ffaf2fb7213e5026aea10247304402203a2613ae68f697eb02b5b7d18e3c4236966dac2b3a760e3021197d76e9ad4239022046f9067d3df650fcabbdfd250308c64f90757dec86f0b08813c979a42d06a6ec012102a1d7ee1cb4dc502f899aaafae0a2eb6cbf80d9a1073ae60ddcaabc3b1d1f15df02483045022100ab1bea2cc5388428fd126c7801550208701e21564bd4bd00cfd4407cfafc1acd0220508ee587f080f3c80a5c0b2175b58edd84b755e659e2135b3152044d75ebc4b501210236dd1b7f27a296447d0eb3750e1bdb2d53af50b31a72a45511dc1ec3fe7a684a19391400220603fd88f32a81e812af0187677fc0e7ac9b7fb63ca68c2d98c2afbcf99aa311ac060cdf758ae500000000020000000000220202ac05f54ef082ac98302d57d532e728653565bd55f46fcf03cacbddb168fd6c760cdf758ae5010000000000000000",
                         partial_tx)
        tx_copy = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertTrue(wallet_online.is_mine(wallet_online.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual('3258b25342b0668dec540fea26ffa270ec3b9ae24f6cf5a25d18698fab5db4d6', tx_copy.txid())
        self.assertEqual(tx.txid(), tx_copy.txid())

        # sign tx
        tx = wallet_offline.sign_transaction(tx_copy, password=None)
        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual('3258b25342b0668dec540fea26ffa270ec3b9ae24f6cf5a25d18698fab5db4d6', tx.txid())
        self.assertEqual('bf6f891366f32b1daf09ffccdfc29f7a7fee9261321be17aed17143ee02813e1', tx.wtxid())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_signing_where_offline_ks_does_not_have_keyorigin_but_psbt_contains_it(self, mock_save_db):
        # keystore has intermediate xprv without root fp; tx contains root fp and full path.
        # tx has input with key beyond gap limit
        wallet_offline = WalletIntegrityHelper.create_standard_wallet(
            # bip39 seed: "brave scare company drastic consider confirm grow differ alter wide olympic utility"
            # der: m/84'/1'/0'
            keystore.from_xprv('vprv9KXDgRXYp3WCozCS3bMehASe2cJhY28DihCZ3KuyiTTjngopkfRC9QkH1SUREyCvnV7TSD6EgEHTTYa5yod7ZveBhVReEU1uDgfVASFqLNw'),
            gap_limit=4,
            config=self.config
        )

        tx = tx_from_any('70736274ff01005202000000017b748828553b1127b86674e71ad0cd4a2e5e8baeab8792a3c3263f7ea0ba86500000000000fdffffff01ad16010000000000160014d74b54300bc0d4b6e8f506fe540b47ce0da38b4a08f21c00000100bf0200000000010163a419b779be17167c54ff3acb1205e5347fbd72963f89fb1d66b5cf09f329c90000000000fdffffff011b17010000000000160014ed420532f0c33477b9b3fbb57431b4a1adce99c90247304402204e4ad4992fa8798e3b595d17c59961b905ca71c32dc3ba910ae14f139259ffbe02206ee2281f21499e46aa77f4bec2edce3674fea529d9dd340439365c2232bad35701210334080358ffdac08f83d6800a8e477e3512ad5c39ede553089db8c4bbe16f59aad7f11c00220602d137f257a96cbc58c7e60f2085cd65a311e242459e23d1efbed77dd8f372513818cc2bdaaa540000800100008000000080000000001e000000002202030671d324eeba0f85499a8749f783a4883103d23f5dedbe048391ff18c3da067818cc2bdaaa540000800100008000000080000000000100000000')
        self.assertEqual('065b6e0a5731107641828337f5e000c9ddd94a12d074708643b0bca517374c6a', tx.txid())

        # sign tx
        tx = wallet_offline.sign_transaction(tx, password=None)
        self.assertTrue(tx.is_complete())
        self.assertEqual('020000000001017b748828553b1127b86674e71ad0cd4a2e5e8baeab8792a3c3263f7ea0ba86500000000000fdffffff01ad16010000000000160014d74b54300bc0d4b6e8f506fe540b47ce0da38b4a0247304402203098741bf4d4f956e96f2706a517a1c0a63f67a242a50d155fbc56ad0bbac8b102207e535391c03bdab641f3205762311c1e6648b3459681e53d68fa44e63604a7f6012102d137f257a96cbc58c7e60f2085cd65a311e242459e23d1efbed77dd8f372513808f21c00',
                         str(tx))

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_offline_wif_online_addr_p2pkh(self, mock_save_db):  # compressed pubkey
        wallet_offline = WalletIntegrityHelper.create_imported_wallet(privkeys=True, config=self.config)
        wallet_offline.import_private_key('p2pkh:cQDxbmQfwRV3vP1mdnVHq37nJekHLsuD3wdSQseBRA2ct4MFk5Pq', password=None)
        wallet_online = WalletIntegrityHelper.create_imported_wallet(privkeys=False, config=self.config)
        wallet_online.import_address('mg2jk6S5WGDhUPA8mLSxDLWpUoQnX1zzoG')

        # bootstrap wallet_online
        funding_tx = Transaction('01000000000101197a89cff51096b9dd4214cdee0eb90cb27a25477e739521d728a679724042730100000000fdffffff048096980000000000160014dab37af8fefbbb31887a0a5f9b2698f4a7b45f6a80969800000000001976a91405a20074ef7eb42c7c6fcd4f499faa699742783288ac809698000000000017a914b808938a8007bc54509cd946944c479c0fa6554f87131b2c0400000000160014a04dfdb9a9aeac3b3fada6f43c2a66886186e2440247304402204f5dbb9dda65eab26179f1ca7c37c8baf028153815085dd1bbb2b826296e3b870220379fcd825742d6e2bdff772f347b629047824f289a5499a501033f6c3495594901210363c9c98740fe0455c646215cea9b13807b758791c8af7b74e62968bef57ff8ae1e391400')
        funding_txid = funding_tx.txid()
        self.assertEqual('0a08ea26a49e2b80f253796d605b69e2d0403fac64bdf6f7db82ada4b7bb6b62', funding_txid)
        wallet_online.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create unsigned tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1qtuynwzd0d6wptvyqmc6ehkm70zcamxpstvxpnz', 2500000)]
        tx = wallet_online.mktx(outputs=outputs, password=None, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325340
        tx.version = 1

        self.assertFalse(tx.is_complete())
        self.assertEqual(1, len(tx.inputs()))
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff0100740100000001626bbbb7a4ad82dbf7f6bd64ac3f40d0e2695b606d7953f2802b9ea426ea080a0100000000fdffffff02a0252600000000001600145f093709af6e9c15b080de359bdb7e78b1dd9830585d7200000000001976a91405a20074ef7eb42c7c6fcd4f499faa699742783288ac1c391400000100fd200101000000000101197a89cff51096b9dd4214cdee0eb90cb27a25477e739521d728a679724042730100000000fdffffff048096980000000000160014dab37af8fefbbb31887a0a5f9b2698f4a7b45f6a80969800000000001976a91405a20074ef7eb42c7c6fcd4f499faa699742783288ac809698000000000017a914b808938a8007bc54509cd946944c479c0fa6554f87131b2c0400000000160014a04dfdb9a9aeac3b3fada6f43c2a66886186e2440247304402204f5dbb9dda65eab26179f1ca7c37c8baf028153815085dd1bbb2b826296e3b870220379fcd825742d6e2bdff772f347b629047824f289a5499a501033f6c3495594901210363c9c98740fe0455c646215cea9b13807b758791c8af7b74e62968bef57ff8ae1e391400000000",
                         partial_tx)
        tx_copy = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertTrue(wallet_online.is_mine(wallet_online.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(None, tx_copy.txid())  # not segwit
        self.assertEqual(tx.txid(), tx_copy.txid())

        # sign tx
        tx = wallet_offline.sign_transaction(tx_copy, password=None)
        self.assertTrue(tx.is_complete())
        self.assertFalse(tx.is_segwit())
        self.assertEqual('4d54486e0285adb85c2edef7e540a7ad9c11c865cedf8e1b69b416e124bc9f2b', tx.txid())
        self.assertEqual('4d54486e0285adb85c2edef7e540a7ad9c11c865cedf8e1b69b416e124bc9f2b', tx.wtxid())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_offline_wif_online_addr_p2wpkh_p2sh(self, mock_save_db):
        wallet_offline = WalletIntegrityHelper.create_imported_wallet(privkeys=True, config=self.config)
        wallet_offline.import_private_key('p2wpkh-p2sh:cU9hVzhpvfn91u2zTVn8uqF2ymS7ucYH8V5TmsTDmuyMHgRk9WsJ', password=None)
        wallet_online = WalletIntegrityHelper.create_imported_wallet(privkeys=False, config=self.config)
        wallet_online.import_address('pNKeotwZ22fHrxJEVP8K4PMbxdBiw19XKa')

        # bootstrap wallet_online
        funding_tx = Transaction('01000000000101197a89cff51096b9dd4214cdee0eb90cb27a25477e739521d728a679724042730100000000fdffffff048096980000000000160014dab37af8fefbbb31887a0a5f9b2698f4a7b45f6a80969800000000001976a91405a20074ef7eb42c7c6fcd4f499faa699742783288ac809698000000000017a914b808938a8007bc54509cd946944c479c0fa6554f87131b2c0400000000160014a04dfdb9a9aeac3b3fada6f43c2a66886186e2440247304402204f5dbb9dda65eab26179f1ca7c37c8baf028153815085dd1bbb2b826296e3b870220379fcd825742d6e2bdff772f347b629047824f289a5499a501033f6c3495594901210363c9c98740fe0455c646215cea9b13807b758791c8af7b74e62968bef57ff8ae1e391400')
        funding_txid = funding_tx.txid()
        self.assertEqual('0a08ea26a49e2b80f253796d605b69e2d0403fac64bdf6f7db82ada4b7bb6b62', funding_txid)
        wallet_online.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create unsigned tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1qtuynwzd0d6wptvyqmc6ehkm70zcamxpstvxpnz', 2500000)]
        tx = wallet_online.mktx(outputs=outputs, password=None, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325340
        tx.version = 1

        self.assertFalse(tx.is_complete())
        self.assertEqual(1, len(tx.inputs()))
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff0100720100000001626bbbb7a4ad82dbf7f6bd64ac3f40d0e2695b606d7953f2802b9ea426ea080a0200000000fdffffff02a0252600000000001600145f093709af6e9c15b080de359bdb7e78b1dd9830585d72000000000017a914b808938a8007bc54509cd946944c479c0fa6554f871c391400000100fd200101000000000101197a89cff51096b9dd4214cdee0eb90cb27a25477e739521d728a679724042730100000000fdffffff048096980000000000160014dab37af8fefbbb31887a0a5f9b2698f4a7b45f6a80969800000000001976a91405a20074ef7eb42c7c6fcd4f499faa699742783288ac809698000000000017a914b808938a8007bc54509cd946944c479c0fa6554f87131b2c0400000000160014a04dfdb9a9aeac3b3fada6f43c2a66886186e2440247304402204f5dbb9dda65eab26179f1ca7c37c8baf028153815085dd1bbb2b826296e3b870220379fcd825742d6e2bdff772f347b629047824f289a5499a501033f6c3495594901210363c9c98740fe0455c646215cea9b13807b758791c8af7b74e62968bef57ff8ae1e391400000000",
                         partial_tx)
        tx_copy = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertTrue(wallet_online.is_mine(wallet_online.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(None, tx_copy.txid())  # redeem script not available
        self.assertEqual(tx.txid(), tx_copy.txid())

        # sign tx
        tx = wallet_offline.sign_transaction(tx_copy, password=None)
        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual('dfe000b6362a536c0bf8906946c0f7539eb07131da624aafe45c1b00dc5564c9', tx.txid())
        self.assertEqual('776deef21c7b5c2f04c993d8f36b4ea8c512dd0519393a08f243c222e85df201', tx.wtxid())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_offline_wif_online_addr_p2wpkh(self, mock_save_db):
        wallet_offline = WalletIntegrityHelper.create_imported_wallet(privkeys=True, config=self.config)
        wallet_offline.import_private_key('p2wpkh:cPuQzcNEgbeYZ5at9VdGkCwkPA9r34gvEVJjuoz384rTfYpahfe7', password=None)
        wallet_online = WalletIntegrityHelper.create_imported_wallet(privkeys=False, config=self.config)
        wallet_online.import_address('tmona1qm2eh4787lwanrzr6pf0ekf5c7jnmghm2jtf6kd')

        # bootstrap wallet_online
        funding_tx = Transaction('01000000000101197a89cff51096b9dd4214cdee0eb90cb27a25477e739521d728a679724042730100000000fdffffff048096980000000000160014dab37af8fefbbb31887a0a5f9b2698f4a7b45f6a80969800000000001976a91405a20074ef7eb42c7c6fcd4f499faa699742783288ac809698000000000017a914b808938a8007bc54509cd946944c479c0fa6554f87131b2c0400000000160014a04dfdb9a9aeac3b3fada6f43c2a66886186e2440247304402204f5dbb9dda65eab26179f1ca7c37c8baf028153815085dd1bbb2b826296e3b870220379fcd825742d6e2bdff772f347b629047824f289a5499a501033f6c3495594901210363c9c98740fe0455c646215cea9b13807b758791c8af7b74e62968bef57ff8ae1e391400')
        funding_txid = funding_tx.txid()
        self.assertEqual('0a08ea26a49e2b80f253796d605b69e2d0403fac64bdf6f7db82ada4b7bb6b62', funding_txid)
        wallet_online.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create unsigned tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1qtuynwzd0d6wptvyqmc6ehkm70zcamxpstvxpnz', 2500000)]
        tx = wallet_online.mktx(outputs=outputs, password=None, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325340
        tx.version = 1

        self.assertFalse(tx.is_complete())
        self.assertEqual(1, len(tx.inputs()))
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff0100710100000001626bbbb7a4ad82dbf7f6bd64ac3f40d0e2695b606d7953f2802b9ea426ea080a0000000000fdffffff02a0252600000000001600145f093709af6e9c15b080de359bdb7e78b1dd9830585d720000000000160014dab37af8fefbbb31887a0a5f9b2698f4a7b45f6a1c391400000100fd200101000000000101197a89cff51096b9dd4214cdee0eb90cb27a25477e739521d728a679724042730100000000fdffffff048096980000000000160014dab37af8fefbbb31887a0a5f9b2698f4a7b45f6a80969800000000001976a91405a20074ef7eb42c7c6fcd4f499faa699742783288ac809698000000000017a914b808938a8007bc54509cd946944c479c0fa6554f87131b2c0400000000160014a04dfdb9a9aeac3b3fada6f43c2a66886186e2440247304402204f5dbb9dda65eab26179f1ca7c37c8baf028153815085dd1bbb2b826296e3b870220379fcd825742d6e2bdff772f347b629047824f289a5499a501033f6c3495594901210363c9c98740fe0455c646215cea9b13807b758791c8af7b74e62968bef57ff8ae1e391400000000",
                         partial_tx)
        tx_copy = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertTrue(wallet_online.is_mine(wallet_online.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual('d7624c0aa86196d786fe92ea8952cce8f60d9aa3c50e55cc1bcf53ed13c289db', tx_copy.txid())
        self.assertEqual(tx.txid(), tx_copy.txid())

        # sign tx
        tx = wallet_offline.sign_transaction(tx_copy, password=None)
        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual('d7624c0aa86196d786fe92ea8952cce8f60d9aa3c50e55cc1bcf53ed13c289db', tx.txid())
        self.assertEqual('c009de753ec04cee55472e9c7c5bd117661f669b77dda60a47b81fbcb73d5084', tx.wtxid())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_offline_xprv_online_addr_p2pkh(self, mock_save_db):  # compressed pubkey
        wallet_offline = WalletIntegrityHelper.create_standard_wallet(
            # bip39: "qwe", der: m/44'/1'/0'
            keystore.from_xprv('tprv8gfKwjuAaqtHgqxMh1tosAQ28XvBMkcY5NeFRA3pZMpz6MR4H4YZ3MJM4fvNPnRKeXR1Td2vQGgjorNXfo94WvT5CYDsPAqjHxSn436G1Eu'),
            gap_limit=4,
            config=self.config
        )
        wallet_online = WalletIntegrityHelper.create_imported_wallet(privkeys=False, config=self.config)
        wallet_online.import_address('mg2jk6S5WGDhUPA8mLSxDLWpUoQnX1zzoG')

        # bootstrap wallet_online
        funding_tx = Transaction('01000000000101197a89cff51096b9dd4214cdee0eb90cb27a25477e739521d728a679724042730100000000fdffffff048096980000000000160014dab37af8fefbbb31887a0a5f9b2698f4a7b45f6a80969800000000001976a91405a20074ef7eb42c7c6fcd4f499faa699742783288ac809698000000000017a914b808938a8007bc54509cd946944c479c0fa6554f87131b2c0400000000160014a04dfdb9a9aeac3b3fada6f43c2a66886186e2440247304402204f5dbb9dda65eab26179f1ca7c37c8baf028153815085dd1bbb2b826296e3b870220379fcd825742d6e2bdff772f347b629047824f289a5499a501033f6c3495594901210363c9c98740fe0455c646215cea9b13807b758791c8af7b74e62968bef57ff8ae1e391400')
        funding_txid = funding_tx.txid()
        self.assertEqual('0a08ea26a49e2b80f253796d605b69e2d0403fac64bdf6f7db82ada4b7bb6b62', funding_txid)
        wallet_online.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create unsigned tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1qtuynwzd0d6wptvyqmc6ehkm70zcamxpstvxpnz', 2500000)]
        tx = wallet_online.mktx(outputs=outputs, password=None, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325340
        tx.version = 1

        self.assertFalse(tx.is_complete())
        self.assertEqual(1, len(tx.inputs()))
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff0100740100000001626bbbb7a4ad82dbf7f6bd64ac3f40d0e2695b606d7953f2802b9ea426ea080a0100000000fdffffff02a0252600000000001600145f093709af6e9c15b080de359bdb7e78b1dd9830585d7200000000001976a91405a20074ef7eb42c7c6fcd4f499faa699742783288ac1c391400000100fd200101000000000101197a89cff51096b9dd4214cdee0eb90cb27a25477e739521d728a679724042730100000000fdffffff048096980000000000160014dab37af8fefbbb31887a0a5f9b2698f4a7b45f6a80969800000000001976a91405a20074ef7eb42c7c6fcd4f499faa699742783288ac809698000000000017a914b808938a8007bc54509cd946944c479c0fa6554f87131b2c0400000000160014a04dfdb9a9aeac3b3fada6f43c2a66886186e2440247304402204f5dbb9dda65eab26179f1ca7c37c8baf028153815085dd1bbb2b826296e3b870220379fcd825742d6e2bdff772f347b629047824f289a5499a501033f6c3495594901210363c9c98740fe0455c646215cea9b13807b758791c8af7b74e62968bef57ff8ae1e391400000000",
                         partial_tx)
        tx_copy = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertTrue(wallet_online.is_mine(wallet_online.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(None, tx_copy.txid())  # not segwit
        self.assertEqual(tx.txid(), tx_copy.txid())

        # sign tx
        tx = wallet_offline.sign_transaction(tx_copy, password=None)
        self.assertTrue(tx.is_complete())
        self.assertFalse(tx.is_segwit())
        self.assertEqual('4d54486e0285adb85c2edef7e540a7ad9c11c865cedf8e1b69b416e124bc9f2b', tx.txid())
        self.assertEqual('4d54486e0285adb85c2edef7e540a7ad9c11c865cedf8e1b69b416e124bc9f2b', tx.wtxid())


    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_offline_xprv_online_addr_p2wpkh_p2sh(self, mock_save_db):
        wallet_offline = WalletIntegrityHelper.create_standard_wallet(
            # bip39: "qwe", der: m/49'/1'/0'
            keystore.from_xprv('uprv8zHHrMQMQ26utWwNJ5MK2SXpB9hbmy7pbPaneii69xT8cZTyFpxQFxkknGWKP8dxBTZhzy7yP6cCnLrRCQjzJDk3G61SjZpxhFQuB2NR8a5'),
            gap_limit=4,
            config=self.config
        )
        wallet_online = WalletIntegrityHelper.create_imported_wallet(privkeys=False, config=self.config)
        wallet_online.import_address('pNKeotwZ22fHrxJEVP8K4PMbxdBiw19XKa')

        # bootstrap wallet_online
        funding_tx = Transaction('01000000000101197a89cff51096b9dd4214cdee0eb90cb27a25477e739521d728a679724042730100000000fdffffff048096980000000000160014dab37af8fefbbb31887a0a5f9b2698f4a7b45f6a80969800000000001976a91405a20074ef7eb42c7c6fcd4f499faa699742783288ac809698000000000017a914b808938a8007bc54509cd946944c479c0fa6554f87131b2c0400000000160014a04dfdb9a9aeac3b3fada6f43c2a66886186e2440247304402204f5dbb9dda65eab26179f1ca7c37c8baf028153815085dd1bbb2b826296e3b870220379fcd825742d6e2bdff772f347b629047824f289a5499a501033f6c3495594901210363c9c98740fe0455c646215cea9b13807b758791c8af7b74e62968bef57ff8ae1e391400')
        funding_txid = funding_tx.txid()
        self.assertEqual('0a08ea26a49e2b80f253796d605b69e2d0403fac64bdf6f7db82ada4b7bb6b62', funding_txid)
        wallet_online.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create unsigned tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1qtuynwzd0d6wptvyqmc6ehkm70zcamxpstvxpnz', 2500000)]
        tx = wallet_online.mktx(outputs=outputs, password=None, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325340
        tx.version = 1

        self.assertFalse(tx.is_complete())
        self.assertEqual(1, len(tx.inputs()))
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff0100720100000001626bbbb7a4ad82dbf7f6bd64ac3f40d0e2695b606d7953f2802b9ea426ea080a0200000000fdffffff02a0252600000000001600145f093709af6e9c15b080de359bdb7e78b1dd9830585d72000000000017a914b808938a8007bc54509cd946944c479c0fa6554f871c391400000100fd200101000000000101197a89cff51096b9dd4214cdee0eb90cb27a25477e739521d728a679724042730100000000fdffffff048096980000000000160014dab37af8fefbbb31887a0a5f9b2698f4a7b45f6a80969800000000001976a91405a20074ef7eb42c7c6fcd4f499faa699742783288ac809698000000000017a914b808938a8007bc54509cd946944c479c0fa6554f87131b2c0400000000160014a04dfdb9a9aeac3b3fada6f43c2a66886186e2440247304402204f5dbb9dda65eab26179f1ca7c37c8baf028153815085dd1bbb2b826296e3b870220379fcd825742d6e2bdff772f347b629047824f289a5499a501033f6c3495594901210363c9c98740fe0455c646215cea9b13807b758791c8af7b74e62968bef57ff8ae1e391400000000",
                         partial_tx)
        tx_copy = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertTrue(wallet_online.is_mine(wallet_online.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(None, tx_copy.txid())  # redeem script not available
        self.assertEqual(tx.txid(), tx_copy.txid())

        # sign tx
        tx = wallet_offline.sign_transaction(tx_copy, password=None)
        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual('dfe000b6362a536c0bf8906946c0f7539eb07131da624aafe45c1b00dc5564c9', tx.txid())
        self.assertEqual('776deef21c7b5c2f04c993d8f36b4ea8c512dd0519393a08f243c222e85df201', tx.wtxid())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_offline_xprv_online_addr_p2wpkh(self, mock_save_db):
        wallet_offline = WalletIntegrityHelper.create_standard_wallet(
            # bip39: "qwe", der: m/84'/1'/0'
            keystore.from_xprv('vprv9K9hbuA23Bidgj1KRSHUZMa59jJLeZBpXPVn4RP7sBLArNhZxJjw4AX7aQmVTErDt4YFC11ptMLjbwxgrsH8GLQ1cx77KggWeVPeDBjr9xM'),
            gap_limit=4,
            config=self.config
        )
        wallet_online = WalletIntegrityHelper.create_imported_wallet(privkeys=False, config=self.config)
        wallet_online.import_address('tmona1qm2eh4787lwanrzr6pf0ekf5c7jnmghm2jtf6kd')

        # bootstrap wallet_online
        funding_tx = Transaction('01000000000101197a89cff51096b9dd4214cdee0eb90cb27a25477e739521d728a679724042730100000000fdffffff048096980000000000160014dab37af8fefbbb31887a0a5f9b2698f4a7b45f6a80969800000000001976a91405a20074ef7eb42c7c6fcd4f499faa699742783288ac809698000000000017a914b808938a8007bc54509cd946944c479c0fa6554f87131b2c0400000000160014a04dfdb9a9aeac3b3fada6f43c2a66886186e2440247304402204f5dbb9dda65eab26179f1ca7c37c8baf028153815085dd1bbb2b826296e3b870220379fcd825742d6e2bdff772f347b629047824f289a5499a501033f6c3495594901210363c9c98740fe0455c646215cea9b13807b758791c8af7b74e62968bef57ff8ae1e391400')
        funding_txid = funding_tx.txid()
        self.assertEqual('0a08ea26a49e2b80f253796d605b69e2d0403fac64bdf6f7db82ada4b7bb6b62', funding_txid)
        wallet_online.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create unsigned tx
        outputs = [PartialTxOutput.from_address_and_value('tmona1qtuynwzd0d6wptvyqmc6ehkm70zcamxpstvxpnz', 2500000)]
        tx = wallet_online.mktx(outputs=outputs, password=None, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325340
        tx.version = 1

        self.assertFalse(tx.is_complete())
        self.assertEqual(1, len(tx.inputs()))
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff0100710100000001626bbbb7a4ad82dbf7f6bd64ac3f40d0e2695b606d7953f2802b9ea426ea080a0000000000fdffffff02a0252600000000001600145f093709af6e9c15b080de359bdb7e78b1dd9830585d720000000000160014dab37af8fefbbb31887a0a5f9b2698f4a7b45f6a1c391400000100fd200101000000000101197a89cff51096b9dd4214cdee0eb90cb27a25477e739521d728a679724042730100000000fdffffff048096980000000000160014dab37af8fefbbb31887a0a5f9b2698f4a7b45f6a80969800000000001976a91405a20074ef7eb42c7c6fcd4f499faa699742783288ac809698000000000017a914b808938a8007bc54509cd946944c479c0fa6554f87131b2c0400000000160014a04dfdb9a9aeac3b3fada6f43c2a66886186e2440247304402204f5dbb9dda65eab26179f1ca7c37c8baf028153815085dd1bbb2b826296e3b870220379fcd825742d6e2bdff772f347b629047824f289a5499a501033f6c3495594901210363c9c98740fe0455c646215cea9b13807b758791c8af7b74e62968bef57ff8ae1e391400000000",
                         partial_tx)
        tx_copy = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertTrue(wallet_online.is_mine(wallet_online.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual('d7624c0aa86196d786fe92ea8952cce8f60d9aa3c50e55cc1bcf53ed13c289db', tx_copy.txid())
        self.assertEqual(tx.txid(), tx_copy.txid())

        # sign tx
        tx = wallet_offline.sign_transaction(tx_copy, password=None)
        self.assertTrue(tx.is_complete())
        self.assertTrue(tx.is_segwit())
        self.assertEqual('d7624c0aa86196d786fe92ea8952cce8f60d9aa3c50e55cc1bcf53ed13c289db', tx.txid())
        self.assertEqual('c009de753ec04cee55472e9c7c5bd117661f669b77dda60a47b81fbcb73d5084', tx.wtxid())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_offline_hd_multisig_online_addr_p2sh(self, mock_save_db):
        # 2-of-3 legacy p2sh multisig
        wallet_offline1 = WalletIntegrityHelper.create_multisig_wallet(
            [
                keystore.from_seed('blast uniform dragon fiscal ensure vast young utility dinosaur abandon rookie sure', '', True),
                keystore.from_xpub('tpubD6NzVbkrYhZ4YTPEgwk4zzr8wyo7pXGmbbVUnfYNtx6SgAMF5q3LN3Kch58P9hxGNsTmP7Dn49nnrmpE6upoRb1Xojg12FGLuLHkVpVtS44'),
                keystore.from_xpub('tpubD6NzVbkrYhZ4XJzYkhsCbDCcZRmDAKSD7bXi9mdCni7acVt45fxbTVZyU6jRGh29ULKTjoapkfFsSJvQHitcVKbQgzgkkYsAmaovcro7Mhf')
            ],
            '2of3', gap_limit=2,
            config=self.config
        )
        wallet_offline2 = WalletIntegrityHelper.create_multisig_wallet(
            [
                keystore.from_seed('cycle rocket west magnet parrot shuffle foot correct salt library feed song', '', True),
                keystore.from_xpub('tpubD6NzVbkrYhZ4YTPEgwk4zzr8wyo7pXGmbbVUnfYNtx6SgAMF5q3LN3Kch58P9hxGNsTmP7Dn49nnrmpE6upoRb1Xojg12FGLuLHkVpVtS44'),
                keystore.from_xpub('tpubD6NzVbkrYhZ4YARFMEZPckrqJkw59GZD1PXtQnw14ukvWDofR7Z1HMeSCxfYEZVvg4VdZ8zGok5VxHwdrLqew5cMdQntWc5mT7mh1CSgrnX')
            ],
            '2of3', gap_limit=2,
            config=self.config
        )
        wallet_online = WalletIntegrityHelper.create_imported_wallet(privkeys=False, config=self.config)
        wallet_online.import_address('pHHPM4uZXFrMBRtqG4MFfdPNnVzGd9TPse')

        # bootstrap wallet_online
        funding_tx = Transaction('010000000001016207d958dc46508d706e4cd7d3bc46c5c2b02160e2578e5fad2efafc3927050301000000171600147a4fc8cdc1c2cf7abbcd88ef6d880e59269797acfdffffff02809698000000000017a91480c2353f6a7bc3c71e99e062655b19adb3dd2e48870d0916020000000017a914703f83ef20f3a52d908475dcad00c5144164d5a2870247304402203b1a5cb48cadeee14fa6c7bbf2bc581ca63104762ec5c37c703df778884cc5b702203233fa53a2a0bfbd85617c636e415da72214e359282cce409019319d031766c50121021112c01a48cc7ea13cba70493c6bffebb3e805df10ff4611d2bf559d26e25c04bf391400')
        funding_txid = funding_tx.txid()
        self.assertEqual('c59913a1fa9b1ef1f6928f0db490be67eeb9d7cb05aa565ee647e859642f3532', funding_txid)
        wallet_online.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create unsigned tx
        outputs = [PartialTxOutput.from_address_and_value('2MuCQQHJNnrXzQzuqfUCfAwAjPqpyEHbgue', 2500000)]
        tx = wallet_online.mktx(outputs=outputs, password=None, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325503
        tx.version = 1

        self.assertFalse(tx.is_complete())
        self.assertEqual(1, len(tx.inputs()))
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff010073010000000132352f6459e847e65e56aa05cbd7b9ee67be90b40d8f92f6f11e9bfaa11399c50000000000fdffffff02a02526000000000017a9141567b2578f300fa618ef0033611fd67087aff6d187585d72000000000017a91480c2353f6a7bc3c71e99e062655b19adb3dd2e4887bf391400000100f7010000000001016207d958dc46508d706e4cd7d3bc46c5c2b02160e2578e5fad2efafc3927050301000000171600147a4fc8cdc1c2cf7abbcd88ef6d880e59269797acfdffffff02809698000000000017a91480c2353f6a7bc3c71e99e062655b19adb3dd2e48870d0916020000000017a914703f83ef20f3a52d908475dcad00c5144164d5a2870247304402203b1a5cb48cadeee14fa6c7bbf2bc581ca63104762ec5c37c703df778884cc5b702203233fa53a2a0bfbd85617c636e415da72214e359282cce409019319d031766c50121021112c01a48cc7ea13cba70493c6bffebb3e805df10ff4611d2bf559d26e25c04bf391400000000",
                         partial_tx)
        tx_copy = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertTrue(wallet_online.is_mine(wallet_online.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(None, tx_copy.txid())  # not segwit
        self.assertEqual(tx.txid(), tx_copy.txid())

        # sign tx - first
        tx = wallet_offline1.sign_transaction(tx_copy, password=None)
        self.assertFalse(tx.is_complete())
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff010073010000000132352f6459e847e65e56aa05cbd7b9ee67be90b40d8f92f6f11e9bfaa11399c50000000000fdffffff02a02526000000000017a9141567b2578f300fa618ef0033611fd67087aff6d187585d72000000000017a91480c2353f6a7bc3c71e99e062655b19adb3dd2e4887bf391400000100f7010000000001016207d958dc46508d706e4cd7d3bc46c5c2b02160e2578e5fad2efafc3927050301000000171600147a4fc8cdc1c2cf7abbcd88ef6d880e59269797acfdffffff02809698000000000017a91480c2353f6a7bc3c71e99e062655b19adb3dd2e48870d0916020000000017a914703f83ef20f3a52d908475dcad00c5144164d5a2870247304402203b1a5cb48cadeee14fa6c7bbf2bc581ca63104762ec5c37c703df778884cc5b702203233fa53a2a0bfbd85617c636e415da72214e359282cce409019319d031766c50121021112c01a48cc7ea13cba70493c6bffebb3e805df10ff4611d2bf559d26e25c04bf391400220202afb4af9a91264e1c6dce3ebe5312801723270ac0ba8134b7b49129328fcb0f284730440220451f77cb18224adcb4981492d9be2c3fa7537f94f4b29eb405992dbdd5df04aa022071e6759d40dde810caa01ca7f16bad3cb742d64428c419c8fb4bad6f1c3f718101010469522102afb4af9a91264e1c6dce3ebe5312801723270ac0ba8134b7b49129328fcb0f2821030b482838721a38d94847699fed8818b5c5f56500ef72f13489e365b65e5749cf2103e5db7969ae2f2576e6a061bf3bb2db16571e77ffb41e0b27170734359235cbce53ae220602afb4af9a91264e1c6dce3ebe5312801723270ac0ba8134b7b49129328fcb0f280c0036e9ac00000000000000002206030b482838721a38d94847699fed8818b5c5f56500ef72f13489e365b65e5749cf0c48adc7a00000000000000000220603e5db7969ae2f2576e6a061bf3bb2db16571e77ffb41e0b27170734359235cbce0cdb69242700000000000000000000010069522102afb4af9a91264e1c6dce3ebe5312801723270ac0ba8134b7b49129328fcb0f2821030b482838721a38d94847699fed8818b5c5f56500ef72f13489e365b65e5749cf2103e5db7969ae2f2576e6a061bf3bb2db16571e77ffb41e0b27170734359235cbce53ae220202afb4af9a91264e1c6dce3ebe5312801723270ac0ba8134b7b49129328fcb0f280c0036e9ac00000000000000002202030b482838721a38d94847699fed8818b5c5f56500ef72f13489e365b65e5749cf0c48adc7a00000000000000000220203e5db7969ae2f2576e6a061bf3bb2db16571e77ffb41e0b27170734359235cbce0cdb692427000000000000000000",
                         partial_tx)
        tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners

        # sign tx - second
        tx = wallet_offline2.sign_transaction(tx, password=None)
        self.assertTrue(tx.is_complete())
        tx = tx_from_any(tx.serialize())

        self.assertEqual('010000000132352f6459e847e65e56aa05cbd7b9ee67be90b40d8f92f6f11e9bfaa11399c500000000fc004730440220451f77cb18224adcb4981492d9be2c3fa7537f94f4b29eb405992dbdd5df04aa022071e6759d40dde810caa01ca7f16bad3cb742d64428c419c8fb4bad6f1c3f718101473044022052980154bdf2e43d6bd8775316cc220ef5ae13b4b9574a7a904a691ee3c5efd3022069b3eddf904cc645bd8fc8b2aaa7aaf7eb5bbfb7bbbd3b6e6cd89b37dfb2856c014c69522102afb4af9a91264e1c6dce3ebe5312801723270ac0ba8134b7b49129328fcb0f2821030b482838721a38d94847699fed8818b5c5f56500ef72f13489e365b65e5749cf2103e5db7969ae2f2576e6a061bf3bb2db16571e77ffb41e0b27170734359235cbce53aefdffffff02a02526000000000017a9141567b2578f300fa618ef0033611fd67087aff6d187585d72000000000017a91480c2353f6a7bc3c71e99e062655b19adb3dd2e4887bf391400',
                         str(tx))
        self.assertEqual('0e8fdc8257a85ebe7eeab14a53c2c258c61a511f64176b7f8fc016bc2263d307', tx.txid())
        self.assertEqual('0e8fdc8257a85ebe7eeab14a53c2c258c61a511f64176b7f8fc016bc2263d307', tx.wtxid())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_offline_hd_multisig_online_addr_p2wsh_p2sh(self, mock_save_db):
        # 2-of-2 p2sh-embedded segwit multisig
        wallet_offline1 = WalletIntegrityHelper.create_multisig_wallet(
            [
                # bip39: finish seminar arrange erosion sunny coil insane together pretty lunch lunch rose, der: m/1234'/1'/0', p2wsh-p2sh multisig
                keystore.from_xprv('Uprv9CvELvByqm8k2dpecJVjgLMX1z5DufEjY4fBC5YvdGF5WjGCa7GVJJ2fYni1tyuF7Hw83E6W2ZBjAhaFLZv2ri3rEsubkCd5avg4EHKoDBN'),
                keystore.from_xpub('Upub5Qb8ik4Cnu8g97KLXKgVXHqY6tH8emQvqtBncjSKsyfTZuorPtTZgX7ovKKZHuuVGBVd1MTTBkWez1XXt2weN1sWBz6SfgRPQYEkNgz81QF')
            ],
            '2of2', gap_limit=2,
            config=self.config
        )
        wallet_offline2 = WalletIntegrityHelper.create_multisig_wallet(
            [
                # bip39: square page wood spy oil story rebel give milk screen slide shuffle, der: m/1234'/1'/0', p2wsh-p2sh multisig
                keystore.from_xprv('Uprv9BbnKEXJxXaNvdEsRJ9VA9toYrSeFJh5UfGBpM2iKe8Uh7UhrM9K8ioL53s8gvCoGfirHHaqpABDAE7VUNw8LNU1DMJKVoWyeNKu9XcDC19'),
                keystore.from_xpub('Upub5RuakRisg8h3F7u7iL2k3UJFa1uiK7xauHamzTxYBbn4PXbM7eajr6M9Q2VCr6cVGhfhqWQqxnABvtSATuVM1xzxk4nA189jJwzaMn1QX7V')
            ],
            '2of2', gap_limit=2,
            config=self.config
        )
        wallet_online = WalletIntegrityHelper.create_imported_wallet(privkeys=False, config=self.config)
        wallet_online.import_address('p5akeBU4HTVHGXWhVpEBJHxUg3m1Sf3p5Y')

        # bootstrap wallet_online
        funding_tx = Transaction('0100000000010118d494d28e5c3bf61566ca0313e22c3b561b888a317d689cc8b47b947adebd440000000017160014aec84704ea8508ddb94a3c6e53f0992d33a2a529fdffffff020f0925000000000017a91409f7aae0265787a02de22839d41e9c927768230287809698000000000017a91400698bd11c38f887f17c99846d9be96321fbf989870247304402206b906369f4075ebcfc149f7429dcfc34e11e1b7bbfc85d1185d5e9c324be0d3702203ce7fc12fd3131920fbcbb733250f05dbf7d03e18a4656232ee69d5c54dd46bd0121028a4b697a37f3f57f6e53f90db077fa9696095b277454fda839c211d640d48649c0391400')
        funding_txid = funding_tx.txid()
        self.assertEqual('54356de9e156b85c8516fd4d51bdb68b5513f58b4a6147483978ae254627ee3e', funding_txid)
        wallet_online.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create unsigned tx
        outputs = [PartialTxOutput.from_address_and_value('2N8CtJRwxb2GCaiWWdSHLZHHLoZy53CCyxf', 2500000)]
        tx = wallet_online.mktx(outputs=outputs, password=None, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325504
        tx.version = 1

        self.assertFalse(tx.is_complete())
        self.assertEqual(1, len(tx.inputs()))
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff01007301000000013eee274625ae78394847614a8bf513558bb6bd514dfd16855cb856e1e96d35540100000000fdffffff02a02526000000000017a914a4189ef02c95cfe36f8e880c6cb54dff0837b22687585d72000000000017a91400698bd11c38f887f17c99846d9be96321fbf98987c0391400000100f70100000000010118d494d28e5c3bf61566ca0313e22c3b561b888a317d689cc8b47b947adebd440000000017160014aec84704ea8508ddb94a3c6e53f0992d33a2a529fdffffff020f0925000000000017a91409f7aae0265787a02de22839d41e9c927768230287809698000000000017a91400698bd11c38f887f17c99846d9be96321fbf989870247304402206b906369f4075ebcfc149f7429dcfc34e11e1b7bbfc85d1185d5e9c324be0d3702203ce7fc12fd3131920fbcbb733250f05dbf7d03e18a4656232ee69d5c54dd46bd0121028a4b697a37f3f57f6e53f90db077fa9696095b277454fda839c211d640d48649c0391400000000",
                         partial_tx)
        tx_copy = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertTrue(wallet_online.is_mine(wallet_online.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual(None, tx_copy.txid())  # redeem script not available
        self.assertEqual(tx.txid(), tx_copy.txid())

        # sign tx - first
        tx = wallet_offline1.sign_transaction(tx_copy, password=None)
        self.assertFalse(tx.is_complete())
        self.assertEqual('6a58a51591142429203b62b6ddf6b799a6926882efac229998c51bee6c3573eb', tx.txid())
        partial_tx = tx.serialize_as_bytes().hex()
        # note re PSBT: online wallet had put a NON-WITNESS UTXO for input0, as they did not know if it was segwit.
        #               offline wallet now replaced this with a WITNESS-UTXO.
        #               this switch is needed to interop with bitcoin core... https://github.com/bitcoin/bitcoin/blob/fba574c908bb61eff1a0e83c935f3526ba9035f2/src/psbt.cpp#L163
        self.assertEqual("70736274ff01007301000000013eee274625ae78394847614a8bf513558bb6bd514dfd16855cb856e1e96d35540100000000fdffffff02a02526000000000017a914a4189ef02c95cfe36f8e880c6cb54dff0837b22687585d72000000000017a91400698bd11c38f887f17c99846d9be96321fbf98987c0391400000100f70100000000010118d494d28e5c3bf61566ca0313e22c3b561b888a317d689cc8b47b947adebd440000000017160014aec84704ea8508ddb94a3c6e53f0992d33a2a529fdffffff020f0925000000000017a91409f7aae0265787a02de22839d41e9c927768230287809698000000000017a91400698bd11c38f887f17c99846d9be96321fbf989870247304402206b906369f4075ebcfc149f7429dcfc34e11e1b7bbfc85d1185d5e9c324be0d3702203ce7fc12fd3131920fbcbb733250f05dbf7d03e18a4656232ee69d5c54dd46bd0121028a4b697a37f3f57f6e53f90db077fa9696095b277454fda839c211d640d48649c0391400220202d3f47041b424a84898e315cc8ef58190f6aec79c178c12de0790890ba7166e9c4730440220234f6648c5741eb195f0f4cd645298a10ce02f6ef557d05df93331e21c4f58cb022058ce2af0de1c238c4a8dd3b3c7a9a0da6e381ddad7593cddfc0480f9fe5baadf0101042200206ee8d4bb1277b7dbe1d4e49b880993aa993f417a9101cb23865c7c7258732704010547522102975c00f6af579f9a1d283f1e5a43032deadbab2308aef30fb307c0cfe54777462102d3f47041b424a84898e315cc8ef58190f6aec79c178c12de0790890ba7166e9c52ae220602975c00f6af579f9a1d283f1e5a43032deadbab2308aef30fb307c0cfe54777460c17cea9140000000001000000220602d3f47041b424a84898e315cc8ef58190f6aec79c178c12de0790890ba7166e9c0cd1dbcc210000000001000000000001002200206ee8d4bb1277b7dbe1d4e49b880993aa993f417a9101cb23865c7c7258732704010147522102975c00f6af579f9a1d283f1e5a43032deadbab2308aef30fb307c0cfe54777462102d3f47041b424a84898e315cc8ef58190f6aec79c178c12de0790890ba7166e9c52ae220202975c00f6af579f9a1d283f1e5a43032deadbab2308aef30fb307c0cfe54777460c17cea9140000000001000000220202d3f47041b424a84898e315cc8ef58190f6aec79c178c12de0790890ba7166e9c0cd1dbcc21000000000100000000",
                         partial_tx)
        tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners

        # sign tx - second
        tx = wallet_offline2.sign_transaction(tx, password=None)
        self.assertTrue(tx.is_complete())
        tx = tx_from_any(tx.serialize())

        self.assertEqual('010000000001013eee274625ae78394847614a8bf513558bb6bd514dfd16855cb856e1e96d355401000000232200206ee8d4bb1277b7dbe1d4e49b880993aa993f417a9101cb23865c7c7258732704fdffffff02a02526000000000017a914a4189ef02c95cfe36f8e880c6cb54dff0837b22687585d72000000000017a91400698bd11c38f887f17c99846d9be96321fbf98987040047304402205a9dd9eb5676196893fb08f60079a2e9f567ee39614075d8c5d9fab0f11cbbc7022039640855188ebb7bccd9e3f00b397a888766d42d00d006f1ca7457c15449285f014730440220234f6648c5741eb195f0f4cd645298a10ce02f6ef557d05df93331e21c4f58cb022058ce2af0de1c238c4a8dd3b3c7a9a0da6e381ddad7593cddfc0480f9fe5baadf0147522102975c00f6af579f9a1d283f1e5a43032deadbab2308aef30fb307c0cfe54777462102d3f47041b424a84898e315cc8ef58190f6aec79c178c12de0790890ba7166e9c52aec0391400',
                         str(tx))
        self.assertEqual('6a58a51591142429203b62b6ddf6b799a6926882efac229998c51bee6c3573eb', tx.txid())
        self.assertEqual('96d0bca1001778c54e4c3a07929fab5562c5b5a23fd1ca3aa3870cc5df2bf97d', tx.wtxid())

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_sending_offline_hd_multisig_online_addr_p2wsh(self, mock_save_db):
        # 2-of-3 p2wsh multisig
        wallet_offline1 = WalletIntegrityHelper.create_multisig_wallet(
            [
                keystore.from_seed('bitter grass shiver impose acquire brush forget axis eager alone wine silver', '', True),
                keystore.from_xpub('Vpub5fcdcgEwTJmbmqAktuK8Kyq92fMf7sWkcP6oqAii2tG47dNbfkGEGUbfS9NuZaRywLkHE6EmUksrqo32ZL3ouLN1HTar6oRiHpDzKMAF1tf'),
                keystore.from_xpub('Vpub5fjkKyYnvSS4wBuakWTkNvZDaBM2vQ1MeXWq368VJHNr2eT8efqhpmZ6UUkb7s2dwCXv2Vuggjdhk4vZVyiAQTwUftvff73XcUGq2NQmWra')
            ],
            '2of3', gap_limit=2,
            config=self.config
        )
        wallet_offline2 = WalletIntegrityHelper.create_multisig_wallet(
            [
                keystore.from_seed('snow nest raise royal more walk demise rotate smooth spirit canyon gun', '', True),
                keystore.from_xpub('Vpub5fjkKyYnvSS4wBuakWTkNvZDaBM2vQ1MeXWq368VJHNr2eT8efqhpmZ6UUkb7s2dwCXv2Vuggjdhk4vZVyiAQTwUftvff73XcUGq2NQmWra'),
                keystore.from_xpub('Vpub5gSKXzxK7FeKQedu2q1z9oJWxqvX72AArW3HSWpEhc8othDH8xMDu28gr7gf17sp492BuJod8Tn7anjvJrKpETwqnQqX7CS8fcYyUtedEMk')
            ],
            '2of3', gap_limit=2,
            config=self.config
        )
        # ^ third seed: hedgehog sunset update estate number jungle amount piano friend donate upper wool
        wallet_online = WalletIntegrityHelper.create_imported_wallet(privkeys=False, config=self.config)
        wallet_online.import_address('tmona1q83p6eqxkuvq4eumcha46crpzg4nj84s9p0hnynkxg8nhvfzqcc7q5kct9k')

        # bootstrap wallet_online
        funding_tx = Transaction('0100000000010132352f6459e847e65e56aa05cbd7b9ee67be90b40d8f92f6f11e9bfaa11399c501000000171600142e5d579693b2a7679622935df94d9f3c84909b24fdffffff0280969800000000002200203c43ac80d6e3015cf378bf6bac0c22456723d6050bef324ec641e7762440c63c83717d010000000017a91441b772909ad301b41b76f4a3c5058888a7fe6f9a8702483045022100de54689f74b8efcce7fdc91e40761084686003bcd56c886ee97e75a7e803526102204dea51ae5e7d01bd56a8c336c64841f7fe02a8b101fa892e13f2d079bb14e6bf012102024e2f73d632c49f4b821ccd3b6da66b155427b1e5b1c4688cefd5a4b4bfa404c1391400')
        funding_txid = funding_tx.txid()
        self.assertEqual('643a7ab9083d0227dd9df314ce56b18d279e6018ff975079dfaab82cd7a66fa3', funding_txid)
        wallet_online.receive_tx_callback(funding_txid, funding_tx, TX_HEIGHT_UNCONFIRMED)

        # create unsigned tx
        outputs = [PartialTxOutput.from_address_and_value('2MyoZVy8T1t94yLmyKu8DP1SmbWvnxbkwRA', 2500000)]
        tx = wallet_online.mktx(outputs=outputs, password=None, fee=5000)
        tx.set_rbf(True)
        tx.locktime = 1325505
        tx.version = 1

        self.assertFalse(tx.is_complete())
        self.assertEqual(1, len(tx.inputs()))
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff01007e0100000001a36fa6d72cb8aadf795097ff18609e278db156ce14f39ddd27023d08b97a3a640000000000fdffffff02a02526000000000017a91447ee5a659f6ffb53f7e3afc1681b6415f3c00fa187585d7200000000002200203c43ac80d6e3015cf378bf6bac0c22456723d6050bef324ec641e7762440c63cc1391400000100fd03010100000000010132352f6459e847e65e56aa05cbd7b9ee67be90b40d8f92f6f11e9bfaa11399c501000000171600142e5d579693b2a7679622935df94d9f3c84909b24fdffffff0280969800000000002200203c43ac80d6e3015cf378bf6bac0c22456723d6050bef324ec641e7762440c63c83717d010000000017a91441b772909ad301b41b76f4a3c5058888a7fe6f9a8702483045022100de54689f74b8efcce7fdc91e40761084686003bcd56c886ee97e75a7e803526102204dea51ae5e7d01bd56a8c336c64841f7fe02a8b101fa892e13f2d079bb14e6bf012102024e2f73d632c49f4b821ccd3b6da66b155427b1e5b1c4688cefd5a4b4bfa404c1391400000000",
                         partial_tx)
        tx_copy = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners
        self.assertTrue(wallet_online.is_mine(wallet_online.get_txin_address(tx_copy.inputs()[0])))

        self.assertEqual('32e946761b4e718c1fa8d044db9e72d5831f6395eb284faf2fb5c4af0743e501', tx_copy.txid())
        self.assertEqual(tx.txid(), tx_copy.txid())

        # sign tx - first
        tx = wallet_offline1.sign_transaction(tx_copy, password=None)
        self.assertFalse(tx.is_complete())
        self.assertEqual('32e946761b4e718c1fa8d044db9e72d5831f6395eb284faf2fb5c4af0743e501', tx.txid())
        partial_tx = tx.serialize_as_bytes().hex()
        self.assertEqual("70736274ff01007e0100000001a36fa6d72cb8aadf795097ff18609e278db156ce14f39ddd27023d08b97a3a640000000000fdffffff02a02526000000000017a91447ee5a659f6ffb53f7e3afc1681b6415f3c00fa187585d7200000000002200203c43ac80d6e3015cf378bf6bac0c22456723d6050bef324ec641e7762440c63cc1391400000100fd03010100000000010132352f6459e847e65e56aa05cbd7b9ee67be90b40d8f92f6f11e9bfaa11399c501000000171600142e5d579693b2a7679622935df94d9f3c84909b24fdffffff0280969800000000002200203c43ac80d6e3015cf378bf6bac0c22456723d6050bef324ec641e7762440c63c83717d010000000017a91441b772909ad301b41b76f4a3c5058888a7fe6f9a8702483045022100de54689f74b8efcce7fdc91e40761084686003bcd56c886ee97e75a7e803526102204dea51ae5e7d01bd56a8c336c64841f7fe02a8b101fa892e13f2d079bb14e6bf012102024e2f73d632c49f4b821ccd3b6da66b155427b1e5b1c4688cefd5a4b4bfa404c139140022020223f815ab09f6bfc8519165c5232947ae89d9d43d678fb3486f3b28382a2371fa4730440220629d89626585f563202e6b38ceddc26ccd00737e0b7ee4239b9266ef9174ea2f02200b74828399a2e35ed46c9b484af4817438d5fea890606ebb201b821944db1fdc0101056952210223f815ab09f6bfc8519165c5232947ae89d9d43d678fb3486f3b28382a2371fa210273c529c2c9a99592f2066cebc2172a48991af2b471cb726b9df78c6497ce984e2102aa8fc578b445a1e4257be6b978fcece92980def98dce0e1eb89e7364635ae94153ae22060223f815ab09f6bfc8519165c5232947ae89d9d43d678fb3486f3b28382a2371fa10b2e35a7d01000080000000000000000022060273c529c2c9a99592f2066cebc2172a48991af2b471cb726b9df78c6497ce984e1053b77ddb010000800000000000000000220602aa8fc578b445a1e4257be6b978fcece92980def98dce0e1eb89e7364635ae9411043067d63010000800000000000000000000001016952210223f815ab09f6bfc8519165c5232947ae89d9d43d678fb3486f3b28382a2371fa210273c529c2c9a99592f2066cebc2172a48991af2b471cb726b9df78c6497ce984e2102aa8fc578b445a1e4257be6b978fcece92980def98dce0e1eb89e7364635ae94153ae22020223f815ab09f6bfc8519165c5232947ae89d9d43d678fb3486f3b28382a2371fa10b2e35a7d01000080000000000000000022020273c529c2c9a99592f2066cebc2172a48991af2b471cb726b9df78c6497ce984e1053b77ddb010000800000000000000000220202aa8fc578b445a1e4257be6b978fcece92980def98dce0e1eb89e7364635ae9411043067d6301000080000000000000000000",
                         partial_tx)
        tx = tx_from_any(partial_tx)  # simulates moving partial txn between cosigners

        # sign tx - second
        tx = wallet_offline2.sign_transaction(tx, password=None)
        self.assertTrue(tx.is_complete())
        tx = tx_from_any(tx.serialize())

        self.assertEqual('01000000000101a36fa6d72cb8aadf795097ff18609e278db156ce14f39ddd27023d08b97a3a640000000000fdffffff02a02526000000000017a91447ee5a659f6ffb53f7e3afc1681b6415f3c00fa187585d7200000000002200203c43ac80d6e3015cf378bf6bac0c22456723d6050bef324ec641e7762440c63c04004730440220629d89626585f563202e6b38ceddc26ccd00737e0b7ee4239b9266ef9174ea2f02200b74828399a2e35ed46c9b484af4817438d5fea890606ebb201b821944db1fdc0147304402205d1a59c84c419992069e9764a7992abca6a812cc5dfd4f0d6515d4283e660ce802202597a38899f31545aaf305629bd488f36bf54e4a05fe983932cafbb3906efb8f016952210223f815ab09f6bfc8519165c5232947ae89d9d43d678fb3486f3b28382a2371fa210273c529c2c9a99592f2066cebc2172a48991af2b471cb726b9df78c6497ce984e2102aa8fc578b445a1e4257be6b978fcece92980def98dce0e1eb89e7364635ae94153aec1391400',
                         str(tx))
        self.assertEqual('32e946761b4e718c1fa8d044db9e72d5831f6395eb284faf2fb5c4af0743e501', tx.txid())
        self.assertEqual('4376fa5f1f6cb37b1f3956175d3bd4ef6882169294802b250a3c672f3ff431c1', tx.wtxid())


class TestWalletHistory_SimpleRandomOrder(TestCaseForTestnet):
    transactions = {
        "0f4972c84974b908a58dda2614b68cf037e6c03e8291898c719766f213217b67": "01000000029d1bdbe67f0bd0d7bd700463f5c29302057c7b52d47de9e2ca5069761e139da2000000008b483045022100a146a2078a318c1266e42265a369a8eef8993750cb3faa8dd80754d8d541d5d202207a6ab8864986919fd1a7fd5854f1e18a8a0431df924d7a878ec3dc283e3d75340141045f7ba332df2a7b4f5d13f246e307c9174cfa9b8b05f3b83410a3c23ef8958d610be285963d67c7bc1feb082f168fa9877c25999963ff8b56b242a852b23e25edfeffffff9d1bdbe67f0bd0d7bd700463f5c29302057c7b52d47de9e2ca5069761e139da2010000008a47304402201c7fa37b74a915668b0244c01f14a9756bbbec1031fb69390bcba236148ab37e02206151581f9aa0e6758b503064c1e661a726d75c6be3364a5a121a8c12cf618f64014104dc28da82e141416aaf771eb78128d00a55fdcbd13622afcbb7a3b911e58baa6a99841bfb7b99bcb7e1d47904fda5d13fdf9675cdbbe73e44efcc08165f49bac6feffffff02b0183101000000001976a914ca14915184a2662b5d1505ce7142c8ca066c70e288ac005a6202000000001976a9145eb4eeaefcf9a709f8671444933243fbd05366a388ac54c51200",
        "2791cdc98570cc2b6d9d5b197dc2d002221b074101e3becb19fab4b79150446d": "010000000132201ff125888a326635a2fc6e971cd774c4d0c1a757d742d0f6b5b020f7203a050000006a47304402201d20bb5629a35b84ff9dd54788b98e265623022894f12152ac0e6158042550fe02204e98969e1f7043261912dd0660d3da64e15acf5435577fc02a00eccfe76b323f012103a336ad86546ab66b6184238fe63bb2955314be118b32fa45dd6bd9c4c5875167fdffffff0254959800000000001976a9148d2db0eb25b691829a47503006370070bc67400588ac80969800000000001976a914f96669095e6df76cfdf5c7e49a1909f002e123d088ace8ca1200",
        "2d216451b20b6501e927d85244bcc1c7c70598332717df91bb571359c358affd": "010000000001036cdf8d2226c57d7cc8485636d8e823c14790d5f24e6cf38ba9323babc7f6db2901000000171600143fc0dbdc2f939c322aed5a9c3544468ec17f5c3efdffffff507dce91b2a8731636e058ccf252f02b5599489b624e003435a29b9862ccc38c0200000017160014c50ff91aa2a790b99aa98af039ae1b156e053375fdffffff6254162cf8ace3ddfb3ec242b8eade155fa91412c5bde7f55decfac5793743c1010000008b483045022100de9599dcd7764ca8d4fcbe39230602e130db296c310d4abb7f7ae4d139c4d46402200fbfd8e6dc94d90afa05b0c0eab3b84feb465754db3f984fbf059447282771c30141045eecefd39fabba7b0098c3d9e85794e652bdbf094f3f85a3de97a249b98b9948857ea1e8209ee4f196a6bbcfbad103a38698ee58766321ba1cdee0cbfb60e7b2fdffffff01e85af70100000000160014e8d29f07cd5f813317bec4defbef337942d85d74024730440220218049aee7bbd34a7fa17f972a8d24a0469b0131d943ef3e30860401eaa2247402203495973f006e6ee6ae74a83228623029f238f37390ee4b587d95cdb1d1aaee9901210392ba263f3a2b260826943ff0df25e9ca4ef603b98b0a916242c947ae0626575f02473044022002603e5ceabb4406d11aedc0cccbf654dd391ce68b6b2228a40e51cf8129310d0220533743120d93be8b6c1453973935b911b0a2322e74708d23e8b5f90e74b0f192012103221b4ee0f508ba595fc1b9c2252ed9d03e99c73b97344dae93263c68834f034800ed161300",
        "31494e7e9f42f4bd736769b07cc602e2a1019617b2c72a03ec945b667aada78f": "0100000000010454022b1b4d3b45e7fcac468de2d6df890a9f41050c05d80e68d4b083f728e76a000000008b483045022100ea8fe74db2aba23ad36ac66aaa481bad2b4d1b3c331869c1d60a28ce8cfad43c02206fa817281b33fbf74a6dd7352bdc5aa1d6d7966118a4ad5b7e153f37205f1ae80141045f7ba332df2a7b4f5d13f246e307c9174cfa9b8b05f3b83410a3c23ef8958d610be285963d67c7bc1feb082f168fa9877c25999963ff8b56b242a852b23e25edfdffffff54022b1b4d3b45e7fcac468de2d6df890a9f41050c05d80e68d4b083f728e76a01000000171600146dfe07e12af3db7c715bf1c455f8517e19c361e7fdffffff54022b1b4d3b45e7fcac468de2d6df890a9f41050c05d80e68d4b083f728e76a020000006a47304402200b1fb89e9a772a8519294acd61a53a29473ce76077165447f49a686f1718db5902207466e2e8290f84114dc9d6c56419cb79a138f03d7af8756de02c810f19e4e03301210222bfebe09c2638cfa5aa8223fb422fe636ba9675c5e2f53c27a5d10514f49051fdffffff54022b1b4d3b45e7fcac468de2d6df890a9f41050c05d80e68d4b083f728e76a0300000000fdffffff018793140d000000001600144b3e27ddf4fc5f367421ee193da5332ef351b700000247304402207ba52959938a3853bcfd942d8a7e6a181349069cde3ea73dbde43fa9669b8d5302207a686b92073863203305cb5d5550d88bdab0d21b9e9761ba4a106ea3970e08d901210265c1e014112ed19c9f754143fb6a2ff89f8630d62b33eb5ae708c9ea576e61b50002473044022029e868a905aa3ecae6eafcbd5959aefff0e5f39c1fc7a131a174828806e74e5202202f0aaa7c3cb3d9a9d526e5428ce37c0f0af0d774aa30b09ded8bc2230e7ffaf2012102fe0104455dc52b1689bba130664e452642180eb865217acfc6997260b7d946ae22c71200",
        "336eee749da7d1c537fd5679157fae63005bfd4bb8cf47ae73600999cbc9beaa": "0100000000010232201ff125888a326635a2fc6e971cd774c4d0c1a757d742d0f6b5b020f7203a020000006a4730440220198c0ba2b2aefa78d8cca01401d408ecdebea5ac05affce36f079f6e5c8405ca02200eabb1b9a01ff62180cf061dfacedba6b2e07355841b9308de2d37d83489c7b80121031c663e5534fe2a6de816aded6bb9afca09b9e540695c23301f772acb29c64a05fdfffffffb28ff16811d3027a2405be68154be8fdaff77284dbce7a2314c4107c2c941600000000000fdffffff015e104f01000000001976a9146dfd56a0b5d0c9450d590ad21598ecfeaa438bd788ac000247304402207d6dc521e3a4577685535f098e5bac4601aa03658b924f30bf7afef1850e437e022045b76771d8b6ca1939352d6b759fca31029e5b2edffa44dc747fe49770e746cd012102c7f36d4ceed353b90594ebaf3907972b6d73289bdf4707e120de31ec4e1eb11679f31200",
        "3a6ed17d34c49dfdf413398e113cf5f71710d59e9f4050bbc601d513a77eb308": "010000000168091e76227e99b098ef8d6d5f7c1bb2a154dd49103b93d7b8d7408d49f07be0000000008a47304402202f683a63af571f405825066bd971945a35e7142a75c9a5255d364b25b7115d5602206c59a7214ae729a519757e45fdc87061d357813217848cf94df74125221267ac014104aecb9d427e10f0c370c32210fe75b6e72ccc4f415076cf1a6318fbed5537388862c914b29269751ab3a04962df06d96f5f4f54e393a0afcbfa44b590385ae61afdffffff0240420f00000000001976a9145f917fd451ca6448978ebb2734d2798274daf00b88aca8063d00000000001976a914e1232622a96a04f5e5a24ca0792bb9c28b089d6e88ace9ca1200",
        "475c149be20c8a73596fad6cb8861a5af46d4fcf8e26a9dbf6cedff7ff80b70d": "01000000013a7e6f19a963adc7437d2f3eb0936f1fc9ef4ba7e083e19802eb1111525a59c2000000008b483045022100958d3931051306489d48fe69b32561e0a16e82a2447c07be9d1069317084b5e502202f70c2d9be8248276d334d07f08f934ffeea83977ad241f9c2de954a2d577f94014104d950039cec15ad10ad4fb658873bc746148bc861323959e0c84bf10f8633104aa90b64ce9f80916ab0a4238e025dcddf885b9a2dd6e901fe043a433731db8ab4fdffffff02a086010000000000160014bbfab2cc3267cea2df1b68c392cb3f0294978ca922940d00000000001976a914760f657c67273a06cad5b1d757a95f4ed79f5a4b88ac4c8d1300",
        "56a65810186f82132cea35357819499468e4e376fca685c023700c75dc3bd216": "01000000000101614b142aeeb827d35d2b77a5b11f16655b6776110ddd9f34424ff49d85706cf90200000000fdffffff02784a4c00000000001600148464f47f35cbcda2e4e5968c5a3a862c43df65a1404b4c00000000001976a914c9efecf0ecba8b42dce0ae2b28e3ea0573d351c988ac0247304402207d8e559ed1f56cb2d02c4cb6c95b95c470f4b3cb3ce97696c3a58e39e55cd9b2022005c9c6f66a7154032a0bb2edc1af1f6c8f488bec52b6581a3a780312fb55681b0121024f83b87ac3440e9b30cec707b7e1461ecc411c2f45520b45a644655528b0a68ae9ca1200",
        "6ae728f783b0d4680ed8050c05419f0a89dfd6e28d46acfce7453b4d1b2b0254": "0100000000010496941b9f18710b39bacde890e39a7fa401e6bf49985857cb7adfb8a45147ef1e000000001716001441aec99157d762708339d7faf7a63a8c479ed84cfdffffff96941b9f18710b39bacde890e39a7fa401e6bf49985857cb7adfb8a45147ef1e0100000000fdffffff1a5d1e4ca513983635b0df49fd4f515c66dd26d7bff045cfbd4773aa5d93197f000000006a4730440220652145460092ef42452437b942cb3f563bf15ad90d572d0b31d9f28449b7a8dd022052aae24f58b8f76bd2c9cf165cc98623f22870ccdbef1661b6dbe01c0ef9010f01210375b63dd8e93634bbf162d88b25d6110b5f5a9638f6fe080c85f8b21c2199a1fdfdffffff1a5d1e4ca513983635b0df49fd4f515c66dd26d7bff045cfbd4773aa5d93197f010000008a47304402207517c52b241e6638a84b05385e0b3df806478c2e444f671ca34921f6232ee2e70220624af63d357b83e3abe7cdf03d680705df0049ec02f02918ee371170e3b4a73d014104de408e142c00615294813233cdfe9e7774615ae25d18ba4a1e3b70420bb6666d711464518457f8b947034076038c6f0cfc8940d85d3de0386e0ad88614885c7cfdffffff0480969800000000001976a9149cd3dfb0d87a861770ae4e268e74b45335cf00ab88ac809698000000000017a914f2a76207d7b54bd34282281205923841341d9e1f87002d3101000000001976a914b8d4651937cd7db5bcf5fc98e6d2d8cfa131e85088ac743db20a00000000160014c7d0df09e03173170aed0247243874c6872748ed02483045022100b932cda0aeb029922e126568a48c05d79317747dcd77e61dce44e190e140822002202d13f84338bb272c531c4086277ac11e166c59612f4aefa6e20f78455bdc09970121028e6808a8ac1e9ede621aaabfcad6f86662dbe0ace0236f078eb23c24bc88bd5e02483045022100d74a253262e3898626c12361ba9bb5866f9303b42eec0a55ced0578829e2e61e022059c08e61d90cd63c84de61c796c9d1bc1e2f8217892a7c07b383af357ddd7a730121028641e89822127336fc12ff99b1089eb1a124847639a0e98d17ff03a135ad578b000020c71200",
        "72419d187c61cfc67a011095566b374dc2c01f5397e36eafe68e40fc44474112": "0100000002677b2113f26697718c8991823ec0e637f08cb61426da8da508b97449c872490f000000008b4830450221009c50c0f56f34781dfa7b3d540ac724436c67ffdc2e5b2d5a395c9ebf72116ef802205a94a490ea14e4824f36f1658a384aeaecadd54839600141eb20375a49d476d1014104c291245c2ee3babb2a35c39389df56540867f93794215f743b9aa97f5ba114c4cdee8d49d877966728b76bc649bb349efd73adef1d77452a9aac26f8c51ae1ddfdffffff677b2113f26697718c8991823ec0e637f08cb61426da8da508b97449c872490f010000008b483045022100ae0b286493491732e7d3f91ab4ac4cebf8fe8a3397e979cb689e62d350fdcf2802206cf7adf8b29159dd797905351da23a5f6dab9b9dbf5028611e86ccef9ff9012e014104c62c4c4201d5c6597e5999f297427139003fdb82e97c2112e84452d1cfdef31f92dd95e00e4d31a6f5f9af0dadede7f6f4284b84144e912ff15531f36358bda7fdffffff019f7093030000000022002027ce908c4ee5f5b76b4722775f23e20c5474f459619b94040258290395b88afb6ec51200",
        "76bcf540b27e75488d95913d0950624511900ae291a37247c22d996bb7cde0b4": "0100000001f4ba9948cdc4face8315c7f0819c76643e813093ffe9fbcf83d798523c7965db000000006a473044022061df431a168483d144d4cffe1c5e860c0a431c19fc56f313a899feb5296a677c02200208474cc1d11ad89b9bebec5ec00b1e0af0adaba0e8b7f28eed4aaf8d409afb0121039742bf6ab70f12f6353e9455da6ed88f028257950450139209b6030e89927997fdffffff01d4f84b00000000001976a9140b93db89b6bf67b5c2db3370b73d806f458b3d0488ac0a171300",
        "7f19935daa7347bdcf45f0bfd726dd665c514ffd49dfb035369813a54c1e5d1a": "01000000000102681b6a8dd3a406ee10e4e4aece3c2e69f6680c02f53157be6374c5c98322823a00000000232200209adfa712053a06cc944237148bcefbc48b16eb1dbdc43d1377809bcef1bea9affdffffff681b6a8dd3a406ee10e4e4aece3c2e69f6680c02f53157be6374c5c98322823a0100000023220020f40ed2e3fbffd150e5b74f162c3ce5dae0dfeba008a7f0f8271cf1cf58bfb442fdffffff02801d2c04000000001976a9140cc01e19090785d629cdcc98316f328df554de4f88ac6d455d05000000001976a914b9e828990a8731af4527bcb6d0cddf8d5ffe90ce88ac040047304402206eb65bd302eefae24eea05781e8317503e68584067d35af028a377f0751bb55b0220226453d00db341a4373f1bcac2391f886d3a6e4c30dd15133d1438018d2aad24014730440220343e578591fab0236d28fb361582002180d82cb1ba79eec9139a7a9519fca4260220723784bd708b4a8ed17bb4b83a5fd2e667895078e80eec55119015beb3592fd2016952210222eca5665ed166d090a5241d9a1eb27a92f85f125aaf8df510b2b5f701f3f534210227bca514c22353a7ae15c61506522872afecf10df75e599aabe4d562d0834fce2103601d7d49bada5a57a4832eafe4d1f1096d7b0b051de4a29cd5fc8ad62865e0a553ae0400483045022100b15ea9daacd809eb4d783a1449b7eb33e2965d4229e1a698db10869299dddc670220128871ffd27037a3e9dac6748ce30c14b145dd7f9d56cc9dcde482461fb6882601483045022100cb659e1de65f8b87f64d1b9e62929a5d565bbd13f73a1e6e9dd5f4efa024b6560220667b13ce2e1a3af2afdcedbe83e2120a6e8341198a79efb855b8bc5f93b4729f0169522102d038600af253cf5019f9d5637ca86763eca6827ed7b2b7f8cc6326dffab5eb68210315cdb32b7267e9b366fb93efe29d29705da3db966e8c8feae0c8eb51a7cf48e82103f0335f730b9414acddad5b3ee405da53961796efd8c003e76e5cd306fcc8600c53ae1fc71200",
        "9de08bcafc602a3d2270c46cbad1be0ef2e96930bec3944739089f960652e7cb": "010000000001013409c10fd732d9e4b3a9a1c4beb511fa5eb32bc51fd169102a21aa8519618f800000000000fdffffff0640420f00000000001976a9149cd3dfb0d87a861770ae4e268e74b45335cf00ab88ac40420f00000000001976a9149cd3dfb0d87a861770ae4e268e74b45335cf00ab88ac40420f00000000001976a9149cd3dfb0d87a861770ae4e268e74b45335cf00ab88ac80841e00000000001976a9149cd3dfb0d87a861770ae4e268e74b45335cf00ab88ac64064a000000000016001469825d422ca80f2a5438add92d741c7df45211f280969800000000001976a9149cd3dfb0d87a861770ae4e268e74b45335cf00ab88ac02483045022100b4369b18bccb74d72b6a38bd6db59122a9e8af3356890a5ecd84bdb8c7ffe317022076a5aa2b817be7b3637d179106fccebb91acbc34011343c8e8177acc2da4882e0121033c8112bbf60855f4c3ae489954500c4b8f3408665d8e1f63cf3216a76125c69865281300",
        "a29d131e766950cae2e97dd4527b7c050293c2f5630470bdd7d00b7fe6db1b9d": "010000000400899af3606e93106a5d0f470e4e2e480dfc2fd56a7257a1f0f4d16fd5961a0f000000006a47304402205b32a834956da303f6d124e1626c7c48a30b8624e33f87a2ae04503c87946691022068aa7f936591fb4b3272046634cf526e4f8a018771c38aff2432a021eea243b70121034bb61618c932b948b9593d1b506092286d9eb70ea7814becef06c3dfcc277d67fdffffff4bc2dcc375abfc7f97d8e8c482f4c7b8bc275384f5271678a32c35d955170753000000006b483045022100de775a580c6cb47061d5a00c6739033f468420c5719f9851f32c6992610abd3902204e6b296e812bb84a60c18c966f6166718922780e6344f243917d7840398eb3db0121025d7317c6910ad2ad3d29a748c7796ddf01e4a8bc5e3bf2a98032f0a20223e4aafdffffff4bc2dcc375abfc7f97d8e8c482f4c7b8bc275384f5271678a32c35d955170753010000006a4730440220615a26f38bf6eb7043794c08fb81f273896b25783346332bec4de8dfaf7ed4d202201c2bc4515fc9b07ded5479d5be452c61ce785099f5e33715e9abd4dbec410e11012103caa46fcb1a6f2505bf66c17901320cc2378057c99e35f0630c41693e97ebb7cffdffffff4bc2dcc375abfc7f97d8e8c482f4c7b8bc275384f5271678a32c35d955170753030000006b483045022100c8fba762dc50041ee3d5c7259c01763ed913063019eefec66678fb8603624faa02200727783ccbdbda8537a6201c63e30c0b2eb9afd0e26cb568d885e6151ef2a8540121027254a862a288cfd98853161f575c49ec0b38f79c3ef0bf1fb89986a3c36a8906fdffffff0240787d01000000001976a9149cd3dfb0d87a861770ae4e268e74b45335cf00ab88ac3bfc1502000000001976a914c30f2af6a79296b6531bf34dba14c8419be8fb7d88ac52c51200",
        "c1433779c5faec5df5e7bdc51214a95f15deeab842c23efbdde3acf82c165462": "0100000003aabec9cb99096073ae47cfb84bfd5b0063ae7f157956fd37c5d1a79d74ee6e33000000008b4830450221008136fc880d5e24fdd9d2a43f5085f374fef013b814f625d44a8075104981d92a0220744526ec8fc7887c586968f22403f0180d54c9b7ff8db9b553a3c4497982e8250141047b8b4c91c5a93a1f2f171c619ca41770427aa07d6de5130c3ba23204b05510b3bd58b7a1b35b9c4409104cfe05e1677fc8b51c03eac98b206e5d6851b31d2368fdffffff16d23bdc750c7023c085a6fc76e3e468944919783535ea2c13826f181058a656010000008a47304402204148410f2d796b1bb976b83904167d28b65dcd7c21b3876022b4fa70abc86280022039ea474245c3dc8cd7e5a572a155df7a6a54496e50c73d9fed28e76a1cf998c00141044702781daed201e35aa07e74d7bda7069e487757a71e3334dc238144ad78819de4120d262e8488068e16c13eea6092e3ab2f729c13ef9a8c42136d6365820f7dfdffffff68091e76227e99b098ef8d6d5f7c1bb2a154dd49103b93d7b8d7408d49f07be0010000008b4830450221008228af51b61a4ee09f58b4a97f204a639c9c9d9787f79b2fc64ea54402c8547902201ed81fca828391d83df5fbd01a3fa5dd87168c455ed7451ba8ccb5bf06942c3b0141046fcdfab26ac08c827e68328dbbf417bbe7577a2baaa5acc29d3e33b3cc0c6366df34455a9f1754cb0952c48461f71ca296b379a574e33bcdbb5ed26bad31220bfdffffff0210791c00000000001976a914a4b991e7c72996c424fe0215f70be6aa7fcae22c88ac80c3c901000000001976a914b0f6e64ea993466f84050becc101062bb502b4e488ac7af31200",
        "c2595a521111eb0298e183e0a74befc91f6f93b03e2f7d43c7ad63a9196f7e3a": "01000000018557003cb450f53922f63740f0f77db892ef27e15b2614b56309bfcee96a0ad3010000006a473044022041923c905ae4b5ed9a21aa94c60b7dbcb8176d58d1eb1506d9fb1e293b65ce01022015d6e9d2e696925c6ad46ce97cc23dec455defa6309b839abf979effc83b8b160121029332bf6bed07dcca4be8a5a9d60648526e205d60c75a21291bffcdefccafdac3fdffffff01c01c0f00000000001976a914a2185918aa1006f96ed47897b8fb620f28a1b09988ac01171300",
        "e07bf0498d40d7b8d7933b1049dd54a1b21b7c5f6d8def98b0997e22761e0968": "01000000016d445091b7b4fa19cbbee30141071b2202d0c27d195b9d6d2bcc7085c9cd9127010000008b483045022100daf671b52393af79487667eddc92ebcc657e8ae743c387b25d1c1a2e19c7a4e7022015ef2a52ea7e94695de8898821f9da539815775516f18329896e5fc52a3563b30141041704a3daafaace77c8e6e54cf35ed27d0bf9bb8bcd54d1b955735ff63ec54fe82a80862d455c12e739108b345d585014bf6aa0cbd403817c89efa18b3c06d6b5fdffffff02144a4c00000000001976a9148942ac692ace81019176c4fb0ac408b18b49237f88ac404b4c00000000001976a914dd36d773acb68ac1041bc31b8a40ee504b164b2e88ace9ca1200",
        "e453e7346693b507561691b5ea73f8eba60bfc8998056226df55b2fac88ba306": "010000000125af87b0c2ebb9539d644e97e6159ccb8e1aa80fe986d01f60d2f3f37f207ae8010000008b483045022100baed0747099f7b28a5624005d50adf1069120356ac68c471a56c511a5bf6972b022046fbf8ec6950a307c3c18ca32ad2955c559b0d9bbd9ec25b64f4806f78cadf770141041ea9afa5231dc4d65a2667789ebf6806829b6cf88bfe443228f95263730b7b70fb8b00b2b33777e168bcc7ad8e0afa5c7828842794ce3814c901e24193700f6cfdffffff02a0860100000000001976a914ade907333744c953140355ff60d341cedf7609fd88ac68830a00000000001976a9145d48feae4c97677e4ca7dcd73b0d9fd1399c962b88acc9cc1300",
        "e87a207ff3f3d2601fd086e90fa81a8ecb9c15e6974e649d53b9ebc2b087af25": "01000000010db780fff7dfcef6dba9268ecf4f6df45a1a86b86cad6f59738a0ce29b145c47010000008a47304402202887ec6ec200e4e2b4178112633011cbdbc999e66d398b1ff3998e23f7c5541802204964bd07c0f18c48b7b9c00fbe34c7bc035efc479e21a4fa196027743f06095f0141044f1714ed25332bb2f74be169784577d0838aa66f2374f5d8cbbf216063626822d536411d13cbfcef1ff3cc1d58499578bc4a3c4a0be2e5184b2dd7963ef67713fdffffff02a0860100000000001600145bbdf3ba178f517d4812d286a40c436a9088076e6a0b0c00000000001976a9143fc16bef782f6856ff6638b1b99e4d3f863581d388acfbcb1300"
    }
    txid_list = sorted(list(transactions))

    def setUp(self):
        super().setUp()
        self.config = SimpleConfig({'electrum_path': self.electrum_path})

    def create_old_wallet(self):
        ks = keystore.from_old_mpk('e9d4b7866dd1e91c862aebf62a49548c7dbf7bcc6e4b7b8c9da820c7737968df9c09d5a3e271dc814a29981f81b3faaf2737b551ef5dcc6189cf0f8252c442b3')
        # seed words: powerful random nobody notice nothing important anyway look away hidden message over
        w = WalletIntegrityHelper.create_standard_wallet(ks, gap_limit=20, config=self.config)
        # some txns are beyond gap limit:
        w.create_new_address(for_change=True)
        return w

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_restoring_old_wallet_txorder1(self, mock_save_db):
        w = self.create_old_wallet()
        for i in [2, 12, 7, 9, 11, 10, 16, 6, 17, 1, 13, 15, 5, 8, 4, 0, 14, 18, 3]:
            tx = Transaction(self.transactions[self.txid_list[i]])
            w.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual(27633300, sum(w.get_balance()))

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_restoring_old_wallet_txorder2(self, mock_save_db):
        w = self.create_old_wallet()
        for i in [9, 18, 2, 0, 13, 3, 1, 11, 4, 17, 7, 14, 12, 15, 10, 8, 5, 6, 16]:
            tx = Transaction(self.transactions[self.txid_list[i]])
            w.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual(27633300, sum(w.get_balance()))

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_restoring_old_wallet_txorder3(self, mock_save_db):
        w = self.create_old_wallet()
        for i in [5, 8, 17, 0, 9, 10, 12, 3, 15, 18, 2, 11, 14, 7, 16, 1, 4, 6, 13]:
            tx = Transaction(self.transactions[self.txid_list[i]])
            w.receive_tx_callback(tx.txid(), tx, TX_HEIGHT_UNCONFIRMED)
        self.assertEqual(27633300, sum(w.get_balance()))


class TestWalletHistory_EvilGapLimit(TestCaseForTestnet):
    transactions = {
        # txn A:
        "511a35e240f4c8855de4c548dad932d03611a37e94e9203fdb6fc79911fe1dd4": "010000000001018aacc3c8f98964232ebb74e379d8ff4e800991eecfcf64bd1793954f5e50a8790100000000fdffffff0340420f0000000000160014dbf321e905d544b54b86a2f3ed95b0ac66a3ddb0ff0514000000000016001474f1c130d3db22894efb3b7612b2c924628d0d7e80841e000000000016001488492707677190c073b6555fb08d37e91bbb75d802483045022100cf2904e09ea9d2670367eccc184d92fcb8a9b9c79a12e4efe81df161077945db02203530276a3401d944cf7a292e0660f36ee1df4a1c92c131d2c0d31d267d52524901210215f523a412a5262612e1a5ef9842dc864b0d73dc61fb4c6bfd480a867bebb1632e181400",
        # txn B:
        "fde0b68938709c4979827caa576e9455ded148537fdb798fd05680da64dc1b4f": "01000000000101a317998ac6cc717de17213804e1459900fe257b9f4a3b9b9edd29806728277530100000000fdffffff03c0c62d00000000001600149543301687b1ca2c67718d55fbe10413c73ddec200093d00000000001600141bc12094a4475dcfbf24f9920dafddf9104ca95b3e4a4c0000000000160014b226a59f2609aa7da4026fe2c231b5ae7be12ac302483045022100f1082386d2ce81612a3957e2801803938f6c0066d76cfbd853918d4119f396df022077d05a2b482b89707a8a600013cb08448cf211218a462f2a23c2c0d80a8a0ca7012103f4aac7e189de53d95e0cb2e45d3c0b2be18e93420734934c61a6a5ad88dd541033181400",
        # txn C:
        "268fce617aaaa4847835c2212b984d7b7741fdab65de22813288341819bc5656": "010000000001014f1bdc64da8056d08f79db7f5348d1de55946e57aa7c8279499c703889b6e0fd0100000000fdffffff0260e316000000000016001445e9879cf7cd5b4a15df7ddcaf5c6dca0e1508bacc242600000000001600141bc12094a4475dcfbf24f9920dafddf9104ca95b02483045022100ae3618912f341fefee11b67e0047c47c88c4fa031561c3fafe993259dd14d846022056fa0a5b5d8a65942fa68bcc2f848fd71fa455ba42bc2d421b67eb49ba62aa4e01210394d8f4f06c2ea9c569eb050c897737a7315e7f2104d9b536b49968cc89a1f11033181400",
    }

    def setUp(self):
        super().setUp()
        self.config = SimpleConfig({
            'electrum_path': self.electrum_path,
            'skipmerklecheck': True,  # needed for Synchronizer to generate new addresses without SPV
        })

    def create_wallet(self):
        ks = keystore.from_xpub('vpub5Vhmk4dEJKanDTTw6immKXa3thw45u3gbd1rPYjREB6viP13sVTWcH6kvbR2YeLtGjradr6SFLVt9PxWDBSrvw1Dc1nmd3oko3m24CQbfaJ')
        # seed words: nephew work weather maze pyramid employ check permit garment scene kiwi smooth
        w = WalletIntegrityHelper.create_standard_wallet(ks, gap_limit=20, config=self.config)
        return w

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_restoring_wallet_txorder1(self, mock_save_db):
        w = self.create_wallet()
        w.db.put('stored_height', 1316917 + 100)
        for txid in self.transactions:
            tx = Transaction(self.transactions[txid])
            w.add_transaction(tx)
        # txn A is an external incoming txn paying to addr (3) and (15)
        # txn B is an external incoming txn paying to addr (4) and (25)
        # txn C is an internal transfer txn from addr (25) -- to -- (1) and (25)
        w.receive_history_callback('tbc1qgh5c088he4d559wl0hw27hrdeg8p2z96pefn4q',  # HD index 1
                                   [('268fce617aaaa4847835c2212b984d7b7741fdab65de22813288341819bc5656', 1316917)],
                                   {})
        w.synchronize()
        w.receive_history_callback('tbc1qm0ejr6g964zt2jux5te7m9ds43n28hdsdz9ull',  # HD index 3
                                   [('511a35e240f4c8855de4c548dad932d03611a37e94e9203fdb6fc79911fe1dd4', 1316912)],
                                   {})
        w.synchronize()
        w.receive_history_callback('tbc1qj4pnq958k89zcem3342lhcgyz0rnmhkzl6x0cl',  # HD index 4
                                   [('fde0b68938709c4979827caa576e9455ded148537fdb798fd05680da64dc1b4f', 1316917)],
                                   {})
        w.synchronize()
        w.receive_history_callback('tbc1q3pyjwpm8wxgvquak240mprfhaydmkawcsl25je',  # HD index 15
                                   [('511a35e240f4c8855de4c548dad932d03611a37e94e9203fdb6fc79911fe1dd4', 1316912)],
                                   {})
        w.synchronize()
        w.receive_history_callback('tbc1qr0qjp99ygawul0eylxfqmt7alygye22mj33vej',  # HD index 25
                                   [('fde0b68938709c4979827caa576e9455ded148537fdb798fd05680da64dc1b4f', 1316917),
                                    ('268fce617aaaa4847835c2212b984d7b7741fdab65de22813288341819bc5656', 1316917)],
                                   {})
        w.synchronize()
        self.assertEqual(7500000, sum(w.get_balance()))

class TestWalletHistory_DoubleSpend(TestCaseForTestnet):
    transactions = {
        # txn A:
        "a3849040f82705151ba12a4389310b58a17b78025d81116a3338595bdefa1625": "020000000001011b7eb29921187b40209c234344f57a3365669c8883a3d511fbde5155f11f64d10000000000fdffffff024c400f0000000000160014b50d21483fb5e088db90bf766ea79219fb377fef40420f0000000000160014aaf5fc4a6297375c32403a9c2768e7029c8dbd750247304402206efd510954b289829f8f778163b98a2a4039deb93c3b0beb834b00cd0add14fd02201c848315ddc52ced0350a981fe1a7f3cbba145c7a43805db2f126ed549eaa500012103083a50d63264743456a3e812bfc91c11bd2a673ba4628c09f02d78f62157e56d788d1700",
        # txn B:
        "0e2182ead6660790290371516cb0b80afa8baebd30dad42b5e58a24ceea17f1c": "020000000001012516fade5b5938336a11815d02787ba1580b3189432aa11b150527f8409084a30100000000fdffffff02a086010000000000160014cb893c9fbb565363556fb18a3bcdda6f20af0bf8d8ba0d0000000000160014478902f02c2b6cd405bb6bd1f90e9860bec173e20247304402206940671b5bdb230a9721aa57396af73d399fb210d795e7dbb8ec1977e101a5470220625505de035d4006b72bd6dfcf09468d1e8da53071080b37b16b0dbbf776db78012102254b5b20ed21c3bba75ec2a9ff230257d13a2493f6b7da066d8195dcdd484310788d1700",
        # txn C:
        "2c9aa33d9c8ec649f9bfb84af027a5414b760be5231fe9eca4a95b9eb3f8a017": "020000000001012516fade5b5938336a11815d02787ba1580b3189432aa11b150527f8409084a30100000000fdffffff01d2410f00000000001600147880a7c79744b908a5f6d6235f2eb46c174c84f002483045022100974d27c872f09115e57c6acb674cd4da6d0b26656ad967ddb2678ff409714b9502206d91b49cf778ced6ca9e40b4094fb57b86c86fac09ce46ce53aea4afa68ff311012102254b5b20ed21c3bba75ec2a9ff230257d13a2493f6b7da066d8195dcdd484310788d1700",
    }

    def setUp(self):
        super().setUp()
        self.config = SimpleConfig({'electrum_path': self.electrum_path})

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_restoring_wallet_without_manual_delete(self, mock_save_db):
        w = restore_wallet_from_text("small rapid pattern language comic denial donate extend tide fever burden barrel",
                                     path='if_this_exists_mocking_failed_648151893',
                                     gap_limit=5,
                                     config=self.config)['wallet']  # type: Abstract_Wallet
        for txid in self.transactions:
            tx = Transaction(self.transactions[txid])
            w.add_transaction(tx)
        # txn A is an external incoming txn funding the wallet
        # txn B is an outgoing payment to an external address
        # txn C is double-spending txn B, to a wallet address
        self.assertEqual(999890, sum(w.get_balance()))

    @mock.patch.object(wallet.Abstract_Wallet, 'save_db')
    def test_restoring_wallet_with_manual_delete(self, mock_save_db):
        w = restore_wallet_from_text("small rapid pattern language comic denial donate extend tide fever burden barrel",
                                     path='if_this_exists_mocking_failed_648151893',
                                     gap_limit=5,
                                     config=self.config)['wallet']  # type: Abstract_Wallet
        # txn A is an external incoming txn funding the wallet
        txA = Transaction(self.transactions["a3849040f82705151ba12a4389310b58a17b78025d81116a3338595bdefa1625"])
        w.add_transaction(txA)
        # txn B is an outgoing payment to an external address
        txB = Transaction(self.transactions["0e2182ead6660790290371516cb0b80afa8baebd30dad42b5e58a24ceea17f1c"])
        w.add_transaction(txB)
        # now the user manually deletes txn B to attempt the double spend
        # txn C is double-spending txn B, to a wallet address
        # rationale1: user might do this with opt-in RBF transactions
        # rationale2: this might be a local transaction, in which case the GUI even allows it
        w.remove_transaction(txB.txid())
        txC = Transaction(self.transactions["2c9aa33d9c8ec649f9bfb84af027a5414b760be5231fe9eca4a95b9eb3f8a017"])
        w.add_transaction(txC)
        self.assertEqual(999890, sum(w.get_balance()))

