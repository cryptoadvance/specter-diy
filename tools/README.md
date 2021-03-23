# Tools

## `hwidevice.py`

This is a HWIv2-compatible driver for Specter-DIY. If you run it with `python3 hwidevice.py` it will try to find connected DIY devices and get some basic info from it.

If you run it with `-i` flag it becomes interactive and you can communicate with the device or simulator over USB (or virtual USB in case of simulator).

## `apps`

[`apps`](./apps) folder contains a collection of scripts used to prepare and sign your Specter-DIY apps. See corresponding [readme](./apps/README.md) for info.