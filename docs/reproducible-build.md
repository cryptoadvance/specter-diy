# Reproducible build

With [docker](https://docs.docker.com/get-docker/) you can build the firmware yourself in the same environment as we do, and verify that binaries in github releases have the same hash. This way you can be sure that firmware upgrades signed by our public keys are actually built from the code in this repository, no backdoors included.

From the root of the repository:

1. Set up bootloader to use production keys:

```sh
cp bootloader/keys/production/pubkeys.c bootloader/keys/selfsigned/
```

2. Build a docker container:

```sh
docker build -t diy .
```

3. Run the container in interactive mode:

```sh
docker run -ti -v `pwd`:/app diy
```

The container runs `./build_firmware.sh`, which now also drops `release/disco-nobootloader.{bin,hex}` alongside the signed
artifacts. The `disco-nobootloader.bin` image matches the standard `nix build` output and can be flashed directly to a
development board when you want to skip the secure bootloader during testing.

At the end of the build you will be presented with a base32 encoded hash of the firmware upgrade file that should be signed and asked to provide signatures.

Get signatures from the description of the github release and enter one by one in the same order as provided in the release.

After adding signatures binaries in the `release` folder should be exactly the same as in github release. Hashes of the binaries will be saved to `release/sha256.txt`.

# Apple M1 users

For Apple M1 add a plafrom flag to the docker commands:

```sh
docker build -t diy . --platform linux/x86_64
docker run --platform linux/amd64 -ti -v `pwd`:/app diy
```
