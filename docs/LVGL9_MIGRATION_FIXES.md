# LVGL 9.x Migration Fixes

This document lists all API changes made to migrate from LVGL 8.x to LVGL 9.x.

## Event Callback API

### Callback Signature
**LVGL 8:** `def callback(obj, event_code)`
**LVGL 9:** `def callback(event)` with `event.get_code()` and `event.get_target()`

```python
# Before (LVGL 8)
def on_click(self, obj, event):
    if event == lv.EVENT.RELEASED:
        ...

# After (LVGL 9)
def on_click(self, event):
    if event.get_code() == lv.EVENT.RELEASED:
        ...
```

**Files:** `qrcode.py`, `input.py`, `mnemonic.py`
**Ref:** https://docs.lvgl.io/9.0/overview/event.html

### Event Registration
**LVGL 8:** `obj.set_event_cb(callback)`
**LVGL 9:** `obj.add_event_cb(callback, event_filter, user_data)`

```python
# Before
btn.set_event_cb(self.on_click)

# After
btn.add_event_cb(self.on_click, lv.EVENT.ALL, None)
```

**Files:** `qrcode.py`, `settings.py`, `input.py`
**Ref:** https://docs.lvgl.io/9.0/overview/event.html#add-events-to-a-widget

---

## Widget Renames

### Button
**LVGL 8:** `lv.btn(parent)`
**LVGL 9:** `lv.button(parent)`

**Files:** `qrcode.py`, `wallets/screens.py`
**Ref:** https://docs.lvgl.io/9.0/details/widgets/button.html

### Buttonmatrix Text Access
**LVGL 8:** `btnm.get_selected_button_text()`
**LVGL 9:** Two-step: `btn_id = btnm.get_selected_button()` then `btnm.get_button_text(btn_id)`

```python
# Before
text = self.btnm.get_selected_button_text()

# After
btn_id = self.btnm.get_selected_button()
text = self.btnm.get_button_text(btn_id)
```

**Files:** `keyboard.py`, `input.py`, `mnemonic.py`
**Ref:** https://docs.lvgl.io/9.0/details/widgets/buttonmatrix.html

---

## Page Widget Removed

**LVGL 8:** `lv.page(parent)` - dedicated scrollable container
**LVGL 9:** Use `lv.obj(parent)` with scrolling enabled (default)

```python
# Before
self.page = lv.page(self)

# After
self.page = lv.obj(self)  # Scrolling enabled by default
```

**Files:** `transaction.py`, `prompt.py`
**Ref:** https://docs.lvgl.io/9.0/details/widgets/obj.html#scrolling

---

## Style API

### Style Copy Removed
**LVGL 8:** `lv.style_copy(new_style, old_style)`
**LVGL 9:** Create new style with `init()` and set properties individually

```python
# Before
new_style = lv.style_t()
lv.style_copy(new_style, old_style)

# After
new_style = lv.style_t()
new_style.init()
new_style.set_bg_color(...)
new_style.set_text_font(...)
```

**Files:** `modal.py`, `mnemonic.py`, `transaction.py`, `settings.py`
**Ref:** https://docs.lvgl.io/9.0/overview/style.html

### Style Application
**LVGL 8:** `obj.set_style(0, style)` or `obj.add_style(part, style)`
**LVGL 9:** `obj.add_style(style, selector)` where selector = part | state

```python
# Before
obj.set_style(0, style)

# After
obj.add_style(style, lv.PART.MAIN)
```

**Files:** `transaction.py`, `mnemonic.py`
**Ref:** https://docs.lvgl.io/9.0/overview/style.html#add-styles-to-widgets

---

## Flag API

### Namespace Change
**LVGL 8:** `lv.OBJ_FLAG.HIDDEN`
**LVGL 9:** `lv.obj.FLAG.HIDDEN`

**Files:** `mnemonic.py`, `qrcode.py`

### Method Rename
**LVGL 8:** `obj.clear_flag(flag)`
**LVGL 9:** `obj.remove_flag(flag)`

