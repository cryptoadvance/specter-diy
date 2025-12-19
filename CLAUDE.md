Please read
* all the files in docs/architecture
* all files in docs/prd
* docs/debugging.md

Run `scripts/disco --help` to understand your options with the board.

Run `scripts/disco` commands to see whether there is a board connected and in which status it is.

## Serial Device Safety

**Prefer** `scripts/disco` for board/serial interaction - it handles timeouts properly.

If you must access serial devices directly, **always wrap with `timeout`**:

```bash
# DANGEROUS - can freeze session indefinitely:
cat /dev/cu.usbmodem*
echo "test" > /dev/cu.usbmodem*
stty -f /dev/cu.usbmodem* ...

# SAFE - with timeout:
timeout 3 cat /dev/cu.usbmodem*
```
