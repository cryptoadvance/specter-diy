# Battery Meter

Specter DIY supports two battery-metering back-ends that share a single voltage-to-percentage conversion table (`BATTERY_TABLE` in `src/platform.py`).  The active back-end is selected in the platform-specific `boot.py` by injecting the appropriate objects into the `platform` module.

---

## Back-ends

### 1 – STC3100 fuel gauge (original Shield)

The original Specter Shield uses a [STC3100](https://www.st.com/en/power-management/stc3100.html) fuel-gauge IC connected over I²C (address `0x70 / 112`).

`boot.py` sets:
```python
platform.i2c = pyb.I2C(...)   # I2C bus connected to STC3100
```

The firmware reads the raw voltage register (reg 8, 2.44 mV/LSB) and the current register (reg 6; negative value means discharging → not charging).

---

### 2 – ADC voltage divider (Shield-BE and DIY retrofits)

Shield-BE uses a simple resistor divider and the STM32F469 on-chip ADC.  This approach requires no extra IC and is easy to add to any shield that exposes an unused MCU analogue-capable pin.

#### Circuit

```
BATT_P ──┬── R_upper (100 kΩ) ──┬── BAT_MEAS (ADC pin)
         │                      │
       (load)                R_lower (150 kΩ)
                               │
                              GND
```

On Shield-BE:
- **R309** = 100 kΩ upper (BATT_P → BAT_MEAS)
- **R310** = 150 kΩ lower (BAT_MEAS → GND)
- **Q303** (AO3401A P-MOSFET) disconnects the divider from GND when the device is powered off, preventing standby drain
- **BAT_MEAS** is routed to **PA3** (ADC1_IN3, also labelled SC_AUX2 / J203 pin 2 on the interface connector)
- **CHG_STATE** is the TP4056 CHRG open-drain output, pulled high by R313 (100 kΩ); it is LOW while charging

#### Voltage conversion

```
V_BATT = V_ADC × (R_upper + R_lower) / R_lower
       = V_ADC × (100k + 150k) / 150k
       = V_ADC × 5/3
```

With a 3.3 V VDDA and 12-bit ADC (0–4095):

```
V_BATT = raw_reading × 3.3 × 5 / (4095 × 3)
```

The firmware averages 16 samples to reduce noise before applying this formula.

Readings outside 2.5 V – 4.25 V are treated as "no battery connected" (the unloaded ADC pin floats to an out-of-range voltage when nothing is attached).

#### boot.py configuration

```python
import platform, pyb

# ADC pin – must be an analogue-capable GPIO
platform.adc = pyb.ADC(pyb.Pin('A3'))

# Charging-state GPIO (active-low, TP4056 CHRG output)
# Omit or set to None if you have no charger / CHG_STATE signal
platform.chg_pin = pyb.Pin('A8', pyb.Pin.IN, pyb.Pin.PULL_UP)
```

If `chg_pin` is `None` the firmware reports `charging = None` (unknown) instead of `True`/`False`.

---

## Retrofitting onto a Shield Lite

The Shield Lite has no on-board battery management, but its Arduino-compatible header exposes several MCU pins that can be repurposed.  Adding a two-resistor divider and wiring it to an available analogue pin is enough to get battery percentage in the UI.

### Minimum BOM

| Part | Value | Notes |
|------|-------|-------|
| R_upper | 100 kΩ | Between BATT+ and ADC pin |
| R_lower | 150 kΩ | Between ADC pin and GND |

> **Optional:** Add a P-MOSFET (e.g. AO3401A) in series with R_lower to GND, gated by the PWR_HOLD signal, so the divider does not drain the battery when the device is off.  This is only needed if the device will spend long periods powered off with a battery attached.

### Wiring

1. Identify an unused MCU pin on the Shield Lite's Arduino header that is analogue-capable on the STM32F469.  Common free analogue pins: **PA3** (ADC1_IN3), **PC4** (ADC1_IN14), **PB0** (ADC1_IN8).
2. Solder R_upper between the battery positive rail and the chosen ADC pin.
3. Solder R_lower between the ADC pin and GND.
4. If the divider ratio differs from 100k/150k, update `_ADC_DIVIDER_SCALE` in `src/platform.py` to `(R_upper + R_lower) / R_lower`.

### boot.py changes

Edit (or create) the shield-specific `boot.py` and add:

```python
import platform, pyb

# Replace 'A3' with whichever pin you wired the divider to
platform.adc = pyb.ADC(pyb.Pin('A3'))

# If you also wired a charger's CHRG output:
# platform.chg_pin = pyb.Pin('A8', pyb.Pin.IN, pyb.Pin.PULL_UP)
platform.chg_pin = None  # no charger signal available
```

No other firmware changes are needed – the rest of the battery logic lives in `src/platform.py` and is shared across all hardware variants.

---

## Voltage table

The table below maps open-circuit battery voltage to state-of-charge.  It is defined as `BATTERY_TABLE` in `src/platform.py` and used by both back-ends.

| State of charge | Voltage |
|----------------:|--------:|
| 100 % | 4.03 V |
| 90 % | 3.97 V |
| 80 % | 3.93 V |
| 70 % | 3.87 V |
| 60 % | 3.81 V |
| 50 % | 3.76 V |
| 40 % | 3.69 V |
| 30 % | 3.58 V |
| 20 % | 3.48 V |
| 10 % | 3.39 V |
| 0 % | 3.30 V |

Voltages between table entries are linearly interpolated.  Voltages above the highest entry (4.03 V) are clamped to 100 %; voltages below the lowest entry (3.30 V) are treated as 0 %.

> These values were measured under a light discharge current typical of the Specter DIY device.  Open-circuit voltage after a rest period will be slightly higher; under heavy load it will be slightly lower.  The table gives a reasonable approximation for a standard single-cell Li-ion / LiPo battery.

---

## Firmware internals

| Symbol | File | Purpose |
|--------|------|---------|
| `BATTERY_TABLE` | `src/platform.py` | Voltage → % lookup table |
| `_voltage_to_level()` | `src/platform.py` | Linear interpolation helper |
| `get_battery_status()` | `src/platform.py` | Returns `(level_percent, charging)` |
| `get_battery_info()` | `src/platform.py` | Returns full diagnostic tuple for the settings screen |
| `platform.adc` | injected by `boot.py` | `pyb.ADC` object for ADC back-end |
| `platform.chg_pin` | injected by `boot.py` | `pyb.Pin` for charger state, or `None` |
| `platform.i2c` | injected by `boot.py` | `pyb.I2C` object for STC3100 back-end |
