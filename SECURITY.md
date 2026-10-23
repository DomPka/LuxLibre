<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Security policy

Some LuxLibre lights talk to phones and computers. The FlashKa keychain light connects over
Bluetooth Low Energy (LE, the low-power kind of Bluetooth), can act as a keyboard that turns
slides, and comes with two web pages: a control app and a firmware installer. This page explains
how to report a security problem without making it public before it is fixed.

## Report a problem privately

Use GitHub's private vulnerability reporting:

1. Open the **Security** tab of the repository
   ([github.com/DomPka/LuxLibre/security](https://github.com/DomPka/LuxLibre/security)).
2. Click **Report a vulnerability**.
3. Describe the problem (see the list below) and submit it. Only you and the maintainers can see
   the report.

Please do not describe a security problem in a public issue, pull request or discussion until a
fix is published.

If there is no **Report a vulnerability** button, private reporting is not switched on yet. Then
open a public issue that only says that you have a security problem to report, with no details,
and wait for a maintainer to answer there.

**Safety or security?** A problem that happens by itself (heat, a cell, charging, a protection
that does not work) is a safety problem: report it in public as described in
[SAFETY.md](SAFETY.md#reporting-a-safety-problem). If someone else could cause it without the
owner's consent, for example over Bluetooth or from a web page, report it privately here.

### What to put in the report

- What an attacker can do, and what they need for it: for example being within Bluetooth range,
  a computer that is paired with the light, or a victim who opens a web page.
- The version: `ver` on the LuxLibre console, the FlashKa firmware version, or the control app
  version shown at the bottom of the app.
- The steps to reproduce it, and the phone, computer, operating system and browser you used.
- Logs, a Bluetooth capture or a proof of concept, if you have them.

Test only on lights, phones and computers that you own or are allowed to test.

## What happens next

A maintainer answers in the private report, works out the fix with you and agrees with you when
the details are published. A fix is published with a GitHub security advisory and an entry in
[CHANGELOG.md](CHANGELOG.md). The advisory credits you, unless you prefer not to be named.

## Scope

| In scope | Examples |
|---|---|
| FlashKa firmware: Bluetooth pairing and bonding (bonding: the light and a computer store a shared key so that they can reconnect) | pairing or bonding outside presenter mode; a device that is not paired reads or writes the encrypted keyboard characteristics; the stored keys of paired computers can be read or changed over the air |
| FlashKa firmware: HID (human interface device: the light acting as a keyboard in presenter mode) | the light sends keys other than the documented ones, or sends keys because of a device that is not paired with it |
| FlashKa firmware: control link of the app | the laser can be switched over Bluetooth (the design does not allow it); a Bluetooth window stays open longer than documented; packets that crash the light or make it skip a protection |
| Web pages: control app, firmware installer, this project's GitHub Pages site | script injection, for example through a device name; the installer writes a different firmware image from the one it shows, or an image made for the other FlashKa board; a page sends data off the computer (the pages are made to upload nothing) |
| LuxLibre firmware (`firmware/`) | console input that crashes the firmware, damages its stored settings or sets a parameter outside its allowed range; any way around the thermal, low-voltage, laser or lockout protections |

Out of scope:

- **Physical access.** Attacks that need the light in your hands: opening it, using its test
  pads, or installing other firmware through USB-C. The light has no secure boot on purpose:
  owners may install their own firmware ([LICENSING.md](LICENSING.md)).
- **Laser misuse** and other dangerous use of a light that works as designed: see
  [SAFETY.md](SAFETY.md).
- **The design limits listed below.**
- Problems in a browser, in the Bluetooth stack of an operating system or in a third-party
  library that LuxLibre uses as intended: report them to that project. Do tell us if LuxLibre
  uses such a part in an unsafe way.
- Copies, forks and products of other makers that are based on LuxLibre: report to whoever
  distributes them.
- Social engineering, and blocking the radio by jamming.

## Known design limits

These are documented choices, not vulnerabilities:

- **No pairing in flashlight mode.** While a Bluetooth window of the light is open (while the
  light is on, for 120 s after it is switched off, for 120 s after three clicks, and while USB is
  connected), anyone within Bluetooth range can connect with the control app and use all its
  functions, except the laser: it cannot be switched over Bluetooth. Range and the short windows
  are the protection
  ([Bluetooth protocol](hardware/flashka-keychain-v06/docs/ble_protocol.md)).
- **"Just Works" pairing in presenter mode.** Presenter mode uses LE Secure Connections without a
  PIN, so pairing does not protect against an attacker who is active within range at that moment.
  Pair a computer where nobody else is trying to connect. If a light was lost and found again,
  make it forget all computers (hold both side keys for 10 s: ^ and v on a v0.7, ‹ and › on a
  v0.6; the ring blinks white three times) and pair again.

## Supported versions

Security fixes are made for the newest release line only.

| Version | Contains | Security fixes |
|---|---|---|
| 0.3.x | LuxLibre firmware 0.3; FlashKa Keychain v0.7 with FlashKa firmware 0.7.0 and control app 0.7.0; the installer holds firmware 0.7.0 (v0.7) and 0.6.0 (v0.6) | yes |
| 0.2.x | LuxLibre firmware 0.2; FlashKa Keychain v0.6 with its firmware, control app and installer 0.6 | no |
| 0.1.x | LuxLibre firmware 0.1; FlashKa Keychain v0.5 | no |
