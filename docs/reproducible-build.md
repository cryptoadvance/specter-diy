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

At the end of the build you will be presented with a base32 encoded hash of the firmware upgrade file that should be signed and asked to provide signatures.

Get signatures from the description of the github release and enter one by one in the same order as provided in the release.

After adding signatures binaries in the `release` folder should be exactly the same as in github release. Hashes of the binaries will be saved to `release/sha256.txt`.

# Simplified build without signing

If you just need a HEX file without bootloader and signatures you can use this command:

```sh
docker run -ti -v `pwd`:/app diy bash -c "make clean && make disco"
```

This will generate the binaries of the main firmware, which can be flashed into the Discovery board via ST-LINK or ROM bootloader.

```txt
bin/specter-diy.bin
bin/specter-diy.hex
```
