# Modulos congelados no firmware da Waveshare 4.3-C.
#
# Congelar em vez de copiar para o sistema de arquivos: o bytecode fica em
# flash e executa direto de la, sem gastar RAM com o codigo, e nao ha como o
# usuario apagar por acidente.

# Modulos padrao da porta esp32 (bootloader do sistema de arquivos, etc).
include("$(PORT_DIR)/boards/manifest.py")

_ROOT = "/home/sm/specter-diy"

# Shims da plataforma: pyb e sdram.
freeze(_ROOT + "/ports/esp32p4/lib")

# Bibliotecas do bundle, item a item.
#
# NAO congelamos f469-disco/libs/common inteiro: ele vendoriza uma copia de
# asyncio da epoca do MicroPython v1.10, que colide com a asyncio moderna vinda
# de $(PORT_DIR)/boards/manifest.py:
#
#   error: redefinition of 'const_qstr_table_data_asyncio___init__'
#
# A do MicroPython e mais nova e mantida; usamos ela.
#
# lvqr depende de lvgl e so importa quando o binding existir -- congelar o
# bytecode e inofensivo ate la.
_COMMON = _ROOT + "/f469-disco/libs/common"
freeze(_COMMON, "embit")
freeze(_COMMON, "microur")
freeze(_COMMON, "bcur.py")
freeze(_COMMON, "lvqr.py")

# O aplicativo Specter.
freeze(_ROOT + "/src")
