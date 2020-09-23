# write here some bootstrap code for your debugging

from keystore.javacard.util import get_connection
from keystore.javacard.applets.memorycard import MemoryCardApplet

conn = get_connection()
app = MemoryCardApplet(conn)