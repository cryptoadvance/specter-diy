"""Camada de compatibilidade `sdram` para o ESP32-P4.

Na Discovery F469 o Specter usa um chip de SDRAM externo, inicializado a mao e
exposto como disco em RAM mais um bloco pre-alocado para o trabalho com PSBT.

Aqui a PSRAM de 32 MB ja e inicializada pelo ESP-IDF no boot e entra no heap do
MicroPython -- `gc.mem_free()` reporta cerca de 31,6 MB. Entao `init()` nao tem
o que fazer, e as alocacoes abaixo saem naturalmente na PSRAM por serem grandes
demais para a RAM interna.
"""

import uctypes

# Espelha o simulador, que usa bytes(0x100000).
PREALLOCATED_SIZE = 0x100000

_preallocated = None


def init():
    """A PSRAM sobe com o ESP-IDF; nada a fazer."""
    return True


def _pool():
    global _preallocated
    if _preallocated is None:
        _preallocated = bytearray(PREALLOCATED_SIZE)
    return _preallocated


def preallocated_ptr():
    return uctypes.addressof(_pool())


def preallocated_size():
    return len(_pool())


class RAMDevice:
    """Block device em RAM, para o disco temporario montado em /ramdisk.

    O Specter cria isto, formata com FAT e monta, para ter area de rascunho que
    nunca toca a flash. Manter isso em RAM importa: e onde dados sensiveis
    transitam, e RAM nao sobrevive a um corte de energia.
    """

    def __init__(self, block_size=512, blocks=512):
        self.block_size = block_size
        self.blocks = blocks
        self.data = bytearray(block_size * blocks)

    def readblocks(self, block_num, buf, offset=0):
        start = block_num * self.block_size + offset
        buf[:] = self.data[start:start + len(buf)]
        return 0

    def writeblocks(self, block_num, buf, offset=0):
        start = block_num * self.block_size + offset
        self.data[start:start + len(buf)] = buf
        return 0

    def ioctl(self, op, arg):
        if op == 3:      # sincronizar: RAM nao precisa
            return 0
        if op == 4:      # numero de blocos
            return self.blocks
        if op == 5:      # tamanho do bloco
            return self.block_size
        if op == 6:      # apagar bloco: no-op em RAM
            return 0
        return None

    def wipe(self):
        """Zera o conteudo. Chame antes de soltar a referencia."""
        for index in range(len(self.data)):
            self.data[index] = 0
