"""Copia arquivos para o filesystem da placa pelo REPL cru e roda um comando."""
import sys, time, serial

PORT = '/dev/ttyACM0'

def enter_raw(s):
    s.write(b'\x03\x03'); time.sleep(0.3); s.reset_input_buffer()
    s.write(b'\x01'); time.sleep(0.3); s.read(4096)

def raw_exec(s, code, wait=3.0):
    s.write(code.encode() + b'\x04')
    time.sleep(wait)
    return s.read(1 << 20).decode('utf-8', 'replace')

def put(s, local, remote):
    data = open(local, 'rb').read()
    raw_exec(s, "f=open(%r,'wb')\n" % remote, 0.4)
    for i in range(0, len(data), 256):
        raw_exec(s, "f.write(%r)\n" % data[i:i+256], 0.12)
    raw_exec(s, "f.close()\n", 0.4)
    return len(data)

def main():
    files = sys.argv[1:-1]
    command = sys.argv[-1]
    s = serial.Serial(PORT, 115200, timeout=1)
    enter_raw(s)
    for spec in files:
        local, _, remote = spec.partition(':')
        remote = remote or '/' + local.rsplit('/', 1)[-1]
        print("-> %s (%d bytes)" % (remote, put(s, local, remote)))
    out = raw_exec(s, command + "\n", 12.0)
    s.write(b'\x02')  # volta ao REPL amigavel
    s.close()
    print(out.replace('\x04', '').replace('>OK', '').strip())

main()
