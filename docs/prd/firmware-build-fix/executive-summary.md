# Executive Summary

Specter-DIY is a Bitcoin hardware wallet built from off-the-shelf components using an STM32F469 Discovery board. The project upgraded its MicroPython foundation from v1.x to v1.25+, along with LVGL from v8.x to v9.3.0.

**Problem:** The firmware build succeeds, but the resulting binary breaks during the flashing process (fails halfway through) and the board fails to reboot successfully. This indicates a runtime or memory layout issue, not a compilation issue.

**Goal:** Debug and fix the firmware so it successfully flashes to the board and boots properly. Develop debugging techniques and methods for on-board firmware debugging. Start with simple Python test code before moving to the complex application in `src/`.

---
