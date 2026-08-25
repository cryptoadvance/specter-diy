"""Stub do modulo `uscard` para a Waveshare ESP32-P4 4.3-C.

Esta placa nao tem leitor de smartcard. O Specter usa `uscard` para o keystore
Specter-Javacard; sem hardware, esse keystore precisa reportar "sem cartao" de
forma limpa para o app cair nos outros (SD card e flash interna).

Espelha a API de f469-disco/libs/unix/uscard.py, que faz o equivalente para o
simulador conectando a um javacard simulado por TCP. Aqui nao ha nem hardware
nem simulador, entao isCardInserted() e sempre False e qualquer operacao que
exija cartao levanta NoCardException.

NAO e um leitor funcional. Se um leitor for ligado a esta placa no futuro, o
caminho e portar o usermod `scard` do bundle (2510 linhas de C), nao estender
este arquivo.
"""


class SmartcardException(Exception):
    pass


class CardConnectionException(SmartcardException):
    pass


class NoCardException(SmartcardException):
    pass


def enableDebug(*args, **kwargs):
    pass


def disableDebug(*args, **kwargs):
    pass


class CardConnection:
    T0_protocol = 2
    T1_protocol = 1

    def isCardInserted(self):
        return False

    def connect(self, protocol=None):
        raise NoCardException("no smartcard reader on this board")

    def disconnect(self):
        pass

    def getATR(self):
        raise NoCardException("no smartcard reader on this board")

    def transmit(self, data):
        raise NoCardException("no smartcard reader on this board")


class Reader:
    def __init__(self, *args, **kwargs):
        self.name = kwargs.get("name", "absent card reader")

    def createConnection(self):
        return CardConnection()
