"""Shared fixtures for disco_lib tests."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_glob():
    """Mock glob.glob for device listing tests."""
    with patch("disco_lib.serial.glob.glob") as mock:
        yield mock


@pytest.fixture
def mock_socket():
    """Mock socket for OpenOCD tests."""
    with patch("disco_lib.openocd.socket.create_connection") as mock:
        yield mock


@pytest.fixture
def mock_serial():
    """Mock pyserial for serial tests."""
    with patch("disco_lib.serial.serial.Serial") as mock:
        yield mock


@pytest.fixture
def mock_subprocess():
    """Mock subprocess for OpenOCD start/stop."""
    with patch("disco_lib.openocd.subprocess.Popen") as mock:
        yield mock
