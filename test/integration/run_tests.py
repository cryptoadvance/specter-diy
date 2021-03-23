# this should run with python3
import sys
if sys.implementation.name == 'micropython':
    print("This file should run with python3, not micropython!")
    sys.exit(1)
import unittest
from tests.controller import sim

def main():
    sim.start() # start simulator
    try:
        sim.load() # unlock, load mnemonic etc
        unittest.main('tests')
    finally:
        sim.shutdown()

if __name__ == '__main__':
    main()
