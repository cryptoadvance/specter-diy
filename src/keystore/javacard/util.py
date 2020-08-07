"""
Simple helper functions to get reader and connection
"""
import uscard as sc
from pyb import Pin

reader = None
conn = None

def get_reader():
	global reader
	if reader is not None:
		return reader
	reader = sc.Reader(name="Specter card reader", ifaceId=2, ioPin=Pin.cpu.A2, clkPin=Pin.cpu.A4, rstPin=Pin.cpu.G10, presPin=Pin.cpu.C2, pwrPin=Pin.cpu.C5)
	return reader

def get_connection():
	global conn
	if conn is not None:
		return conn
	reader = get_reader()
	conn = reader.createConnection()
	return conn

def encode(data):
	return bytes([len(data)])+data
