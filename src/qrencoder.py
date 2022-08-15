import math
from microur.util.bytewords import stream_pos
from microur.encoder import UREncoder
from bcur import bcur_encode_stream
from helpers import b2a_base64_stream, read_write

class QREncoder:
    """A simple encoder that just splits the data into chunks"""
    is_infinite = False
    MAX_PREFIX_LEN = 0

    def __init__(self, stream, part_len=300, tempfile=None):
        if tempfile is None:
            raise ValueError("Temp file is required for this encoder")
        with open(tempfile, "wb") as fout:
            self._start, self._len = self.convert(stream, fout)
        self.tempfile = tempfile
        self.f = None
        self._start = 0
        self._num = 0
        self.part_len = part_len

    def convert(self, fin, fout):
        # dummy convertion, just copy to the tempfile
        return 0, read_write(fin, fout)

    @property
    def part_len(self):
        return self._part_len

    @part_len.setter
    def part_len(self, part_len):
        if part_len > 2 * self.MAX_PREFIX_LEN:
            part_len -= self.MAX_PREFIX_LEN
        self._part_len = math.ceil(self._len / math.ceil(self._len / part_len))

    def get_full(self, maxlen=None):
        if maxlen is not None and maxlen < self._len:
            return ""
        self.f.seek(0, 0)
        return self.f.read()

    def __len__(self):
        return math.ceil(self._len / self.part_len)

    def __getitem__(self, idx):
        idx = idx % len(self)
        self.f.seek(self._start + idx*self.part_len, 0)
        return self.f.read(self.part_len)

    def __iter__(self):
        self._num = 0
        return self

    def __next__(self):
        if self._num >= len(self):
            raise StopIteration
        self._num += 1
        return self.__getitem__(self._num-1)

    def __enter__(self):
        if self.f is None:
            self.f = open(self.tempfile, "r")
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        if self.f is not None:
            self.f.close()

    def __str__(self):
        return self.get_full()

class Base64QREncoder(QREncoder):
    MAX_PREFIX_LEN = 8

    def convert(self, fin ,fout):
        return 0, b2a_base64_stream(fin, fout)

    def __getitem__(self, idx):
        idx = idx % len(self)
        self.f.seek(self._start + idx*self.part_len, 0)
        return "p%dof%d %s" % (idx+1, len(self), self.f.read(self.part_len))

class LegacyBCUREncoder(QREncoder):
    MAX_PREFIX_LEN = 73 # uh... large one, and pretty useless

    def convert(self, fin ,fout):
        cur, sz = stream_pos(fin)
        sz, enc_hash = bcur_encode_stream(fin, fout, size=sz)
        self.enc_hash = enc_hash.decode()
        return 0, sz

    def get_full(self, maxlen=None):
        if maxlen is not None and maxlen < self._len+9:
            return ""
        self.f.seek(0, 0)
        return "UR:BYTES/" + self.f.read()

    def __getitem__(self, idx):
        if len(self) == 1:
            return "UR:BYTES/" + self.f.read()
        idx = idx % len(self)
        self.f.seek(self._start + idx*self.part_len, 0)
        return "UR:BYTES/%dOF%d/%s/%s" % (idx+1, len(self), self.enc_hash, self.f.read(self.part_len))

class CryptoPSBTEncoder(QREncoder):
    is_infinite = True
    MAX_PREFIX_LEN = 22

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.encoder = None

    def __len__(self):
        return self.encoder.seq_len

    def get_full(self, maxlen=None):
        return "" # we don't support full here yet

    def __enter__(self):
        super().__enter__()
        self.encoder = UREncoder(UREncoder.CRYPTO_PSBT, self.f, self._part_len)
        return self

    def __exit__(self, *args, **kwargs):
        del self.encoder
        super().__exit__(*args, **kwargs)

    def __getitem__(self, idx):
        return self.encoder.get_part(idx)
