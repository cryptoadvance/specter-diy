#!/bin/bash

set -e

INFO="\e[1;36m"
ENDCOLOR="\e[0m"

echo -e "${INFO}
══════════════════════ Building main firmware ═════════════════════════════
${ENDCOLOR}"
make clean
make disco USE_DBOOT=1

echo -e "${INFO}
═════════════════════ Building secure bootloader ══════════════════════════
${ENDCOLOR}"
cd bootloader
make clean
make stm32f469disco READ_PROTECTION=1 WRITE_PROTECTION=1
cd -

echo -e "${INFO}
══════════════════════ Assembling final binaries ══════════════════════════
${ENDCOLOR}"
mkdir -p release

python3 ./bootloader/tools/make-initial-firmware.py -s ./bootloader/build/stm32f469disco/startup/release/startup.hex -b ./bootloader/build/stm32f469disco/bootloader/release/bootloader.hex -f ./bin/specter-diy.hex -bin ./release/initial_firmware.bin
echo -e "Initial firmware saved to release/initial_firmware.bin"

python3 ./bootloader/tools/upgrade-generator.py gen -f ./bin/specter-diy.hex -b ./bootloader/build/stm32f469disco/bootloader/release/bootloader.hex -p stm32f469disco ./release/specter_upgrade.bin
cp ./release/specter_upgrade.bin ./release/specter_upgrade_unsigned.bin
echo "Unsigned upgrate file saved to release/specter_upgrade_unsigned.bin"

HASH=$(python3 ./bootloader/tools/upgrade-generator.py message ./release/specter_upgrade.bin)

echo "
╔═════════════════════════════════════════════════════════════════════════╗
║                   Message to sign with vendor keys:                     ║
║                                                                         ║
║    ${HASH}    ║
║                                                                         ║
╚═════════════════════════════════════════════════════════════════════════╝
"


echo -e "${INFO}
═════════════════════ Adding signature to the binary ══════════════════════
${ENDCOLOR}"

while true; do
  echo "Provide a signature to add to the upgrade file, or just hit enter to stop."
  read SIGNATURE
  if [ -z $SIGNATURE ]; then
    break
  fi
  python3 ./bootloader/tools/upgrade-generator.py import-sig -s $SIGNATURE ./release/specter_upgrade.bin
  echo "Signature is added: ${SIGNATURE}"
done

echo -e "${INFO}
═════════════════════════ Hashes of the binaries: ═════════════════════════
${ENDCOLOR}"

cd release
sha256sum *.bin > sha256.txt
cat sha256.txt

echo "
Hashes saved to release/sha256.txt file.
"
