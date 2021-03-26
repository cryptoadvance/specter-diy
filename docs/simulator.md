# Simulator

Simulator requires `SDL` library to be installed (`sudo apt install libsdl2-dev` on Linux and `brew install sdl2` on Mac).

Run `make unix` to get it. If everything goes well a `micropython_unix` binary will appear in the `bin` folder.

Start simulator using `make simulate`.

You should see the screen with the wallet interface. As in unixport we don't have QR code scanner or USB connector, so instead it simulates serial communication and USB on TCP ports: `5941` for QR scanner and `8789` for USB connection.

You can connect to these ports using `telnet` and type whatever you expect to be scanned / sent from the host.

The simulator is also printing content of the QR codes displayed on the screen to the console.


The simulator create folders in `./fs`, one of them is called `sd`. Files located in this directory can be used within the simulator.


