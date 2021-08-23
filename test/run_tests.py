import sys
sys.path.append('../src')
sys.path.append('../f469-disco/libs/common')
sys.path.append('../f469-disco/libs/unix')
sys.path.append('../f469-disco/usermods/udisplay_f469/display_unixport')
sys.path.append('../f469-disco/tests')

import unittest
from tests import util

util.clear_testdir()
unittest.main('tests')
