# Installing the compiled code

With the secure bootloader initial installation of the firmware is slightly different. Upgrades are easier and don't require to connect hardware wallet to the computer.

## Flashing initial firmware

**Note** If you don't want to use binaries from the releases check out the [bootloader documentation](https://github.com/cryptoadvance/specter-bootloader/blob/master/doc/selfsigned.md) that explains how to compile and configure it to use your public keys instead of ours.

- Download the `bootloader.bin` and `bootloader.sha256.signed.txt` files from the latest release of [cryptoadvance/specter-bootloader](https://github.com/cryptoadvance/specter-bootloader/releases) repository.
	- Verify the signature of the `bootloader.sha256.signed.txt` file against [Stepan's PGP key](https://stepansnigirev.com/ss-specter-release.asc)
	- Verify the hash of the `bootloader.bin` against the hash stored in the `bootloader.sha256.signed.txt`
- Make sure the [power jumper](./assembly.md) of your discovery board is at STLK position
- Connect the discovery board to your computer via the **miniUSB** cable on the top of the board.
    - The board should appear as a removable disk named `DIS_F469NI`.
- Copy the `bootloader.bin` file into the root of the `DIS_F469NI` filesystem.
- When the board is done flashing the firmware the board will reset itself and reboot to the bootloader. You will see an error message that no firmware is found - it's ok.
- Now you can switch the power jumper where you like it and power the board from the powerbank or battery.

After the bootloader is loaded to the board you need to load Specter firmware to it.
The bootloader will verify the signatures and make sure no downgrades are possible.

## Flashing signed Specter firmware

- Download the `specter_upgrade_<version>.bin` from the [releases](https://github.com/cryptoadvance/specter-diy/releases).
- Copy this binary to the root of the SD card (FAT-formatted)
	- Make sure only one `specter_upgrade***.bin` file is in the root directory
- Insert SD card to the SD slot of the discovery board and power on the board
- Bootloader will flash the firmware and will notify you when it's done.
- Reboot the board - you will see Specter-DIY interface now, it will suggest you to select your PIN code

After you verified that everything is working fine it's time to lock the bootloader into a secure state (RDP and write protection).

## Switching to secure state of the bootloader

- Download the `specter_upgrade_bootloader_<version>.bin` from the last release of [cryptoadvance/specter-bootloader](https://github.com/cryptoadvance/specter-bootloader/releases) repository.
- Put it into the SD card, remove all other `specter_upgrade_*.bin` files from it.
- Insert SD card to the board and reboot it.
- The bootloader will update itself and transfer to the secured state.

Now you are good to go.

## Upgrading firmware

Whenever a new release is out just download the `specter_upgrade_<version>.bin` from the releases, drop it to the SD card and upgrade the device just like in two previous states.
