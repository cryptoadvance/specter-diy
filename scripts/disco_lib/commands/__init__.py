"""CLI command groups for disco."""

from .ocd import ocd
from .cpu import cpu
from .mem import mem
from .flash import flash
from .serial import serial
from .repl import repl
from .doctor import doctor

__all__ = ["ocd", "cpu", "mem", "flash", "serial", "repl", "doctor"]
