import shutil
import json
import time
import socket
import subprocess
import os
import signal

class TCPSocket:
    def __init__(self, port=8787):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.connect(("127.0.0.1", port))

    def readline(self, eol=b"\r\n", timeout=3):
        res = b""
        t0 = time.time()
        while not (eol in res):
            # timeout
            if time.time()-t0 > timeout:
                break
            try:
                raw = self.s.recv(1000)
                res += raw
            except Exception as e:
                print(e)
                time.sleep(0.01)
        return res

    def send(self, cmd):
        cmd = json.dumps([cmd])[1:-1]
        self.s.send(str(cmd).encode()+b"\r\n")
        res = self.readline()

    def query(self, data):
        self.s.send(data)
        return self.readline(eol=b"ACK")

    def receive(self):
        return self.readline()

class SimController:
    def __init__(self):
        self.started = False
        self.gui = None
        self.usb = None

    def start(self):
        print("Starting up...")
        try:
            shutil.rmtree("./fs/")
        except:
            pass
        self.proc = subprocess.Popen("../../bin/micropython_unix simulator.py",
                                stdout=subprocess.PIPE,
                                shell=True, preexec_fn=os.setsid)
        time.sleep(1)

    def load(self):
        # command socket
        self.gui = TCPSocket(8787)
        # select PIN
        self.gui.send("")
        # confirm PIN
        self.gui.send("")
        # enter recovery phrase
        self.gui.send(1)
        self.gui.send("abandon "*11+"about")
        # now we can open usb communication
        time.sleep(1)
        self.usb = TCPSocket(8789)

    def shutdown(self):
        print("Shutting down...")
        if self.gui is not None:
            try:
                self.gui.s.send(b"quit\r\n")
                time.sleep(0.3)
            except:
                pass
        os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)  # Send the signal to all the process groups
        time.sleep(1)

    def query(self, data, commands=[]):
        if isinstance(data, str):
            data = data.encode()
        if data[-1:] not in b"\r\n":
            data = data + b"\r\n"
        res = self.usb.query(data)
        assert res == b"ACK\r\n"
        # if we need to confirm anything
        for command in commands:
            sim.gui.send(command)
        res = sim.usb.receive()
        return res.strip()


sim = SimController()