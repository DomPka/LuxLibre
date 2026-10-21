# Aurora++ v0.5 web pages: control app and firmware installer

Two small web pages belong to the flashlight. Both run entirely inside the browser: no server, no
account, nothing is uploaded, no CDN, no web fonts. Each page is **one file** and also works offline.

| File (folder `app/`) | What it is | Works in |
|---|---|---|
| `index.html` | Start page with two big links. | Every browser. |
| `aurora-app.html` | **Control app.** Switch the light, choose the brightness and the profile, see the battery, ... over Bluetooth. Has a Demo mode that needs no flashlight. | Chrome or Edge on Android, Windows, macOS, Linux, ChromeOS. On iPhone and iPad the free **Bluefy** browser. Not Firefox, not Safari. |
| `aurora-flasher.html` | **Firmware installer.** Puts the firmware on the flashlight through the USB-C port (Web Serial). The firmware image is inside the file. | Chrome or Edge **on a computer** (Windows, macOS, Linux, ChromeOS). Not on phones or tablets, not Firefox, not Safari. |

Contents

1. [The control app](#1-the-control-app)
2. [The firmware installer](#2-the-firmware-installer)
3. [Rebuilding the installer with new firmware](#3-rebuilding-the-installer-with-new-firmware)
4. [Free hosting on GitHub Pages, step by step](#4-free-hosting-on-github-pages-step-by-step)
5. [Why https, and opening the files directly](#5-why-https-and-opening-the-files-directly)
6. [Where the protocol document leaves room](#6-where-the-protocol-document-leaves-room)
7. [Tests and screenshots](#7-tests-and-screenshots)
8. [What could not be tested](#8-what-could-not-be-tested)
9. [Files](#9-files)

---

## 1. The control app

`app/aurora-app.html` speaks the Bluetooth protocol of [`ble_protocol.md`](ble_protocol.md) (version 1)
through Web Bluetooth: `requestDevice` with the name prefix `Aurora` and the Aurora Control Service
and Battery Service, notifications of Status and Battery Level, one GATT operation at a time.

### What it shows

* Battery percentage (large), voltage, charging / fully charged / USB power, board temperature,
  LED current, estimated runtime, turbo countdown, lockout.
* Badges "Too warm" (thermal limit) and "Battery protection" (low voltage or cell current limit).
* Who changed the light last (button, app, automatic).
* The banner **"App locked for N s - the button has priority"** while the flashlight ignores the app
  (Status byte 14); the controls are paused until it reaches 0.

### What it does

* Big On / Off button. Level buttons Moon, Low, Medium, High, Turbo (Turbo also from Off, in one tap,
  with an orange countdown bar and the automatic step-down).
* "Fine brightness" slider: exact current (`OUTPUT_MA`), logarithmic scale, at most about 5 writes per second.
* Profile cards Extreme, Balanced, Endurance, Custom with one-line explanations and the numbers of the profile
  in use. "Save to flashlight" stores the selected profile and level (`SAVE`).
* **Custom profile editor**: every field of the Profile characteristic with the ranges of the protocol
  document, plain-language messages for out-of-range values, "Apply (try it)" and "Save to flashlight". After
  every write the profile is read back; if the flashlight adjusted a value the app says so and shows what is really
  used.
* Lockout switch, "Find my flashlight" (`IDENTIFY`), "Keep Bluetooth on" (`KEEPALIVE`, see section 6).
* The ATT error codes 0x80 button priority, 0x81 invalid, 0x82 protection, 0x83 lockout become plain sentences.
  Browsers rarely pass the code on as a number, so the app reads it from the error text defensively and otherwise
  infers the reason from the last Status packet (and says "probably" when it is a guess).
* Connection lost: a banner, automatic reconnect attempts, a Reconnect button. Bluetooth switched off or a chooser
  that was cancelled are explained.
* No Web Bluetooth (wrong browser, or the page was not opened from https): a clear explanation (Chrome or Edge on
  Android, Windows, macOS, Linux, ChromeOS; iPhone and iPad need the free **Bluefy** browser; Firefox and Safari do
  not support Web Bluetooth) and a working Demo button.
* Mobile first: works from 320 px width, light and dark theme (`prefers-color-scheme`), touch targets of at least 44 px, no
  horizontal scrolling.

`FACTORY_RESET` (0x7F) exists in the protocol module and is tested, but the app has no button for it on purpose.

The flashlight listens for Bluetooth only in "windows" (protocol document section 1). If it is not in the list:
switch the light on, or click the button three times quickly while it is off (the small colour LED blinks blue),
or plug in USB. The start screen of the app says so.

### Demo mode

"Try demo mode" on the start screen runs a flashlight written in JavaScript inside the page. It is not a
mock of the screen: it receives the same 1 to 3 byte commands and 20-byte profile writes, and answers with the same
18-byte Status packets, produced by the same encoder and decoder that the real Bluetooth link uses. It returns the
same ATT error codes. A "Demo tools" card acts like things a person does to a real flashlight: press the flashlight
button (starts the 3 s app lock), lose the Bluetooth connection, plug in USB, a hot day (45 degC air), battery charge slider,
and a drain speed of real time, 20 x or 120 x.

The model is small and simplified. It follows protocol document section 6, the rest is plausible, not measured:

| Part | Model |
|---|---|
| Battery | 800 mAh (two LP601646 cells), open-circuit voltage 3.00 V (0 %), 3.30 (3 %), 3.55 (10 %), 3.66 (20 %), 3.76 (40 %), 3.87 (60 %), 4.00 (80 %), 4.19 V (100 %); internal resistance 0.15 ohm — the same capacity the firmware's runtime estimate uses (`docs/firmware.md`). |
| LED | forward voltage 2.75 V + 0.15 V/A, step-down converter efficiency 0.9, so the battery current is V_LED x I / (0.9 x V_BAT) (document section 6); 8 mA for the electronics (none from the battery while USB is plugged in). |
| Heat | 75 % of the LED's electrical power becomes heat; 7.5 K/W to the air, time constant 70 s; air 24 degC (45 degC on a "hot day"). |
| Protection | Temperature: linear reduction from the profile limit, 15 degC above it the level is Low, above 70 degC Moon, above 80 degC off. Low voltage: one level down every 5 s below the profile's step-down voltage, Moon below 3.10 V, off below 3.00 V (switch-on refused until the cell is above 3.30 V or USB is present). Cell current limit of the profile. Turbo refused within 5 degC of the temperature limit. |
| Turbo | Runs for the profile's turbo time, then steps down; never remembered for the next switch-on. |
| Charging | Only with USB, between 0 and 45 degC and while the LED draws 500 mA or less; 280 mA, tapering above 80 % (the value the firmware assumes; the charger's nominal current is about 300 mA, `docs/firmware.md`). |
| Button priority | 3 s app lock after every button press. |
| Runtime estimate | (remaining charge minus a 5 % reserve) / battery current. |
| Status packets | On every change and at least every 2 s. |

---

## 2. The firmware installer

`app/aurora-flasher.html` installs the firmware through the USB-C port with
[esptool-js](https://github.com/espressif/esptool-js) 0.7.0 over Web Serial. The page, esptool-js, the helper program
for the ESP32-C3 and the firmware image are **all inside the one file**: no download happens while installing.

### What a person does

1. **Plug in** the flashlight with a USB-C **data** cable, directly into the computer.
2. **Connect**: click the button and choose the port named **"USB JTAG/serial debug unit"** (Windows: "USB Serial
   Device (COMx)") in the browser's list.
3. **Install firmware**: a progress bar shows preparing, writing, checking, restarting.
4. **Done**: unplug the cable and plug it in again; press the flashlight's button once if the light does not come
   on.

A box "Something not working?" covers: no port in the list (different cable, charge-only cables have no data
wires; different USB port; "Show all serial ports"), a port that is listed but fails to connect (unplug, **hold the
button**, plug in, let go: this forces the chip's built-in download mode; Connect again), errors while installing, a
busy port, and a dark light after installing. The page says up front that phones and tablets cannot install firmware
and that Chrome or Edge on a computer is needed.

### What happens behind the buttons

* **Connect** opens the port at 115200 baud (the USB link is virtual, the speed does not matter) and resets the chip
  into its ROM download mode with the USB-Serial/JTAG reset sequence, so a running flashlight needs no button. It reads
  the chip type and refuses anything that is not an **ESP32-C3** before anything is written, loads esptool-js's small
  helper program into RAM and reads the flash size. If any step fails the port is closed again.
* **Install firmware** writes the image at address **0x0** (compressed), lets the chip compute the MD5 of what it
  wrote and compares it with the image (**"Installed and checked"**), then restarts the chip with the RTS line. The
  flashlight's USB port disappears and comes back while it restarts; the page expects that.
* Every installation resets the flashlight's saved settings (custom profile, remembered level) to the factory
  defaults, because the image covers the settings region at 0x9000 (it is 0xFF in the image, `docs/firmware.md`
  section 2.10 and 4). To keep the settings, flash only the app, for example
  `espflash flash --partition-table firmware/partitions.csv firmware/dist/aurora-fw-v0.5.0.elf`. The page says this in
  step 3.
* The unchecked box **"Factory reset (clear the whole flash first)"** additionally erases the whole flash chip before
  writing, which is only useful if the flashlight misbehaves after an update.

### Safety

* Only an ESP32-C3 is accepted; the image must fit the flash chip.
* The page checks the image: a merged image for address 0x0 has the ESP image marker, the ESP32-C3 chip id, the
  partition table at 0x8000 and the app at 0x10000. The SHA-256 of the firmware inside the page is recomputed when the
  page loads and compared with the value stored at build time; one changed byte shows "The firmware inside this page is
  damaged" and disables Install.
* The firmware card in step 3 shows name, version, size and SHA-256 of what will be written.
* A failed installation cannot break the flashlight for good: the chip's download mode lives in ROM and is reachable
  by holding the button while plugging in USB.
* While installing: the browser asks before the tab is closed, the screen is kept awake where the browser allows it,
  the tab title says "Installing... keep this tab open", and the page asks to keep the tab in front (hidden tabs run
  timers slowly, which can make the transfer time out).
* If the cable is pulled out the page explains it at once instead of waiting for a time-out.
* Errors are explained in plain words with next steps; "Technical details" and the collapsed "Technical log" show the
  esptool-js output for support ("Copy log").
* **Advanced: use a different .bin file** (collapsed). Wrong chip, too small, or not a merged image are explained; an
  image that does not look merged needs an extra tick ("I understand and want to install this file anyway").

Without Web Serial (Firefox, Safari, iPhone, iPad, Android, an insecure address) the page explains why and disables
Connect. It decides by looking for Web Serial, not by guessing the device, so any browser that offers it can connect.

---

## 3. Rebuilding the installer with new firmware

`app/aurora-flasher.html` is **generated**. It contains a copy of the firmware, so it must be rebuilt every time
`firmware/build.sh` produces a new `firmware/dist/aurora-fw-v0.5.0-merged.bin`.

```
cd tools/web
npm install                 # once; needs Node.js 18 or newer and the npm registry (esptool-js, esbuild, test tools)
node build_flasher.mjs      # the same as: npm run build
```

The script prints what it embedded, for example

```
Wrote .../app/aurora-flasher.html
  page: 764 KB  (script 195 KB, esptool-js 0.7.0, minified)
  firmware: aurora-fw-v0.5.0-merged.bin  v0.5.0  409 KB (419136 bytes)
  SHA-256:  9016ac6c571668eae8ea3d9b806105bbb181f77e74668609c33c3c897ab7d0c6
```

Compare the SHA-256 with `sha256sum firmware/dist/aurora-fw-v0.5.0-merged.bin`; the page shows the same value in step 3.
The output depends only on its inputs (no time stamps): building twice gives byte-identical pages. After a rebuild,
upload the new `aurora-flasher.html` again (section 4).

| Option | Meaning |
|---|---|
| `--bin <file>` | Firmware image to embed. Default `firmware/dist/aurora-fw-v0.5.0-merged.bin`. Pass it when the version changes. |
| `--out <file>` | Page to write. Default `app/aurora-flasher.html`. |
| `--version <x.y.z>` | Version shown on the page. Default: from the file name (`aurora-fw-vX.Y.Z-merged.bin`), else `package.json`. |
| `--require-firmware` | Fail instead of building the placeholder when the image is missing (`npm run build:release`). |
| `--placeholder` | Build the placeholder page even if the image exists (`npm run build:placeholder`). |
| `--allow-unmerged` | Embed an image that does not look like a merged bootloader + partition table + app image. |
| `--no-minify` | Readable JavaScript in the page, for debugging. |
| `--help` | List the options. |

**No firmware yet?** If the image does not exist the script still builds the page, but says so loudly (a box of
asterisks "PLACEHOLDER BUILD - NO FIRMWARE IS EMBEDDED IN THIS PAGE" on the console) and the page shows a yellow banner,
keeps its Install button disabled and still lets a person pick a `.bin` under Advanced. Nothing is embedded and no
hash is shown. Run the command again once the firmware exists.

The build refuses an image that would not work at address 0x0: too small, not an ESP image, made for another chip, or
not a complete merged image (unless `--allow-unmerged`). It bundles only the ESP32-C3 helper program of esptool-js, not
the other 13 chips, and keeps esptool-js's error class names (the page decides on them).

---

## 4. Free hosting on GitHub Pages, step by step

GitHub Pages serves a folder of files as a web site at an `https://` address, for free. You need the three files from
the `app/` folder: `index.html`, `aurora-app.html`, `aurora-flasher.html`. (The `screenshots` folder is only for the
user guide; do not upload it.) GitHub's screens change now and then; if a button has another name, look for the
closest one.

**What to know first.** On the free plan the repository must be **public**, so everybody can see its files, including the
firmware that is inside `aurora-flasher.html`. The pages contain no secrets and no accounts. The flashlight itself has no
pairing: whoever is near it while its Bluetooth window is open can use the app.

1. **Create a GitHub account.** Go to `github.com`, click **Sign up**, enter an e-mail address, a password and a
   user name (the name becomes part of the web address, for example `maria-k`), solve the puzzle, enter the code that is
   mailed to you. Choose the free plan. An unconfirmed e-mail address stops Pages from working, so confirm it.
2. **Create a repository.** Click the **+** at the top right, then **New repository**. Repository name: for example
   `aurora-flashlight` (letters, digits and hyphens, no spaces). Choose **Public**. Tick **Add a README file**. Click
   **Create repository**.
3. **Upload the pages.** In the new repository click **Add file**, then **Upload files**. Drag the three files
   (`index.html`, `aurora-app.html`, `aurora-flasher.html`) from the `app` folder into the window (or click "choose
   your files"). They must end up at the top level of the repository, not in a sub-folder. Wait until all three are
   listed, scroll down and click **Commit changes**.
4. **Switch Pages on.** Click the **Settings** tab of the repository, then **Pages** in the list on the left. Under
   "Build and deployment" set **Source** to **Deploy from a branch**. Under **Branch** choose **main** and the folder
   **/ (root)**, then click **Save**.
5. **Wait one or two minutes**, then reload the Pages settings page. A box says
   **"Your site is live at https://USER.github.io/REPOSITORY/"**. (The **Actions** tab shows the progress: a yellow dot
   while it works, a green check when done.)
6. **Open it.** With the example names:
   * start page: `https://maria-k.github.io/aurora-flashlight/`
   * control app: `https://maria-k.github.io/aurora-flashlight/aurora-app.html`
   * firmware installer: `https://maria-k.github.io/aurora-flashlight/aurora-flasher.html`

   The user name in the address is written in lower case. Send these addresses to anyone who needs them. On an
   Android phone open the app address in Chrome (menu, "Add to Home screen" gives an icon); on an iPhone open it in
   **Bluefy**.
7. **Update a page later**, for example after rebuilding the installer: open the repository, **Add file**, **Upload
   files**, drag the new file with the same name, **Commit changes**. The site updates after a minute or two. If the old
   version still shows, reload with Ctrl+Shift+R (Cmd+Shift+R on a Mac).
8. **Take it down**: Settings, Pages, switch the source off, or delete the repository (Settings, Danger zone).

Any other static web host that serves https works the same way: upload the same three files.

---

## 5. Why https, and opening the files directly

Web Bluetooth and Web Serial let a web page talk to hardware. Browsers allow that only in a **secure context**: a page
served over **https://**, from **http://localhost** on the same computer, or opened as a **local file** in Chrome or
Edge. On a plain `http://` address the browser removes `navigator.bluetooth` and `navigator.serial`, so the pages would
only say that the browser cannot do it. GitHub Pages serves everything over https automatically (Settings, Pages,
"Enforce HTTPS" should be ticked; it is the default).

**Opening the file directly works too**, on a computer in Chrome or Edge: download the file, then double-click it or drag
it into a browser window; the address bar shows `file:///...`. Chrome counts such a page as secure, so Connect works
for the control app (the Demo button works in any browser). The installer should behave the same way; that was only
tested with a pretend serial port in headless Chromium (section 8). Phones make opening downloaded files awkward: use the
GitHub address there, with Chrome on Android or Bluefy on iPhone. Opening a file does not work in Firefox or Safari
because they have neither API.

---

## 6. Where the protocol document leaves room

`ble_protocol.md` is implemented exactly. These are the places where it was ambiguous or silent, and what the app does.
`docs/firmware.md` section 3 lists how the firmware decided the same points; there is no conflict.

| Topic | Document | App |
|---|---|---|
| `KEEPALIVE` argument | "u8 seconds" but "max 600 s" (a byte holds 255). | Sends the literal one-byte form with 255 s first (about 4 minutes, which the firmware accepts). Only if the flashlight refuses that as invalid does it try a 3-byte form with a u16 of 600 s. |
| `LEVEL` and `OUTPUT_MA` while the light is off | Silent whether they switch the light on. | The level buttons send `LEVEL`, then `ON`, then read Status and repeat `LEVEL` if the light came up at another level (switch-on uses the remembered level). The slider sends `OUTPUT_MA` and shows what Status reports. The firmware switches on for all three. |
| Turbo as remembered level | Silent. | Turbo is never the level used at the next switch-on (the firmware does the same). |
| Built-in profiles | No flag bits; Endurance turbo "none". | Extreme and Balanced: turbo allowed, remember level, battery on RGB. Endurance: no turbo flag, turbo = High, 0 s, step-down = High. Custom starts as Balanced. Same values as `firmware/aurora-core/src/profile.rs`. |
| When "turbo" exists | "turbo time 0 = turbo = High". | Turbo exists when the flag is set, the time is above 0 and the turbo current is above High. |
| ATT error codes | "returned to the write". | Browsers differ in how they report an ATT application error, and often not as a number. The app looks for 0x80 to 0x83 in numeric error properties and in the error text (hex, or decimal after a word like "error"), and otherwise infers the reason from the last Status (lockout, app lock, temperature, battery); inferred reasons are worded as guesses. |
| Status interval | "at least every 2 s". | The app does not rely on it: countdowns are computed locally between packets, and Status is read when none arrived for 6 s. (The firmware sends on change and every 2 s.) |
| Battery level | Read and notify. | Used when present; Status byte 8 is the fallback if the Battery Service is missing (tested). |

The cells are two LP601646 in parallel, about 800 mAh (v0.4 had one 102050 pouch of about 1000 mAh); the app only
shows what the firmware reports.

---

## 7. Tests and screenshots

```
cd tools/web
npm install
npm run typecheck           # TypeScript checks the installer's JavaScript (JSDoc types), no output = clean
npm test                    # Node unit tests, about 30 s
npm run test:browser        # headless Chromium: both pages, writes the screenshots
```

The browser tests need a Chromium that Playwright can find. Where one is preinstalled set
`PLAYWRIGHT_BROWSERS_PATH` (e.g. `/opt/pw-browsers`); otherwise run `npx playwright install chromium` once.
`npm install` itself downloads no browser. Run only one page with `node browser/run-app-tests.mjs` or
`node browser/run-flasher-tests.mjs`; add `--no-shots` to skip the screenshots. `npm run test:all` runs everything.

**Node unit tests** (`test/`, `node --test`):

* `protocol.test.mjs`: encoder and decoder of the app's protocol module against byte vectors worked out by hand from
  the document, both directions: Status (18 bytes), every command, the 20-byte profile with clamping, built-in profiles,
  the ATT error mapping, KEEPALIVE forms.
* `sim.test.mjs`: the demo flashlight (commands, errors, button priority, turbo, protection, charging).
* `flasher-backend.test.mjs`: the real esptool-js 0.7.0 running against a pretend ESP32-C3 (reset sequence, ROM
  protocol, helper program upload, compressed write, MD5 check, erase, restart), including no answer, wrong chip,
  failed verification, a pulled cable and a busy port.
* `friendly.test.mjs`, `image.test.mjs`, `md5.test.mjs`: error explanations, image checks, the MD5 used for
  verification.
* `build.test.mjs`: the build script (embedding, hash, version, placeholder, refusals, reproducible output, one
  self-contained file, only the ESP32-C3 helper program).

**Browser tests** (`browser/`, Playwright with headless Chromium):

* `run-app-tests.mjs`: loads the app without console errors; the explanation without Web Bluetooth (generic, iPhone,
  Firefox, desktop Safari); a complete click-through of the demo (on/off, levels from off, turbo with countdown and step-down,
  slider throttling, profiles, Custom editor with validation, Apply and Save, lockout, identify, keep-alive, button
  priority, USB, hot day, low battery, lost connection and reconnect, exit); the same page against a pretend
  `navigator.bluetooth` that follows the document (bytes on the wire, one operation at a time, notifications, ATT
  errors, automatic reconnect, adapter off, cancelled chooser); no horizontal scroll at 320, 360, 390 and 1280 px.
* `run-flasher-tests.mjs`: builds the page (real firmware, placeholder, synthetic and tampered variants) and runs it
  against a pretend ESP32-C3 behind a pretend `navigator.serial`: placeholder, firmware card, the happy path with phases
  and flash content check, factory reset, log and copy, closing the tab while installing, cancelled chooser, a
  flashlight that does not answer (hold the button, then Try again), wrong chip, busy port, failed verification, a
  cable pulled mid-install and replugged, unplugged while connected, the Advanced panel, unsupported browsers,
  a damaged page, layouts, the start page, links between the pages, and that the real page installs the real
  firmware byte for byte.

**Screenshots** (`app/screenshots/`, 390x844 phone at 2x for the app, 1x for the installer, and 1280x800 desktop;
`dark` in the name means the dark theme):

| File | Shows |
|---|---|
| `index-390.png`, `index-1280.png` | Start page |
| `app-start-*.png`, `app-dark-start-*.png` | Start screen of the control app (Connect, Demo) |
| `app-unsupported-*.png` | Explanation shown by a browser without Web Bluetooth |
| `app-demo-off-*.png`, `app-demo-on-*.png`, `app-demo-on-390-full.png` | Demo flashlight off, on at High (also dark variants, and the whole page on a phone) |
| `app-light-controls-390.png`, `app-profiles-390.png`, `app-settings-390.png` | Light card, profile cards, Settings card (phone, also dark) |
| `app-turbo-*.png` | Turbo running with the countdown bar |
| `app-locked-*.png` | "App locked for N s - the button has priority" |
| `app-editor-*.png`, `app-editor-buttons-390.png`, `app-editor-error-*.png` | Custom profile editor, its buttons, a validation message |
| `app-lost-*.png` | Connection lost, Reconnect |
| `flasher-start-*.png`, `flasher-start-390-full.png` | Installer, steps 1 to 4 and the troubleshooting box |
| `flasher-connected-*.png` | Flashlight found, firmware card, factory-reset box, Install button |
| `flasher-installing-*.png`, `flasher-done-*.png` | Progress bar, finished installation |
| `flasher-error-*.png` | Flashlight does not answer: the download-mode steps |
| `flasher-unsupported-*.png` | Installer in a browser without Web Serial (Firefox) |
| `flasher-placeholder-*.png` | Placeholder build without firmware |
| `flasher-advanced-*.png` | "Use a different .bin file" with a file that needs a tick |
| `flasher-dark-start-*.png`, `flasher-dark-installing-*.png`, `flasher-dark-done-*.png` | Dark theme |

---

## 8. What could not be tested

No flashlight, serial port or Bluetooth adapter was available. Everything below is therefore untested and needs one
real run before the pages are given to people:

* **Real Bluetooth.** The app was tested against a pretend `navigator.bluetooth` written from the protocol document and
  against the demo flashlight. Not tested: a real Aurora++ (the firmware's own host tests cover its side), the error
  text real browsers produce for an ATT error (Chrome on Android, Chrome on Windows and macOS, Edge, Bluefy differ and the
  app's inference is the fallback), Bluefy on a real iPhone, Web Bluetooth on Linux (Chrome may still keep it behind
  `chrome://flags/#enable-web-bluetooth`), and long sessions (battery drain, reconnect after a day).
* **Real serial hardware.** The installer was tested with the real esptool-js and the real page, against a pretend
  ESP32-C3 that implements the USB-Serial/JTAG reset behaviour (DTR/RTS), the ROM and helper-program protocol, flash
  write with MD5, erase and a pulled cable. Not tested: how a real ESP32-C3 re-enumerates over USB after the reset
  (timing, whether Chrome offers the same port again), the real port names in Chrome's chooser on Windows, macOS and
  Linux (this page names them from documentation), Linux permissions for `/dev/ttyACM0` (the page explains the
  `dialout` group), real flash timing, throttling of a tab in the background, and Web Serial from a `file://` page
  (headless Chromium only shows that `navigator.serial` exists there).
* **GitHub.** GitHub cannot be reached from the build environment. Section 4 was written from knowledge of GitHub's
  web interface and was not followed live.
* **Demo mode** is a model (section 1), not the firmware.

---

## 9. Files

```
app/
  index.html                start page
  aurora-app.html           control app (hand-written, single file; protocol and demo flashlight are inline <script> blocks)
  aurora-flasher.html       firmware installer (GENERATED by tools/web/build_flasher.mjs, contains the firmware)
  screenshots/              pictures made by the browser tests (not part of the web site)
tools/web/
  build_flasher.mjs         builds app/aurora-flasher.html (section 3)
  flasher/                  sources of the installer
    flasher.template.html     page, CSS and the two placeholders the build fills in
    main.js                   the page's logic (steps, progress, errors)
    backend.js                connect and install with esptool-js (the part that talks to the chip)
    friendly.js               error text for people
    image.js, md5.js          image checks, MD5 and SHA-256 helpers
    stubs.js                  replaces esptool-js's list of helper programs by the ESP32-C3's
  test/                     Node unit tests and helpers (a pretend ESP32-C3, synthetic images)
  browser/                  Playwright test runners, pretend navigator.bluetooth / navigator.serial
  package.json, package-lock.json, tsconfig.json
  .test-output/, node_modules/   generated, ignored by git
```

Versions used: esptool-js 0.7.0, esbuild 0.28.2, Playwright 1.56.0, TypeScript 5.9.3, Node.js 22.
