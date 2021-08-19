# Installing the compiled code

With the secure bootloader initial installation of the firmware is slightly different. Upgrades are easier and don't require to connect hardware wallet to the computer.

## Flashing initial firmware

**Note** If you don't want to use binaries from the releases check out the [bootloader documentation](https://github.com/cryptoadvance/specter-bootloader/blob/master/doc/selfsigned.md) that explains how to compile and configure it to use your public keys instead of ours.

- If you are upgrading from versions below `1.4.0` or uploading the firmware for the first time, use the `initial_firmware_<version>.bin` from the [releases](https://github.com/cryptoadvance/specter-diy/releases) page.
	- Verify the signature of the `sha256.signed.txt` file against [Stepan's PGP key](https://stepansnigirev.com/ss-specter-release.asc)
	- Verify the hash of the `initial_firmware_<version>.bin` against the hash stored in the `sha256.signed.txt`
- If you are upgrading from an empty bootloader or you see the bootloader error message that firmware is not valid, check out the next section - [Flashing signed Specter firmware](#flashing-signed-specter-firmware).
- Make sure the [power jumper](./assembly.md) of your discovery board is at STLK position
- Connect the discovery board to your computer via the **miniUSB** cable on the top of the board.
    - The board should appear as a removable disk named `DIS_F469NI`.
- Copy the `initial_firmware_<version>.bin` file into the root of the `DIS_F469NI` filesystem.
- When the board is done flashing the firmware the board will reset itself and reboot to the bootloader. Bootloader will check the firmware and boot into the main firmware. If see an error message that no firmware is found - follow the update instructions and upload firmware via SD card.
- Now you can switch the power jumper where you like it and power the board from the powerbank or battery.

> Flashing initial firmware via copy-paste of the `.bin` file sometimes fails - often because of the cable, or if you connect the device through a USB hub. In this case you can try a few more times (normally works in 2-3 attempts).
> 
> If it fails all the time you can use [stlink](https://github.com/stlink-org/stlink/releases/latest) open-source tool. Install it and type in your terminal: `st-flash write <path/to/initial_firmare.bin> 0x8000000`. It usually works much more reliable.

## Flashing signed Specter firmware

- Download the `specter_upgrade_<version>.bin` from the [releases](https://github.com/cryptoadvance/specter-diy/releases).
- Copy this binary to the root of the SD card (FAT-formatted)
	- Make sure only one `specter_upgrade***.bin` file is in the root directory
- Insert SD card to the SD slot of the discovery board and power on the board
- Bootloader will flash the firmware and will notify you when it's done.
- Reboot the board - you will see Specter-DIY interface now, it will suggest you to select your PIN code

## Upgrading firmware later on

Whenever a new release is out just download the `specter_upgrade_<version>.bin` from the releases, drop it to the SD card and upgrade the device just like in the previous step. Bootloader will make sure only signed firmware can be loaded to the board.

## How to find out firmware version

Create an empty file on the SD card named `.show_version` and insert into the device. On every boot the bootloader will check if this file is present and if so - it will show information about current firmware and bootloader versions.
