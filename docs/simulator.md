# Simulator

Simulator requires `SDL` library to be installed (`sudo apt install libsdl2-dev` on Linux and `brew install sdl2` on Mac).

Run `make unix` to get it. If everything goes well a `micropython_unix` binary will appear in the `bin` folder.

Start simulator using `make simulate`.

You should see the screen with the wallet interface. As in unixport we don't have QR code scanner or USB connector, so instead it simulates serial communication and USB on TCP ports: `5941` for QR scanner and `8789` for USB connection.

You can connect to these ports using `telnet` and type whatever you expect to be scanned / sent from the host.

The simulator is also printing content of the QR codes displayed on the screen to the console.

The simulator create folders in `./fs`:

- `fs/flash` - files that would be stored in the internal flash of the MCU
- `fs/qspi` - files in external QSPI chip (untrusted, everything is stored encrypted and authenticated)
- `fs/ramdisk` - files in external SPIRAM memory (work as temporary storage for host communication, untrusted)
- `fs/sd` - SD card

## Specter-Playground

For a more interactive development experience, check out [specter-playground](https://github.com/k9ert/specter-playground). It is an external community project that builds on top of the simulator and lets you explore and prototype UI scenarios for the Specter hardware without flashing a device.


