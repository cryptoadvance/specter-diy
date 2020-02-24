# this script is useful for debugging and developing
# it automatically loads specter, sets entropy and initializes keys
# you can change it to go to some particular screen or functionality
# here for example it goes to "sign transaction" screen
import main as specter

def main():
	specter.main(False)
	specter.entropy = b'\x8f\xc7i\x03u\x84\xecj\t%q\xeb\x14\x9aKK\xb2O\xa1__\xab$i'
	specter.init_keys("")
	tx = "cHNidP8BAHICAAAAAU8to85Xo1JDKG2dfvkcRYHTVKX67ELnixmvVHH0ThyTAAAAAAD+////AqCGAQAAAAAAF6kU882+nVMDKGj4rKzjDB6NjyJqSBCHKCoSAAAAAAAWABQqcs9Y7Zo8QjuKFPRi8VNPcgKBWQAAAAAAAQEfVrETAAAAAAAWABQRqqwP0wG9TmsGaO2p7a+zxNrlFyIGAkM1xkguJvhHARCWNeiib/Yk7TjmKmO66vJfEi+HUokMGIzOY/hUAACAAQAAgAAAAIAAAAAAAQAAAAAAIgICQlSVCCKFEDXEo4YdHwiNh8pZ94/iJadOKMpn2om/tw4YjM5j+FQAAIABAACAAAAAgAEAAAABAAAAAA=="
	specter.parse_transaction(tx)
	specter.ioloop()