# this should run with python3
import sys
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
