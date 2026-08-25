"""Leitura de QR pela camera, na placa.

    ports/esp32p4/tools/push.py ports/esp32p4/test_qr.py:/test_qr.py \\
        "exec(open('/test_qr.py').read())"

Aponte a camera para um QR code durante a janela de leitura.
"""

import time

import camera
import p4board


def run(seconds=25):
    p4board.init()
    print("sensor   :", camera.init())
    print("quadro   : %dx%d" % camera.size())

    start = time.ticks_ms()
    scans = 0
    payload = None
    while time.ticks_diff(time.ticks_ms(), start) < seconds * 1000:
        payload = camera.scan()
        scans += 1
        if payload:
            break
    elapsed = time.ticks_diff(time.ticks_ms(), start)

    # gray_size() so tem valor depois do primeiro scan: o buffer e alocado
    # sob demanda, quando a resolucao do sensor ja e conhecida.
    print("cinza    : %dx%d" % camera.gray_size())
    print("taxa     : %.1f leituras/s" % (scans * 1000 / elapsed))
    if payload:
        print("QR lido  :", payload)
        print("bytes    :", len(payload))
    else:
        print("nenhum QR no campo de visao em %d s" % seconds)
    camera.deinit()


run()
