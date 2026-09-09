# this should run with python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(1, str((ROOT / "../../f469-disco/libs/common/embit/src").resolve()))

if sys.implementation.name == 'micropython':
    print("This file should run with python3, not micropython!")
    sys.exit(1)
from util.controller import sim, core
import unittest

def main():
    # core.start() # start Bitcoin Core on regtest
    sim.start() # start simulator
    try:
        sim.load() # unlock, load mnemonic etc
        unittest.main('tests')
    finally:
        # core.shutdown()
        sim.shutdown()

if __name__ == '__main__':
    main()
