# Specter-DIY

    "Cypherpunks write code. We know that someone has to write software to defend privacy, 
    and since we can't get privacy unless we all do, we're going to write it."
    A Cypherpunk's Manifesto - Eric Hughes - 9 March 1993

    ...and Cypherpunks do build their own Bitcoin Hardware Wallets.

![](./docs/pictures/kit.jpg)

The idea of the project is to build a hardware wallet from off-the-shelf components.
Even though we have [an extension board](./shield) that puts everything in a nice form-factor and helps you to avoid any soldering, we will continue supporting and maintaining compatibility with standard components.

We also want to keep the project flexible such that it can work on any other set of components with minimal changes. Maybe you want to make a hardware wallet on a different architecture (RISC-V?), with an audio modem as a communication channel - you should be able to do it. It should be easy to add or change functionality of Specter and we try to abstract logical modules as much as we can.

QR codes are a default way for Specter to communicate with the host. QR codes are pretty convenient and allow the user to be in control of the data transmission - every QR code has a very limited capacity and communication happens unidirectionally. And it's airgapped - you don't need to connect the wallet to the computer at any time.

For secret storage we support agnostic mode (wallet forgets all secrets when turned off), reckless mode (stores secrets in flash of the application microcontroller) and secure element integration is coming soon.

Our main focus is multisignature setup with other hardware wallets, but wallet can also work as a single signer. We try to make it compatible with Bitcoin Core where we can - PSBT for unsigned transactions, wallet descriptors for importing/exporting multisig wallets. To communicate with Bitcoin Core easier we are also working on [Specter Desktop app](https://github.com/cryptoadvance/specter-desktop) - a small python flask server talking to your Bitcoin Core node.

Most of the firmware is written in MicroPython which makes the code easy to audit and change. We use [secp256k1](https://github.com/bitcoin-core/secp256k1) library from Bitcoin Core for elliptic curve calculations and [LittlevGL](https://littlevgl.com/) library for GUI.

## DISCLAIMER

The project has significantly matured, to the extent that the security level of Specter-DIY is now comparable to commercial hardware wallets on the market. We implemented a secure bootloader that verifies firmware upgrades, so you can be sure that only signed firmware can be uploaded to the device after initial setup. However, unlike with commercial signing devices the bootloader has to be installed manually by the user and is not set in the factory of the device vendor. Thus, pay extra attention during the initial firmware installation and make sure you verified PGP signatures and flash the firmware from a secure computer.

If something doesn't work open an issue here or ask a question in our [Telegram group](https://t.me/+VEinVSYkW5TUl5Ai).

## Documentation

All the docs are stored in the [`docs/`](./docs) folder:

- [`shopping.md`](./docs/shopping.md) explains what to buy
- [`assembly.md`](./docs/assembly.md) shows how to put everything together.
- [`quickstart.md`](./docs/quickstart.md) guides you through the initial steps how to get firmware on the board
- [`reproducible-build.md`](./docs/reproducible-build.md) describes how to build the initial firmware and upgrade files with the same hash as in the release using Docker
- [`build.md`](./docs/build.md) describes how to build the firmware and the simulator yourself
- [`security.md`](./docs/security.md) explains possible attack vectors and security model of the project
- [`development.md`](./docs/development.md) explains how to start developing on Specter
- [`simulator.md`](./docs/simulator.md) shows how to run a simulator on unix/macOS
- [`communication.md`](./docs/communication.md) defines communication protocol with the host over QR codes and USB
- [`roadmap.md`](./docs/roadmap.md) explains what we need to implement before we can consider the wallet be ready to use with real funds.

Specter-Shield documentation and all the files are available in the [`shield/`](./shield) folder:

- [What it looks like](./shield/README.md)
- [How to print a 3d case](./shield/3dprinting.md)

Supported networks: Mainnet, Testnet, Regtest, Signet.

## USB communication on Linux

You may need to set up udev rules and add yourself to `dialout` group. Read more in [`udev`](./udev/README.md) folder.

## Video and screenshots

Check out [this video](https://www.youtube.com/watch?v=1H7FqG_FmCw) to get an idea how to assemble it and how it works.

Here is a [Gallery](./docs/pictures/gallery/README.md) with devices assembled by the community.

A few pictures of the UI:

### Wallet screens

![](./docs/pictures/wallet_screens.jpg)

### Key generation and recovery

![](./docs/pictures/init_screens.jpg)
