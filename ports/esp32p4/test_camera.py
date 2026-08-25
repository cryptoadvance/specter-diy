"""Teste da camera MIPI-CSI na placa.

    ports/esp32p4/tools/push.py ports/esp32p4/test_camera.py:/test_camera.py \\
        "exec(open('/test_camera.py').read())"

Usar exec com caminho absoluto, e nao import: o app do Specter troca o
diretorio de trabalho para o ramdisk, entao a raiz nao esta no sys.path.
"""

import time

import camera
import p4board


def run(frames=10):
    # A camera reusa o barramento I2C que o touch cria; sem isto o SCCB nao
    # tem por onde falar com o sensor.
    p4board.init()

    print("sensor    :", camera.init())
    print("etapa     :", camera.stage())
    print("formato   :", camera.format())
    width, height = camera.size()
    print("resolucao : %dx%d" % (width, height))

    start = time.ticks_ms()
    stats = None
    for _ in range(frames):
        frame = camera.capture()
        if stats is None:
            # Amostragem esparsa: percorrer 2,4 MB byte a byte em Python leva
            # mais tempo que capturar o quadro.
            step = max(1, len(frame) // 2000)
            sample = [frame[i] for i in range(0, len(frame), step)]
            stats = (len(frame), min(sample), max(sample),
                     sum(sample) // len(sample))
        camera.release()
    elapsed = time.ticks_diff(time.ticks_ms(), start)

    print("taxa      : %.1f fps" % (frames * 1000 / elapsed))
    print("bytes     : %d por quadro" % stats[0])
    print("luminancia: min=%d max=%d media=%d" % (stats[1], stats[2], stats[3]))
    # Um sensor morto ou com a tampa fechada entrega um quadro uniforme; a
    # variacao e o que distingue imagem real de buffer parado.
    print("imagem    :", "viva" if stats[2] > stats[1] + 10 else "SUSPEITA")
    camera.deinit()


run()
