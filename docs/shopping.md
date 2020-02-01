# Shopping list for Specter-DIY

## Discovery board

Main part of the device is the developer board:

- STM32F469I-DISCO developer board (i.e. from [Mouser](https://eu.mouser.com/ProductDetail/STMicroelectronics/STM32F469I-DISCO?qs=kWQV1gtkNndotCjy2DKZ4w==) or [Digikey](https://www.digikey.com/product-detail/en/stmicroelectronics/STM32F469I-DISCO/497-15990-ND/5428811))
- **Mini**USB cable (for example [this](https://eu.mouser.com/ProductDetail/Omron-Automation-and-Safety/USB-MINIUSB?qs=sGAEpiMZZMt93J8DTi5DC6y9EQiX1Vkv))

For the rest of the components we are currently working on [a devkit](../devkit) that includes a smartcard slot, QR code scanner, battery and a 3d printed case, but it doesn't include the main part — discovery board that you need to order separately. This way supply chain attack is still not an issue as the security-critical components are bought from random electronic store.

You can start using Specter even without any extra components, but you will be able to communicate with it only over USB. In this case it's not airgapped so you lose an important security property.

## QR scanner

For QR code scanner you have several options.

**Option 1.** Resonably good scanner from Waveshare (40$)

- [Waveshare scanner](https://www.waveshare.com/barcode-scanner-module.htm) - you will need to find a way how to mount it nicely, maybe use some kind of Arduino Prototype shield and some ducktape. For wiring see [here](./waveshare.md).

**Option 2.** Extremely nice scanner from Mikroe but pretty expensive (150$):

- [Barcode Click](https://www.mikroe.com/barcode-click) + [Adapter](https://www.mikroe.com/arduino-uno-click-shield)

**Option 3.** Any other QR scanner

You can find some cheap scanners in China. Their quality is often not that great, but you can take a chance. Maybe even ESPcamera would do the job. You only need to connect power, UART (pins D0 and D1), and trigger to D5. 

**Option 4.** No scanner. 

Then you can only use Specter with USB.

Unless you build your own communication module that uses something else instead of QR codes - audiomodem, bluetooth or whatever else. As soon as it can be triggered and send the data over serial you can do whatever you want.

## Optional components

If you add a battery & power charger/booster then your wallet becomes completely self-contained ;)
