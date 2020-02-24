# this script is useful for debugging and developing
# it automatically loads specter, sets entropy and initializes keys
# you can change it to go to some particular screen or functionality
# here for example it goes to "sign transaction" screen
import main as specter

def main():
	specter.main(False)
	specter.entropy = b'\x8f\xc7i\x03u\x84\xecj\t%q\xeb\x14\x9aKK\xb2O\xa1__\xab$i'
	specter.init_keys("")

	# test wallet import
	wallet = "MoreMultisig&wsh(sortedmulti(2,[8cce63f8/48h/1h/0h/2h]tpubDF3Nnrvc5wjeiPc9yfcGAqg5Co3obX5BXS5Cn1Azs8eitQD9mwKzCFVkMavgWcVBmre9cKhrk7sGcov34RhKkDp46d2r8DnJDBA7m8Uz68D,[16eee265/48h/1h/0h/2h]tpubDErr96huTofYKcxcUrh7raUM2F1Q1ojvEzNXAWfAZ9wMrvshJnHNDgeV18UUeFCDRMZVSaecp4sAPXWgeKhJUZxHrz8cVXj3zTNmCaMBL17,[3aa5c770/48h/1h/0h/2h]tpubDEELUh8vms8q6WrZnrZpQEGBDP5iuPfHMf6tDfUj34WjtK5Zt4iagPTAKnq59ATSakbYY56WA8gJiJhwxoVDV1sYRyQ84Qrp8juhQ15ZWxw))"
	specter.parse_new_wallet(wallet)

	# or test tx signing
	# tx = "cHNidP8BAHICAAAAAU8to85Xo1JDKG2dfvkcRYHTVKX67ELnixmvVHH0ThyTAAAAAAD+////AqCGAQAAAAAAF6kU882+nVMDKGj4rKzjDB6NjyJqSBCHKCoSAAAAAAAWABQqcs9Y7Zo8QjuKFPRi8VNPcgKBWQAAAAAAAQEfVrETAAAAAAAWABQRqqwP0wG9TmsGaO2p7a+zxNrlFyIGAkM1xkguJvhHARCWNeiib/Yk7TjmKmO66vJfEi+HUokMGIzOY/hUAACAAQAAgAAAAIAAAAAAAQAAAAAAIgICQlSVCCKFEDXEo4YdHwiNh8pZ94/iJadOKMpn2om/tw4YjM5j+FQAAIABAACAAAAAgAEAAAABAAAAAA=="
	# specter.parse_transaction(tx)
	specter.ioloop()