"""Wrapper do modulo `udisplay` para a Waveshare ESP32-P4 4.3-C.

Espelha f469-disco/usermods/udisplay_f469/display_f469/display.py, que faz o
mesmo para a Discovery. O app importa `display`, nao `udisplay`, e conta com o
init opcionalmente ligar a atualizacao periodica do LVGL.

Diferenca: la o timer e `pyb.Timer(4)`; aqui e `machine.Timer`. O padrao de
usar micropython.schedule() para tirar o trabalho de dentro da interrupcao e
mantido -- lv_task_handler() aloca memoria e nao pode rodar num contexto de IRQ.
"""

from udisplay import backlight, off, on, set_rotation, update

_timer = None

UPDATE_HZ = 30
UPDATE_MS = 1000 // UPDATE_HZ


def init(autoupdate=True):
    import udisplay

    udisplay.init()

    if autoupdate:
        global _timer
        import machine
        import micropython

        def _schedule(timer):
            try:
                micropython.schedule(udisplay.update, UPDATE_MS)
            except RuntimeError:
                # Fila de schedule cheia: o proximo tick cobre. Perder um
                # quadro e melhor que estourar numa interrupcao.
                pass

        _timer = machine.Timer(0)
        _timer.init(freq=UPDATE_HZ, mode=machine.Timer.PERIODIC, callback=_schedule)


def deinit():
    global _timer
    if _timer is not None:
        _timer.deinit()
        _timer = None
