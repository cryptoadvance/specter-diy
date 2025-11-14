import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str((ROOT / "../src").resolve()))
sys.path.insert(0, str((ROOT / "../f469-disco/libs/common").resolve()))
sys.path.insert(0, str((ROOT / "../f469-disco/libs/unix").resolve()))
sys.path.insert(0, str((ROOT / "../f469-disco/usermods/udisplay_f469/display_unixport").resolve()))
sys.path.insert(0, str((ROOT / "../f469-disco/tests").resolve()))

from native_support import setup_native_stubs

setup_native_stubs()

import unittest
from tests import util

util.clear_testdir()
unittest.main('tests_native', verbosity=2)
