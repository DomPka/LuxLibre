**What this changes and why**

**Checklist**
- [ ] `make -C firmware test` passes (CI runs it too)
- [ ] new behaviour has a test; a bug fix has a test that failed before
- [ ] `make -C firmware docs` run and committed if parameters or gestures changed
- [ ] new files start with an SPDX licence line
- [ ] safety-relevant change (thermal, low voltage, charging, laser, lockout)? It names the design rule and needs a second reviewer
- [ ] hardware change? Review checklist and, if built, a test report are included
- [ ] commits are signed off (`git commit -s`, see CONTRIBUTING.md)
