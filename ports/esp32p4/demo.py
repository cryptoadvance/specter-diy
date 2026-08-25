"""Demonstracao do modulo p4board na Waveshare ESP32-P4 4.3-C.

Copie para a placa e rode:

    mpremote cp ports/esp32p4/demo.py :demo.py
    mpremote exec "import demo; demo.main()"

Ou cole no REPL em paste mode (ctrl-E, cola, ctrl-D). Colar bloco multilinha
sem paste mode nao funciona: o REPL trata a indentacao como continuacao e
embaralha o codigo.
"""

import time

import framebuf

import p4board

BLACK = 0x0000
WHITE = 0xFFFF
RED = 0xF800
GREEN = 0x07E0
BLUE = 0x001F
YELLOW = 0xFFE0
CYAN = 0x07FF
PALETTE = (RED, GREEN, BLUE, YELLOW, 0xF81F)


def screen():
    """Envolve o framebuffer do painel num FrameBuffer, sem copia.

    p4board.framebuffer() devolve um memoryview gravavel apontando direto para
    a memoria que o controlador DPI varre. Escrever nele e desenhar; nada e
    enviado ao painel ate p4board.flush().
    """
    return framebuf.FrameBuffer(
        p4board.framebuffer(), p4board.WIDTH, p4board.HEIGHT, framebuf.RGB565
    )


def test_pattern():
    """Barras coloridas, moldura e texto -- confere painel, cor e geometria."""
    touch_ok = p4board.init()
    g = screen()
    g.fill(BLACK)
    for index, (color, name) in enumerate(
        ((RED, "VERMELHO"), (GREEN, "VERDE"), (BLUE, "AZUL"), (YELLOW, "AMARELO"))
    ):
        g.fill_rect(40, 60 + index * 110, 400, 90, color)
        g.text(name, 60, 95 + index * 110, BLACK)
    g.rect(20, 20, 440, 760, WHITE)
    g.text("SPECTER DIY - ESP32-P4", 110, 560, WHITE)
    g.text("Waveshare 4.3-C  480x800", 100, 590, WHITE)
    g.text("touch 0x%02x" % p4board.touch_address(), 170, 620, CYAN if touch_ok else RED)
    p4board.flush()
    p4board.backlight(100)
    return touch_ok


def draw(seconds=20):
    """Desenha sob o dedo. Cor por id do ponto, entao multitouch aparece."""
    p4board.init()
    g = screen()
    g.fill(BLACK)
    g.text("TOQUE PARA DESENHAR", 90, 30, WHITE)
    p4board.flush()
    p4board.backlight(100)

    total = 0
    deadline = time.ticks_add(time.ticks_ms(), seconds * 1000)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        for point_id, x, y, _size in p4board.touch():
            total += 1
            g.fill_rect(max(0, x - 6), max(0, y - 6), 12, 12,
                        PALETTE[point_id % len(PALETTE)])
            # Faixa estreita em vez da tela inteira: o flush custa proporcional
            # a area, e a 50 Hz isso importa.
            top = max(0, y - 8)
            p4board.flush(top, min(20, p4board.HEIGHT - top))
        time.sleep_ms(20)
    return total


def main():
    print("touch:", "ok" if test_pattern() else "FALHOU")
    time.sleep(3)
    print("pontos lidos:", draw())
