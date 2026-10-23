// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - the parameter list.
//
// Every user setting of the firmware is one line here, in the style of ArduPilot
// parameters: a short NAME, a default (boards may override it, see lx_board.h), a range,
// a unit and a description. The same list generates the C++ enum, the defaults table,
// the console names and docs/firmware/parameters.md (make docs).
//
// LX_PARAM(ID, "NAME", default, min, max, "unit", "description")
//
// Rules: names are at most 10 characters, upper case. Stored settings are matched by a hash
// of the names in this order: adding, removing, renaming or reordering lines resets the stored
// parameters to their defaults (the calibration block survives). If the meaning or unit of a
// parameter changes, rename it, otherwise old stored values would be read with the new meaning.

// --- user interface ---------------------------------------------------------------------
LX_PARAM(UI_STYLE, "UI_STYLE", LX_DEF_UI_STYLE, 0, 2, "",
         "Button layout: 0 = ramp (smooth dimming), 1 = modes (fixed steps), 2 = simple (modes capped at SIMPLE_MAX, no turbo or blinkies)")
LX_PARAM(PREVIEW, "PREVIEW", LX_DEF_PREVIEW, 0, 1, "",
         "1 = the light shows the floor level while the button is pressed from off (instant feedback)")
LX_PARAM(CLICK_MS, "CLICK_MS", 400, 150, 1000, "ms",
         "Longest press that counts as a click, and the longest pause between clicks of one gesture")
LX_PARAM(RAMP_FLOOR, "RAMP_FLOOR", LX_DEF_RAMP_FLOOR, 1, 150, "level",
         "Lowest level of the ramp (moon); also used for momentary moon")
LX_PARAM(RAMP_CEIL, "RAMP_CEIL", LX_DEF_RAMP_CEIL, 1, 150, "level",
         "Highest level reached by holding the button; turbo is above it")
LX_PARAM(RAMP_MS, "RAMP_MS", 16, 2, 100, "ms",
         "Time per level while ramping (150 levels x 16 ms = 2.4 s for the whole ramp)")
LX_PARAM(MODE_CNT, "MODE_CNT", LX_DEF_MODE_CNT, 1, 5, "",
         "Number of fixed modes in the modes and simple layouts")
LX_PARAM(MODE_1, "MODE_1", LX_DEF_MODE_1, 1, 150, "level", "Level of mode 1")
LX_PARAM(MODE_2, "MODE_2", LX_DEF_MODE_2, 1, 150, "level", "Level of mode 2")
LX_PARAM(MODE_3, "MODE_3", LX_DEF_MODE_3, 1, 150, "level", "Level of mode 3")
LX_PARAM(MODE_4, "MODE_4", LX_DEF_MODE_4, 1, 150, "level", "Level of mode 4")
LX_PARAM(MODE_5, "MODE_5", LX_DEF_MODE_5, 1, 150, "level", "Level of mode 5")
LX_PARAM(MODE_MS, "MODE_MS", 600, 200, 2000, "ms",
         "Interval between mode steps while the button is held (modes layout)")
LX_PARAM(MEMORY, "MEMORY", 1, 0, 1, "",
         "Switch-on level: 1 = the last level used, 0 = always MEM_LEVEL (or mode 1)")
LX_PARAM(MEM_LEVEL, "MEM_LEVEL", LX_DEF_MEM_LEVEL, 1, 150, "level",
         "Switch-on level when MEMORY = 0 (ramp layout)")
LX_PARAM(TURBO_LVL, "TURBO_LVL", LX_DEF_TURBO_LVL, 1, 150, "level",
         "Turbo level (double click)")
LX_PARAM(TURBO_S, "TURBO_S", LX_DEF_TURBO_S, 0, 600, "s",
         "Longest turbo burst before the automatic step-down to TURBO_DOWN; 0 = no time limit (the thermal limit always applies)")
LX_PARAM(TURBO_DOWN, "TURBO_DOWN", LX_DEF_TURBO_DOWN, 1, 150, "level",
         "Level after the turbo time has run out")
LX_PARAM(SIMPLE_MAX, "SIMPLE_MAX", 100, 1, 150, "level",
         "Highest level available in the simple layout (for lending the light to others)")
LX_PARAM(SMOOTH_MS, "SMOOTH_MS", 2, 0, 50, "ms",
         "Soft transitions: time per level when the brightness changes; 0 = instant")
LX_PARAM(BLINK_LVL, "BLINK_LVL", LX_DEF_BLINK_LVL, 1, 150, "level",
         "Brightness used for battery and temperature read-outs")
LX_PARAM(BLINKY, "BLINKY", LX_DEF_BLINKY, 0, 7, "bits",
         "Blinky modes after the battery check: 1 = beacon, 2 = SOS, 4 = strobe (add the numbers; 0 = none)")
LX_PARAM(STROBE_HZ, "STROBE_HZ", 10, 1, 20, "Hz",
         "Strobe frequency; flashing between 3 and 30 Hz can trigger photosensitive seizures")
LX_PARAM(LOCK_MOON, "LOCK_MOON", LX_DEF_LOCK_MOON, 0, 1, "",
         "In lockout, holding the button gives momentary moon (0 = lockout stays completely dark)")
LX_PARAM(AUTOLOCK, "AUTOLOCK", 0, 0, 240, "min",
         "Lock automatically after this many minutes off; 0 = never")
LX_PARAM(POCKET_S, "POCKET_S", LX_DEF_POCKET_S, 0, 600, "s",
         "Pocket protection: a button held this long while the main LED is on switches the light off and locks it; 0 = off")
