# Roadmap for Specter-DIY development

Security critical features:

- GUI alert on exception
- optional secure bootloader checking signatures on the firmware
- make sure that code and secrets are stored on **internal** flash, not QSPI (see [dual_flash_storage branch](https://github.com/diybitcoinhardware/micropython/tree/dual_flash_storage))
- secure poweroff that erases all the secrets from RAM
- moving device secret to the very beginning of the flash or even to the bootloader
- smartcard integration for key storage
- add tests, fuzzing, catch random crashes
- optimize the code

Documentation:

- firmware protection instructions with tools from STM

Would be nice to add:

- Devkit (WIP)
- SD card support
