# Simulator

Simulator requires `SDL` library to be installed (`sudo apt install libsdl2-dev` on Linux and `brew install sdl2` on Mac):

To compile the unixport simulator go to `f469-disco` folder and run `./build_unixport.sh`.

If everything goes well you will get a `micropython_unix` binary in this folder.

Now you can run `micropython_unix` binary and ask it to run `main` function of `main.py` file:

```
cd ../src
../f469-disco/micropython_unix -c "import main; main.main()"
```

You should see the screen with the wallet interface. As in unixport we don't have QR code scanner or USB connector, so instead it simulates serial communication and USB on TCP ports: `5941` for QR scanner and `8789` for USB connection. 

You can connect to these ports using `telnet` and type whatever you expect to be scanned / sent from the host.

The simulator is also printing content of the QR codes displayed on the screen to the console.
