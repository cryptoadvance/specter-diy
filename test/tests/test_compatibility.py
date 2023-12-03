from unittest import TestCase
from apps.compatibility import parse_software_wallet_json, parse_cc_wallet_txt
import json
from io import BytesIO

WALLET_SOFTWARE = b'{"label": "blah", "blockheight": 0, "descriptor": "wsh(sortedmulti(1,[fb7c1f11/48h/1h/0h/2h]tpubDExnGppazLhZPNadP8Q5Vgee2QcvbyAf9GvGaEY7ALVJREaG2vdTqv1MHRoDtPaYP3y1DGVx7wrKKhsLhs26GY263uE6Wi3qNbi71AHZ6p7/0/*,[33a2bf0c/48h/1h/0h/2h]tpubDF4cAhFDn6XSPhQtFECSkQm35oEzVyHHAiPa4Qy83fBtPw9nFJAodN6xF6nY7y2xKMGc5nbDFZfAac88oaurVzrCUxyhmc9J8W5tg3N5NkS/0/*))#vk844svv", "devices": [{"type": "specter", "label": "ability"}, {"type": "coldcard", "label": "hox"}]}'

COLDCARD_FILE = """
# Coldcard Multisig setup file (created on Specter Desktop)
#
Name: blah
Policy: 1 of 2
Derivation: m/48'/1'/0'/2'
Format: P2WSH
FB7C1F11: tpubDExnGppazLhZPNadP8Q5Vgee2QcvbyAf9GvGaEY7ALVJREaG2vdTqv1MHRoDtPaYP3y1DGVx7wrKKhsLhs26GY263uE6Wi3qNbi71AHZ6p7
33A2BF0C: tpubDF4cAhFDn6XSPhQtFECSkQm35oEzVyHHAiPa4Qy83fBtPw9nFJAodN6xF6nY7y2xKMGc5nbDFZfAac88oaurVzrCUxyhmc9J8W5tg3N5NkS
"""

EXPECTED = ('blah', 'wsh(sortedmulti(1,[fb7c1f11/48h/1h/0h/2h]tpubDExnGppazLhZPNadP8Q5Vgee2QcvbyAf9GvGaEY7ALVJREaG2vdTqv1MHRoDtPaYP3y1DGVx7wrKKhsLhs26GY263uE6Wi3qNbi71AHZ6p7/{0,1}/*,[33a2bf0c/48h/1h/0h/2h]tpubDF4cAhFDn6XSPhQtFECSkQm35oEzVyHHAiPa4Qy83fBtPw9nFJAodN6xF6nY7y2xKMGc5nbDFZfAac88oaurVzrCUxyhmc9J8W5tg3N5NkS/{0,1}/*))')

class CompatibilityTest(TestCase):

    def test_import(self):
        self.assertEqual(EXPECTED, parse_software_wallet_json(json.load(BytesIO(WALLET_SOFTWARE))))
        self.assertEqual(EXPECTED, parse_cc_wallet_txt(BytesIO(COLDCARD_FILE.encode())))
