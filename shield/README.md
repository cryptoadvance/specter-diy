# Specter Shield

Specter shield is an extension board for F469-Discovery board by STMicroelectronics. It uses a standard Arduino headers so it might work with other boards with Arduino headers as well.

It includes a QR scanner, smartcard slot and a battery. All elements are not security-critical - QR scanner only captures images and sends scanned data to the main MCU over dead-simple serial interface, smartcard controller learns nothing about the data transmitted to the secure element as communication with it is encrypted.

Structure diagram, pinout and schematics are available in this folder and on [circuitmaker](https://circuitmaker.com/Projects/Details/MikhailTolkachev/specter-shield). To manufacture the kit yourself just send the content of the [`specter-shield`](./specter-shield/) folder to the PCB manufacturer.

For the QR scanner we use GROW GM65-S scanner.

Available in [our shop](https://specter.solutions/shop/specter-shield/). Assembled kit look like this:

![](./3dshield.jpg)

## Print the case for Specter-DIY + Shield:

- Design by @geometrick-design: https://www.thingiverse.com/thing:4671552, [instructions](3dprinting.md)
- Design by @SeedSigner: https://www.thingiverse.com/thing:4733846, [files and instructions](./Alternative_3D_Printed_Case)
