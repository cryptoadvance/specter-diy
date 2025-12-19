# Coding Standards

This document defines the coding standards and conventions for the Specter-DIY project.

## Table of Contents

- [Overview](#overview)
- [Python Coding Standards](#python-coding-standards)
- [C Coding Standards](#c-coding-standards)
- [Git Commit Conventions](#git-commit-conventions)
- [Code Formatting Tools](#code-formatting-tools)
- [Documentation Standards](#documentation-standards)

---

## Overview

Specter-DIY is a mixed-language codebase with MicroPython (Python) for application logic and C for embedded systems programming (bootloader, custom MicroPython modules). We follow industry-standard conventions with project-specific adaptations.

**Core Principles:**
- **Consistency:** Code should look like it was written by one person
- **Readability:** Code is read more often than written
- **Security:** This is a Bitcoin hardware wallet - security is paramount
- **Maintainability:** Code should be easy to understand and modify

---

## Python Coding Standards

### General Guidelines

Python code in Specter-DIY follows [PEP 8](https://peps.python.org/pep-0008/) with MicroPython-specific adaptations.

**Key Requirements:**
- Auto-formatted using [ruff format](https://docs.astral.sh/ruff/formatter)
- Line length: **99 characters**
- Encoding: UTF-8
- Indentation: **4 spaces** (no tabs)

### Naming Conventions

Follow these naming patterns consistently:

```python
# Modules: short, all lowercase
import platform
import keystore

# Classes: CamelCase (abbreviations all uppercase)
class KeyStore:
    pass

class SDHost:
    pass

class I2C:  # Not I2c
    pass

# Functions and methods: lowercase with underscores
def load_apps():
    pass

def mem_read(address, size):
    pass

# Constants: all uppercase with underscores
GPIO_IDR = 0x10
MAX_RETRIES = 3
DEFAULT_NETWORK = "main"

# Private attributes/methods: single leading underscore
class Wallet:
    def __init__(self):
        self._private_key = None

    def _internal_method(self):
        pass
```

### Code Structure

**Imports:**
- Group imports in this order:
  1. Standard library imports
  2. Related third-party imports
  3. Local application imports
- Separate groups with blank lines
- Avoid wildcard imports (`from module import *`)

```python
# Standard library
import os
import sys

# MicroPython/third-party
import display
import lvgl as lv

# Local
from keystore import KeyStore
from helpers import load_apps
```

**Docstrings:**
- Use docstrings for modules, classes, and public functions
- Follow [PEP 257](https://peps.python.org/pep-0257/) conventions
- Keep docstrings concise - this runs on embedded hardware

```python
def verify_signature(message, signature, pubkey):
    """
    Verify an ECDSA signature against a message.

    Returns True if valid, False otherwise.
    """
    pass
```

**Comments:**
- Use comments sparingly - code should be self-documenting
- Explain **why**, not **what**
- Keep comments up-to-date with code changes

```python
# Good: Explains why
# Use SDRAM for temp storage to preserve flash write cycles
rampath = platform.mount_sdram()

# Bad: States the obvious
# Create a variable called rampath
rampath = platform.mount_sdram()
```

### MicroPython-Specific Considerations

**Memory Efficiency:**
- Avoid allocating large objects unnecessarily
- Reuse buffers when possible
- Be mindful of garbage collection

**Hardware Interaction:**
- Use platform abstraction in `platform.py`
- Never hardcode hardware addresses in application code
- Always handle hardware failures gracefully

```python
# Good: Platform abstraction
import platform
path = platform.fpath("/flash/keystore")

# Bad: Hardcoded path
path = "/flash/keystore"
```

### Error Handling

**Exceptions:**
- Use specific exception types
- Always catch specific exceptions, not bare `except:`
- Clean up resources in `finally` blocks

```python
# Good
try:
    data = read_from_sdcard()
except OSError as e:
    logger.error(f"SD card read failed: {e}")
    return None
finally:
    close_sdcard()

# Bad
try:
    data = read_from_sdcard()
except:
    pass
```

### Security Considerations

**Critical for Bitcoin Wallet:**
- Never log private keys or sensitive material
- Zero out sensitive data when no longer needed
- Use constant-time comparisons for secrets
- Validate all external inputs

```python
# Good: Clear sensitive data
def sign_transaction(privkey, tx):
    signature = do_sign(privkey, tx)
    # Zero out private key
    privkey = None
    return signature

# Bad: Leaves key in memory
def sign_transaction(privkey, tx):
    return do_sign(privkey, tx)
```

---

## C Coding Standards

C code is used in the bootloader and custom MicroPython modules. We follow MicroPython conventions with security hardening.

### General Guidelines

**Key Requirements:**
- Auto-formatted using [uncrustify](https://github.com/uncrustify/uncrustify) v0.71 or v0.72
- Configuration: `f469-disco/micropython/tools/uncrustify.cfg`
- Indentation: **4 spaces** (no tabs)
- Line length: Keep reasonable (prefer < 100 characters)

### Naming Conventions

```c
// Functions and variables: underscore_case
void init_display(void);
int buffer_size = 0;

// Types: underscore_case with _t suffix
typedef struct _keystore_t {
    uint8_t *data;
    size_t len;
} keystore_t;

// Macros and enums: CAPS_WITH_UNDERSCORE
#define MAX_BUFFER_SIZE 1024
#define GPIO_PIN_HIGH   1

enum {
    STATE_IDLE,
    STATE_ACTIVE,
    STATE_ERROR
};
```

### Code Style

**Whitespace:**
- Expand tabs to 4 spaces
- No trailing whitespace
- One space after keywords: `if (`, `for (`, `while (`
- One space after commas and around operators

**Braces:**
- Use braces for all blocks (even single-line)
- Opening brace on same line as statement
- `else` on same line as closing brace

```c
// Good
if (condition) {
    do_something();
} else {
    do_other();
}

// Bad
if (condition)
    do_something();
```

**Header Files:**
- Protect from multiple inclusion with include guards
- Use descriptive guard names

```c
#ifndef SPECTER_KEYSTORE_H
#define SPECTER_KEYSTORE_H

// Header content

#endif // SPECTER_KEYSTORE_H
```

### Integer Types

MicroPython runs on various architectures. Use correct types:

```c
// MicroPython-specific types (preferred)
mp_int_t signed_value;      // Machine word-sized signed int
mp_uint_t unsigned_value;   // Machine word-sized unsigned int

// Standard types
size_t byte_count;          // For sizes/counts
uint8_t byte_value;         // Explicit 8-bit
uint32_t word_value;        // Explicit 32-bit

// Avoid bare int/uint unless you know what you're doing
```

### Comments

Use `//` prefix, not `/* ... */`:

```c
// Initialize the display hardware
void init_display(void) {
    // Configure GPIO pins for LCD interface
    gpio_init();

    // Good: Explains non-obvious logic
    // Wait 100ms for display power-up sequence
    delay_ms(100);
}
```

### Memory Management

**In MicroPython modules:**
- Use `m_new`, `m_renew`, `m_del` macros (defined in `py/misc.h`)
- Never use `malloc`/`free` directly

```c
// Good
uint8_t *buffer = m_new(uint8_t, size);
// ... use buffer ...
m_del(uint8_t, buffer, size);

// Bad (in MicroPython context)
uint8_t *buffer = malloc(size);
```

**In bootloader:**
- Keep heap allocations minimal
- Prefer stack allocation for small buffers
- Always check allocation results

### Security Considerations

**Bootloader (critical):**
- Signature verification must be constant-time
- Never skip security checks
- Fail secure (on error, halt; don't continue)
- Clear sensitive data (keys, signatures) after use

```c
// Good: Constant-time comparison
int secure_compare(const uint8_t *a, const uint8_t *b, size_t len) {
    volatile uint8_t result = 0;
    for (size_t i = 0; i < len; i++) {
        result |= a[i] ^ b[i];
    }
    return result == 0;
}

// Bad: Early return leaks timing info
int insecure_compare(const uint8_t *a, const uint8_t *b, size_t len) {
    for (size_t i = 0; i < len; i++) {
        if (a[i] != b[i]) return 0;
    }
    return 1;
}
```

---

## Git Commit Conventions

### Commit Message Format

Each commit message must follow this structure:

```
<prefix>: <subject>

<body>

Signed-off-by: Your Name <your.email@example.com>
```

**Prefix:**
- Use directory or file path prefix to show affected area
- Examples: `src/keystore:`, `bootloader/core:`, `docs/build:`, `f469-disco/usermods/secp256k1:`
- For multi-area changes: `src/gui, src/apps:`

**Subject Line:**
- Describe change clearly and concisely
- Use imperative mood ("Add feature" not "Added feature")
- Start with capital letter, end with period
- Must fit within **72 characters** (including prefix)

**Body (optional):**
- Add blank line after subject
- Explain **why** the change was made
- Provide context for complex changes
- Lines must fit within **75 characters**
- Required for changes > 5 lines

**Sign-off:**
- Always required: `git commit -s`
- Certifies you have rights to submit this code
- Use real name and active email

### Good Commit Examples

```
src/keystore: Add support for SD card key storage.

Implements SDKeyStore class for storing keys on external SD card.
This enables cold storage mode where keys never touch internal flash.

Signed-off-by: Alice Developer <alice@example.com>
```

```
bootloader: Fix signature verification timing leak.

Replace byte-by-byte comparison with constant-time comparison
to prevent timing attacks on signature verification.

Signed-off-by: Bob Security <bob@example.com>
```

```
docs/build: Update Nix shell instructions.

Signed-off-by: Charlie Writer <charlie@example.com>
```

### Bad Commit Examples

```
# Bad: No prefix
Fixed a bug

# Bad: Vague, no period, too long subject line
src/keystore: made some changes to the keystore module because it wasn't working right

# Bad: No sign-off
src/gui: Add dark mode.

# Bad: Past tense
src/apps: Added wallet backup feature.
```

### When to Commit

- Commit logical units of work
- Each commit should compile and pass tests
- Don't commit commented-out code
- Don't commit work-in-progress (or prefix with `WIP:`)

---

## Code Formatting Tools

### Python: Ruff

**Installation:**
```bash
pip install ruff
```

**Usage:**
```bash
# Format code
ruff format src/

# Check formatting
ruff check src/

# Format specific file
ruff format src/keystore/core.py
```

**Configuration:**
- Line length: 99 characters
- Settings in `pyproject.toml` (if present)

### C: Uncrustify

**Version Requirement:**
- **MUST** use uncrustify v0.71 or v0.72
- v0.73+ will not work (incompatible)

**Installation:**

Ubuntu/Debian (21.10+, 22.04 LTS+):
```bash
sudo apt install uncrustify
```

macOS (Homebrew):
```bash
curl -L https://github.com/Homebrew/homebrew-core/raw/2b07d8192623365078a8b855a164ebcdf81494a6/Formula/uncrustify.rb > uncrustify.rb
brew install uncrustify.rb
rm uncrustify.rb
```

**Usage:**
```bash
# Format MicroPython code
cd f469-disco/micropython
./tools/codeformat.py path/to/file.c

# Format all C files
./tools/codeformat.py
```

### Pre-commit Hooks

**Setup:**
```bash
# Install pre-commit
pip install pre-commit

# Install hooks in repo
cd f469-disco/micropython
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

**Usage:**
- Hooks run automatically on `git commit`
- Skip hooks: `git commit -n` (use sparingly)
- Run manually: `pre-commit run --all-files`

---

## Documentation Standards

### Inline Documentation

**Python:**
- Use docstrings for modules, classes, public functions
- Follow PEP 257 conventions
- Keep concise (embedded hardware constraints)

**C:**
- Document non-obvious logic with comments
- Explain hardware interactions
- Document security-critical sections thoroughly

### Markdown Documentation

**Style:**
- Use ATX-style headers (`#`, `##`, not underlines)
- Code blocks: Use fenced blocks with language tags
- Lists: Use `-` for unordered, numbers for ordered
- Links: Use reference-style for repeated URLs

**Structure:**
```markdown
# Document Title

Brief introduction.

## Section

Content.

### Subsection

More content.
```

**Code Examples:**
````markdown
```python
def example():
    return "Hello"
```
````

### README Files

Each major directory should have a `README.md`:
- Purpose of the directory
- Key files/subdirectories
- How to use/build/test
- Links to related documentation

---

## Additional Resources

**Official Style Guides:**
- [PEP 8 - Python Style Guide](https://peps.python.org/pep-0008/)
- [PEP 257 - Docstring Conventions](https://peps.python.org/pep-0257/)
- [MicroPython CODECONVENTIONS.md](../f469-disco/micropython/CODECONVENTIONS.md)

**Tools:**
- [Ruff](https://docs.astral.sh/ruff/)
- [Uncrustify](https://github.com/uncrustify/uncrustify)
- [pre-commit](https://pre-commit.com/)

**Security:**
- [OWASP Embedded Application Security](https://owasp.org/www-project-embedded-application-security/)
- [Bitcoin Core Developer Notes](https://github.com/bitcoin/bitcoin/blob/master/doc/developer-notes.md)

---

## Enforcement

- **Pre-commit hooks:** Recommended for all developers
- **Code review:** All PRs reviewed for standards compliance
- **CI/CD:** Automated checks run on all PRs
- **Exceptions:** Must be documented and justified

---

**Last Updated:** 2025-12-05
**Maintainer:** Specter-DIY Core Team
