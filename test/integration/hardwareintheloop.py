#!/usr/bin/env python3
"""
Hardware-in-the-Loop test runner for Specter-DIY.

Mirrors run_tests.py but targets real STM32F469 hardware via serial UART.
Loads the same test files from tests/ — no test code changes needed.

Prerequisites:
  - Device flashed with HIL firmware: make hardwareintheloop
  - ST-Link connected (debug UART on /dev/ttyACM0)
  - For RPC tests: bitcoind running in regtest mode

Environment variables for RPC tests:
  BTC_RPC_USER     (default: specter)
  BTC_RPC_PASSWORD (default: specter)
  BTC_RPC_HOST     (default: 127.0.0.1)
  BTC_RPC_PORT     (default: 18443)
"""
import sys
import os
import importlib.util
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'hil'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from controller import sim as hw_sim

import util.controller
util.controller.sim = hw_sim

TEST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests')


def load_test_module(name, filename):
    path = os.path.join(TEST_DIR, filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load module from %s" % path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def rpc_available():
    """Check if Bitcoin Core RPC is accessible via env vars."""
    try:
        import requests
        url = "http://%s:%s" % (
            os.environ.get("BTC_RPC_HOST", "127.0.0.1"),
            os.environ.get("BTC_RPC_PORT", "18443"),
        )
        r = requests.get(url, auth=(
            os.environ.get("BTC_RPC_USER", "specter"),
            os.environ.get("BTC_RPC_PASSWORD", "specter"),
        ), timeout=2)
        return True
    except Exception:
        return False


def main():
    hw_sim.start()
    try:
        hw_sim.load()

        loader = unittest.TestLoader()
        suite = unittest.TestSuite()

        test_files = [
            ("test_basic", "test_basic.py"),
        ]

        if rpc_available():
            print("Bitcoin Core RPC available - including RPC tests")
            test_files.append(("test_with_rpc", "test_with_rpc.py"))
        else:
            print("Bitcoin Core RPC not available - skipping RPC tests")
            print("Set BTC_RPC_USER, BTC_RPC_PASSWORD, BTC_RPC_PORT to enable")

        for name, filename in test_files:
            try:
                mod = load_test_module(name, filename)
                suite.addTests(loader.loadTestsFromModule(mod))
            except Exception as e:
                print("Failed to load %s: %s" % (filename, e))

        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        hw_sim.shutdown()


if __name__ == '__main__':
    main()