LX_PARAM(AUX_MODE, "AUX_MODE", LX_DEF_AUX_MODE, 0, 2, "",
         "Indicator LED: 0 = off, 1 = events and charging only, 2 = also the battery colour for 2 s after switch-on")

// --- thermal regulation -----------------------------------------------------------------
LX_PARAM(THM_LIMIT, "THM_LIMIT", LX_DEF_THM_LIMIT, 30, 70, "degC",
         "Temperature the regulator holds (sensor reading + THM_OFFSET); set it so that the hottest touchable surface stays within THM-1 (docs/design-rules.md)")
LX_PARAM(THM_OFFSET, "THM_OFFSET", 0, -10, 10, "degC",
         "Calibration: added to the sensor reading so that it reads the true temperature at the sensor (kept by the factory reset)")
LX_PARAM(THM_KP, "THM_KP", LX_DEF_THM_KP, 10, 20, "0.1 lvl/degC",
         "Proportional gain of the thermal regulator")
LX_PARAM(THM_KI, "THM_KI", LX_DEF_THM_KI, 1, 12, "0.1 lvl/degC/s",
         "Integral gain of the thermal regulator (cannot be 0: the regulator always acts)")
LX_PARAM(THM_LEAD, "THM_LEAD", LX_DEF_THM_LEAD, 0, 10, "s",
         "Prediction: the regulator acts on temperature + rate of rise x THM_LEAD, to make up for sensor lag")
LX_PARAM(THM_FLOOR, "THM_FLOOR", LX_DEF_THM_FLOOR, 1, 150, "level",
         "Lowest level the thermal regulator may force (below it only THM_SHUTDN acts)")
LX_PARAM(THM_UP, "THM_UP", 20, 1, 100, "0.1 lvl/s",
         "Fastest brightness recovery while the light cools down")
LX_PARAM(THM_SHUTDN, "THM_SHUTDN", LX_DEF_THM_SHUTDN, 40, 100, "degC",
         "Hard limit: the light switches off and stays off until 5 degC cooler")

// --- battery -----------------------------------------------------------------------------
LX_PARAM(BAT_CELLS, "BAT_CELLS", LX_BAT_CELLS, 1, 4, "",
         "Number of cells in series")
LX_PARAM(BAT_CHEM, "BAT_CHEM", 0, 0, 2, "",
         "Chemistry for the charge estimate: 0 = Li-ion (3.7 V), 1 = LiFePO4 (3.2 V), 2 = NiMH (1.2 V)")
LX_PARAM(LVP_WARN, "LVP_WARN", LX_DEF_LVP_WARN, 900, 3700, "mV/cell",
         "Below this voltage (under load) the light steps down")
LX_PARAM(LVP_CUT, "LVP_CUT", LX_DEF_LVP_CUT, 900, 3500, "mV/cell",
         "Below this voltage the light switches off to protect the cell (never below 2700 mV for Li-ion, 2000 mV for LiFePO4, 900 mV for NiMH, whatever is set)")
LX_PARAM(LVP_RESUME, "LVP_RESUME", 3300, 1000, 3800, "mV/cell",
         "After a low-voltage cut-off the light can be switched on again once the cell rests above this")
LX_PARAM(BAT_RINT, "BAT_RINT", LX_DEF_BAT_RINT, 0, 1000, "mOhm",
         "Resistance of cell, springs and wiring, for the load compensation of the charge estimate")
LX_PARAM(BAT_CAL, "BAT_CAL", 0, -300, 300, "mV",
         "Calibration: added to the measured pack voltage (kept by the factory reset)")
LX_PARAM(BAT_MAX_MA, "BAT_MAX_MA", LX_DEF_BAT_MAX_MA, 0, 30000, "mA",
         "Cell current limit, 0 = off (needs the board's LED current model, LX_MAIN_MAX_MA)")

// --- charging ----------------------------------------------------------------------------
LX_PARAM(CHG_TMIN, "CHG_TMIN", 0, 0, 20, "degC",
         "Charging is paused below this temperature (Li-ion must not be charged below 0 degC)")
LX_PARAM(CHG_TMAX, "CHG_TMAX", 45, 30, 50, "degC",
         "Charging is paused above this temperature")
LX_PARAM(CHG_MAXLVL, "CHG_MAXLVL", LX_DEF_CHG_MAXLVL, 1, 150, "level",
         "Highest level while USB power is connected")

// --- laser (boards with LX_HAS_LASER) -----------------------------------------------------
LX_PARAM(LASER_EN, "LASER_EN", LX_HAS_LASER, 0, 1, "",
         "Allow the laser gesture (click, then click-and-hold from off)")
LX_PARAM(LASER_S, "LASER_S", 60, 1, 300, "s",
         "Longest laser emission per press")
LX_PARAM(LASER_TMAX, "LASER_TMAX", 60, 30, 80, "degC",
         "No laser above this temperature")
LX_PARAM(LASER_VMIN, "LASER_VMIN", 3200, 900, 3800, "mV/cell",
         "No laser below this cell voltage (cheap laser modules drift when the supply sags)")

// --- side lights (boards with LX_HAS_SIDE) --------------------------------------------------
LX_PARAM(SIDE_RED, "SIDE_RED", LX_DEF_SIDE_RED, 1, 100, "%",
         "Brightness of the red side light (5 clicks from off)")
LX_PARAM(SIDE_UV, "SIDE_UV", LX_DEF_SIDE_UV, 0, 100, "%",
         "Brightness of the UV side light; 0 = no UV (two clicks in the side light then do nothing)")
