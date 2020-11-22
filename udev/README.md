# udev rules

This directory contains udev rules for micropython & Specter DIY.
These are necessary for the devices to be reachable on linux environments.

 - `49-micropython.rules` (Specter-DIY): http://wiki.micropython.org/Installation#USB-Permissioning-on-Linux

Specter is connected as a virtual serial port, so you need to add yourself to `dialout` group.

# Usage

Apply these rules by copying them to `/etc/udev/rules.d/` and notifying `udevadm`.
Your user will need to be added to the `plugdev` group, which needs to be created if it does not already exist.

```
$ sudo cp 49-micropython.rules /etc/udev/rules.d/
$ sudo udevadm trigger
$ sudo udevadm control --reload-rules
$ sudo groupadd plugdev
$ sudo usermod -aG plugdev `whoami`
$ sudo usermod -aG dialout `whoami`
```