```python
# Before
obj.clear_flag(lv.OBJ_FLAG.HIDDEN)

# After
obj.remove_flag(lv.obj.FLAG.HIDDEN)
```

**Files:** `keyboard.py`, `mnemonic.py`
**Ref:** https://docs.lvgl.io/9.0/overview/obj.html#flags

### Hidden Property
**LVGL 8:** `obj.set_hidden(True/False)`
**LVGL 9:** `obj.add_flag(lv.obj.FLAG.HIDDEN)` / `obj.remove_flag(lv.obj.FLAG.HIDDEN)`

```python
# Before
obj.set_hidden(True)
obj.set_hidden(False)

# After
obj.add_flag(lv.obj.FLAG.HIDDEN)
obj.remove_flag(lv.obj.FLAG.HIDDEN)
```

**Files:** `qrcode.py`

---

## Alignment API

### Relative Alignment
**LVGL 8:** `obj.align(other_obj, align_type, x, y)`
**LVGL 9:** `obj.align_to(other_obj, align_type, x, y)`

```python
# Before
btn.align(label, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)

# After
btn.align_to(label, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
```

**Files:** `qrcode.py`, `wallets/screens.py`, `xpubs/screens.py`, `bip85.py`, `backup.py`
**Ref:** https://docs.lvgl.io/9.0/overview/coord.html#align

### Alignment Constants
**LVGL 8:** `lv.ALIGN.IN_BOTTOM_MID`, `lv.ALIGN.IN_TOP_MID`, etc.
**LVGL 9:** `lv.ALIGN.BOTTOM_MID`, `lv.ALIGN.TOP_MID` (removed `IN_` prefix)

**Files:** `qrcode.py`

---

## Label API

### Long Mode
**LVGL 8:** `lv.label.LONG.BREAK`
**LVGL 9:** `lv.label.LONG_MODE.WRAP`

```python
# Before
lbl.set_long_mode(lv.label.LONG.BREAK)

# After
lbl.set_long_mode(lv.label.LONG_MODE.WRAP)
```

**Files:** `transaction.py`
**Ref:** https://docs.lvgl.io/9.0/details/widgets/label.html#long-modes

### Text Alignment
**LVGL 8:** `lbl.set_align(lv.label.ALIGN.LEFT)`
**LVGL 9:** `lbl.set_style_text_align(lv.TEXT_ALIGN.LEFT, 0)`

**Files:** `transaction.py`

---

## Button State API

**LVGL 8:** `lv.btn.STATE.INA`, `lv.btn.STATE.REL`
**LVGL 9:** `lv.STATE.DISABLED`, use `add_state()`/`remove_state()`

```python
# Before
btn.set_state(lv.btn.STATE.INA)

# After
btn.add_state(lv.STATE.DISABLED)
```

**Files:** `wallets/screens.py`
**Ref:** https://docs.lvgl.io/9.0/overview/obj.html#states

---

## Object Deletion

**LVGL 8:** `obj.del_async()`
**LVGL 9:** `obj.delete()`

**Files:** `mnemonic.py`
**Ref:** https://docs.lvgl.io/9.0/overview/obj.html#delete-objects

---

## Font Names

**LVGL 8:** `lv.font_roboto_22`, `lv.font_roboto_28`
**LVGL 9:** `lv.font_montserrat_22`, `lv.font_montserrat_28` (roboto not included in build)

**Files:** `mnemonic.py`, `qrcode.py`, `transaction.py`
**Note:** Font availability depends on build configuration

---

## Table API

**LVGL 8:** `table.set_col_cnt()`, `table.set_row_cnt()`
**LVGL 9:** `table.set_column_count()`, `table.set_row_count()`

**Files:** `mnemonic.py`
**Ref:** https://docs.lvgl.io/9.0/details/widgets/table.html

---

## References

- [LVGL 9.0 Migration Guide](https://docs.lvgl.io/9.0/overview/migration.html)
- [LVGL 9.0 API Documentation](https://docs.lvgl.io/9.0/)
- [LVGL GitHub Releases](https://github.com/lvgl/lvgl/releases)
