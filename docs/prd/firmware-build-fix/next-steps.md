# Next Steps

## Immediate Actions (Priority Order)

1. **Set up debugging hardware**
   - Connect STM32F469 Discovery board via USB (built-in ST-Link debugger)
   - Verify software prerequisites installed: OpenOCD, GDB (see Prerequisites section)
   - Test OpenOCD connection: `openocd -f board/stm32f469discovery.cfg`
   - Verify GDB can attach and read registers

2. **Attempt minimal firmware build**
   - Create simple frozen manifest: `manifests/minimal.py` with hello world
   - Build with: `make disco USE_DBOOT=1 FROZEN_MANIFEST=manifests/minimal.py`
   - Check binary size (should be much smaller without modules)

3. **Reproduce flash failure with monitoring**
   - Attempt flash while debugger attached
   - Document exact point of failure
   - Check for error messages or status codes

4. **Verify memory layout**
   - Use `arm-none-eabi-readelf -h bin/specter-diy.elf` to check entry point
   - Use `arm-none-eabi-objdump -h bin/specter-diy.elf` to check section addresses
   - Verify firmware TEXT0_ADDR = 0x08020000

5. **Test known-good v1.x firmware (if available)**
   - Flash working v1.x firmware as baseline
   - Verify bootloader still functions correctly
   - Document differences in behavior

---
