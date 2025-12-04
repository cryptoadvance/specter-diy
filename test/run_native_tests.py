import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Insert src directly after the local dir (highest prio)
sys.path.insert(1, str((ROOT / "../src").resolve()))

# make the other stuff available with lowest prio
sys.path.append(str((ROOT / "../f469-disco/libs/common").resolve()))
sys.path.append(str((ROOT / "../f469-disco/libs/unix").resolve()))
sys.path.append(str((ROOT / "../f469-disco/usermods/udisplay_f469/display_unixport").resolve()))
sys.path.append(str((ROOT / "../f469-disco/tests").resolve()))

# uncomment if import issues
#print("Import priotisation:")
#print('\n'.join(f'{i}: {p}' for i, p in enumerate(sys.path[:10])))

from native_support import setup_native_stubs

setup_native_stubs()

import unittest
from tests import util

util.clear_testdir()
unittest.main('tests_native', verbosity=2)
