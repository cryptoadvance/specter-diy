# Specter-DIY

![](./docs/pictures/kit.jpg)

## DISCLAIMER

This firmware is **WORK IN PROGRESS — USE AT YOUR OWN RISK**, better on testnet. It is not perfectly stable yet - sometimes it crashes. If this happens to you please open an issue and we will try to fix it. Meanwhile try reseting the device (press the black button on the back or powercycle the board).

This wallet is a **FUNCTIONAL PROTOTYPE**. This means we use it to experiment with user interface, communication methods and new interesting features (like anti chosen-nonce protocol, CoinJoin and Lightning). That's why **by default we don't store your private keys on the device** - you need to type your recovery phrase every time you power it on. You still can save your recovery phrase to the device if you wish - there is a setting for that.

If something doesn't work open an issue here or ask a question in our [Telegram group](https://t.me/spectersupport) or [Slack](https://join.slack.com/t/spectersupport/shared_invite/enQtNzY4MTQ2MTg0NDY1LWQzMGMzMTk2MWE2YmVmNzE3ODgxODIxNWRlMzJjZTZlMDBlMjA5YzVhZjQ0NzJlNmE0N2Q4MzE0ZGJiNjM4NTY).

## What is this project for?

It is a Do-It-Yourself airgapped hardware wallet that uses QR codes for communication with the computer (i.e. [Specter Desktop app](https://github.com/cryptoadvance/specter-desktop) on top of Bitcoin Core). It can be used in your multisignature setup  as an additional signer with a completely different security model:

- It can be built from off-the-shelf hardware - this reduces chance of the supply chain attack
- It is airgapped with a very limited uni-directional communication protocol (QR codes) - you fully control communication with the host
- You can adapt it to your security model. Most of the firmware is written in MicroPython which makes the code easy to audit and change.

## Documentation

All the docs are stored in the [`docs/`](./docs) folder:

- [`shopping.md`](./docs/shopping.md) explains what to buy
- [`quickstart.md`](./docs/quickstart.md) guides you through the initial steps how to get firmware on the board
- [`security.md`](./docs/security.md) explains possible attack vectors and security model of the project
- [`development.md`](./docs/development.md) explains how to start developing on Specter
- [`simulator.md`](./docs/simulator.md) shows how to run a simulator on unix/macOS
- [`communication.md`](./docs/communication.md) defines communication protocol with the host over QR codes and USB
- [`roadmap.md`](./docs/roadmap.md) explains what we need to implement before we can consider the wallet be ready to use with real funds.

Supported networks: Mainnet, Testnet, Regtest, Signet.

## Video and screenshots

Check out [this Twitter thread](https://twitter.com/StepanSnigirev/status/1168923849699876881) to get an idea how it works.

A few pictures:

### Wallet screens

![](./docs/pictures/wallet_screens.jpg)

### Key generation and recovery

![](./docs/pictures/init_screens.jpg)
