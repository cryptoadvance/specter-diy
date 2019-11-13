from bitcoin import bip32

class KeyStore:
	def __init__(self, seed=None):
		self.root = None
		self.load_seed(seed)

	def load_seed(self, seed):
		if seed is not None:
			self.root = bip32.HDKey.from_seed(seed)