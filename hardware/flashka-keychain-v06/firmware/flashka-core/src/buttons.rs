// SPDX-License-Identifier: MIT OR Apache-2.0
//! The v0.6 three-button resistor ladder: classification of the ADC reading
//! and the gestures of the two slide buttons (› next, ‹ previous).
//!
//! All buttons pull the same BTN net (10 k pull-up R9) down:
//!
//! | Pressed | BTN | Class |
//! |---|---|---|
//! | none | 3.30 V | [`ButtonClass::None`] (> 810 mV) |
//! | ● main (alone or with others) | 0 V | [`ButtonClass::Main`] (< 106 mV) |
//! | ‹ + › | 0.212 V | [`ButtonClass::Both`] (106 to < 256 mV) |
//! | › next (1 k) | 0.300 V | [`ButtonClass::Next`] (256 to < 448 mV) |
//! | ‹ previous (2.2 k) | 0.595 V | [`ButtonClass::Prev`] (448 to 810 mV) |
//!
//! A class counts once it has been stable for [`DEBOUNCE_MS`]. The main
//! button keeps the v0.5 gesture parser ([`crate::gesture`]); this module
//! adds the slide-button gestures. The main button always wins: while ● is
//! pressed, slide gestures are cancelled and only start again after every
//! button has been released.

use crate::config::{
    BOTH_FORGET_MS, BOTH_PRESENTER_MS, BTN_BOTH_BELOW_MV, BTN_MAIN_BELOW_MV, BTN_NEXT_BELOW_MV, BTN_PREV_MAX_MV,
    DEBOUNCE_MS, SLIDE_HOLD_MS,
};

/// Which button(s) the BTN voltage says are pressed.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ButtonClass {
    None,
    Main,
    Both,
    Next,
    Prev,
}

impl ButtonClass {
    pub fn is_pressed(self) -> bool {
        self != ButtonClass::None
    }
}

/// Classify a calibrated ADC reading of GPIO3 (mV).
pub fn classify_mv(mv: u16) -> ButtonClass {
    if mv < BTN_MAIN_BELOW_MV {
        ButtonClass::Main
    } else if mv < BTN_BOTH_BELOW_MV {
        ButtonClass::Both
    } else if mv < BTN_NEXT_BELOW_MV {
        ButtonClass::Next
    } else if mv <= BTN_PREV_MAX_MV {
        ButtonClass::Prev
    } else {
        ButtonClass::None
    }
}

/// Classify one sample. `adc_mv = None` (conversion failed): fall back to the
/// digital input GPIO9 on the same net, which only knows "pressed" - it is
/// taken as the main button, so the flashlight keeps its v0.5 single-button
/// behaviour even without the ADC.
pub fn classify_sample(adc_mv: Option<u16>, digital_low: bool) -> ButtonClass {
    match adc_mv {
        Some(mv) => classify_mv(mv),
        None if digital_low => ButtonClass::Main,
        None => ButtonClass::None,
    }
}

/// Debounce of the ladder class: a new class counts once it has been stable
/// for [`DEBOUNCE_MS`] (the same rule as the v0.5 button).
#[derive(Clone, Copy, Debug)]
pub struct LadderDebouncer {
    stable: ButtonClass,
    candidate: ButtonClass,
    since: u64,
}

impl LadderDebouncer {
    pub fn new(initial: ButtonClass, now: u64) -> Self {
        Self {
            stable: initial,
            candidate: initial,
            since: now,
        }
    }

    pub fn level(&self) -> ButtonClass {
        self.stable
    }

    /// Start time of a change that is still being debounced.
    pub fn pending_since(&self) -> Option<u64> {
        (self.candidate != self.stable).then_some(self.since)
    }

    /// Feed a raw class. Returns `Some((class, t))` when a change has been
    /// stable for the debounce time; `t` is when the change started.
    pub fn update(&mut self, raw: ButtonClass, now: u64) -> Option<(ButtonClass, u64)> {
        if raw == self.stable {
            self.candidate = raw;
            return None;
        }
        if raw != self.candidate {
            self.candidate = raw;
            self.since = now;
        }
        if now.saturating_sub(self.since) >= DEBOUNCE_MS {
            self.stable = raw;
            Some((raw, self.since))
        } else {
            None
        }
    }
}

/// One of the two slide buttons.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Slide {
    /// › next (towards the screen).
    Next,
    /// ‹ previous.
    Prev,
}

impl Slide {
    pub fn swapped(self) -> Slide {
        match self {
            Slide::Next => Slide::Prev,
            Slide::Prev => Slide::Next,
        }
    }
}

/// A recognised slide-button event.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SlideEvent {
    /// Released before [`SLIDE_HOLD_MS`] and never combined with the other slide button.
    Click(Slide),
    /// Held for [`SLIDE_HOLD_MS`] (sent once, at the threshold).
    Hold(Slide),
    /// ‹ + › held for [`BOTH_PRESENTER_MS`] (sent once).
    Both2s,
    /// ‹ + › held for [`BOTH_FORGET_MS`] (sent once, after [`SlideEvent::Both2s`]).
    Both10s,
}

/// Events produced by one update.
#[derive(Clone, Copy, Debug)]
pub struct SlideEvents {
    buf: [SlideEvent; 4],
    len: usize,
}

impl SlideEvents {
    const fn new() -> Self {
        Self {
            buf: [SlideEvent::Both2s; 4],
            len: 0,
        }
    }

    fn push(&mut self, e: SlideEvent) {
        if self.len < self.buf.len() {
            self.buf[self.len] = e;
            self.len += 1;
        }
    }

    pub fn as_slice(&self) -> &[SlideEvent] {
        &self.buf[..self.len]
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum State {
    Idle,
    /// One slide button down.
    Single { slide: Slide, since: u64, held: bool },
    /// Both slide buttons down.
    Both { since: u64, fired2: bool, fired10: bool },
    /// The gesture was cancelled (main button pressed, one of two buttons
    /// released, or a direct change from one slide button to the other):
    /// wait until every button is released.
    Ignore,
}

/// Debouncer + slide-button gesture state machine.
///
/// A click is reported on release, so that pressing the second button of a
/// ‹ + › combination never sends a click of the first one.
#[derive(Clone, Copy, Debug)]
pub struct SlideParser {
    deb: LadderDebouncer,
    state: State,
    down_since: Option<u64>,
}

impl SlideParser {
    /// Nothing pressed at start.
    pub fn new(now: u64) -> Self {
        Self::new_with(ButtonClass::None, now)
    }

    /// `initial` = the class seen at the first sample after boot (a press
    /// that woke the chip is taken to have started now).
    pub fn new_with(initial: ButtonClass, now: u64) -> Self {
        let state = match initial {
            ButtonClass::None => State::Idle,
            ButtonClass::Main => State::Ignore,
            ButtonClass::Both => State::Both {
                since: now,
                fired2: false,
                fired10: false,
            },
            ButtonClass::Next => State::Single {
                slide: Slide::Next,
                since: now,
                held: false,
            },
            ButtonClass::Prev => State::Single {
                slide: Slide::Prev,
                since: now,
                held: false,
            },
        };
        Self {
            deb: LadderDebouncer::new(initial, now),
            state,
            down_since: initial.is_pressed().then_some(now),
        }
    }

    /// Debounced class.
    pub fn level(&self) -> ButtonClass {
        self.deb.level()
    }

    /// Since when any button (the main one included) is held down.
    pub fn down_since(&self) -> Option<u64> {
        self.down_since
    }

    /// No slide gesture in progress. A held main button counts as idle here
    /// (the main gesture parser reports it).
    pub fn is_idle(&self) -> bool {
        match self.state {
            State::Idle => true,
            State::Ignore => matches!(self.deb.level(), ButtonClass::Main | ButtonClass::None),
            _ => false,
        }
    }

    /// Feed a raw class (call every 5-20 ms).
    pub fn update(&mut self, raw: ButtonClass, now: u64) -> SlideEvents {
        let mut ev = SlideEvents::new();
        if let Some((level, t)) = self.deb.update(raw, now) {
            self.run_timers(t, &mut ev);
            self.edge(level, t, &mut ev);
        }
        // As in the main gesture parser: while a change is being debounced,
        // time only advances to the moment it started (a 790 ms press stays a click).
        let horizon = self.deb.pending_since().unwrap_or(now).min(now);
        self.run_timers(horizon, &mut ev);
        ev
    }

    fn run_timers(&mut self, t: u64, ev: &mut SlideEvents) {
        match self.state {
            State::Single {
                slide,
                since,
                held: false,
            } if t.saturating_sub(since) >= SLIDE_HOLD_MS => {
                ev.push(SlideEvent::Hold(slide));
                self.state = State::Single {
                    slide,
                    since,
                    held: true,
                };
            }
            State::Both {
                since,
                mut fired2,
                mut fired10,
            } => {
                let el = t.saturating_sub(since);
                if !fired2 && el >= BOTH_PRESENTER_MS {
                    ev.push(SlideEvent::Both2s);
                    fired2 = true;
                }
                if !fired10 && el >= BOTH_FORGET_MS {
                    ev.push(SlideEvent::Both10s);
                    fired10 = true;
                }
                self.state = State::Both { since, fired2, fired10 };
            }
            _ => {}
        }
    }

    fn edge(&mut self, level: ButtonClass, t: u64, ev: &mut SlideEvents) {
        use ButtonClass as C;
        self.down_since = match (self.down_since, level.is_pressed()) {
            (None, true) => Some(t),
            (Some(s), true) => Some(s),
            (_, false) => None,
        };
        self.state = match (self.state, level) {
            // the main button always wins
            (_, C::Main) => State::Ignore,
            (State::Ignore, C::None) => State::Idle,
            (State::Ignore, _) => State::Ignore,
            (State::Idle, C::Next) => State::Single {
                slide: Slide::Next,
                since: t,
                held: false,
            },
            (State::Idle, C::Prev) => State::Single {
                slide: Slide::Prev,
                since: t,
                held: false,
            },
            (State::Idle | State::Single { .. }, C::Both) => State::Both {
                since: t,
                fired2: false,
                fired10: false,
            },
            (State::Idle, C::None) => State::Idle,
            (State::Single { slide, held, .. }, C::None) => {
                if !held {
                    ev.push(SlideEvent::Click(slide));
                }
                State::Idle
            }
            // (edges only report changes; kept for completeness)
            (s @ State::Single { slide: Slide::Next, .. }, C::Next)
            | (s @ State::Single { slide: Slide::Prev, .. }, C::Prev)
            | (s @ State::Both { .. }, C::Both) => s,
            // direct change from one slide button to the other: ambiguous, drop it
            (State::Single { .. }, C::Next | C::Prev) => State::Ignore,
            (State::Both { .. }, C::None) => State::Idle,
            // one of the two released: the combination is over
            (State::Both { .. }, C::Next | C::Prev) => State::Ignore,
        };
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ButtonClass as C;
    use SlideEvent::*;

    #[test]
    fn classification_levels_and_edges() {
        // nominal ladder voltages
        assert_eq!(classify_mv(0), C::Main);
        assert_eq!(classify_mv(212), C::Both);
        assert_eq!(classify_mv(300), C::Next);
        assert_eq!(classify_mv(595), C::Prev);
        assert_eq!(classify_mv(1_050), C::None);
        assert_eq!(classify_mv(u16::MAX), C::None);
        // boundaries: "< 106 MAIN, 106-256 BOTH, 256-448 NEXT, 448-810 PREV, > 810 NONE"
        assert_eq!(classify_mv(105), C::Main);
        assert_eq!(classify_mv(106), C::Both);
        assert_eq!(classify_mv(255), C::Both);
        assert_eq!(classify_mv(256), C::Next);
        assert_eq!(classify_mv(447), C::Next);
        assert_eq!(classify_mv(448), C::Prev);
        assert_eq!(classify_mv(810), C::Prev);
        assert_eq!(classify_mv(811), C::None);
    }

    /// Ladder voltages with 1 % resistors and the datasheet's +-10 mV ADC error
    /// stay inside their class, with the GPIO9 pull-up off as the firmware sets it.
    #[test]
    fn ladder_tolerance() {
        let v = |r_low: f64, r_pu: f64| 3_300.0 * r_low / (r_low + r_pu);
        for (r_low, class) in [(1_000.0, C::Next), (2_200.0, C::Prev), (1_000.0 * 2_200.0 / 3_200.0, C::Both)] {
            for k_low in [0.99, 1.01] {
                for k_pu in [0.99, 1.01] {
                    for err in [-10.0, 10.0] {
                        let mv = v(r_low * k_low, 10_000.0 * k_pu) + err;
                        assert_eq!(classify_mv(mv as u16), class, "{r_low} {k_low} {k_pu} {err}: {mv}");
                    }
                }
            }
        }
        // supply at 3.0 V (low battery LDO dropout) still classifies correctly
        assert_eq!(classify_mv((3_000.0 * 1_000.0 / 11_000.0) as u16), C::Next);
        assert_eq!(classify_mv((3_000.0 * 2_200.0 / 12_200.0) as u16), C::Prev);
    }

    #[test]
    fn digital_fallback() {
        assert_eq!(classify_sample(None, true), C::Main);
        assert_eq!(classify_sample(None, false), C::None);
        assert_eq!(classify_sample(Some(300), false), C::Next);
        assert_eq!(classify_sample(Some(2_000), true), C::None);
    }

    /// Drive a parser with (class, duration) segments sampled every `step` ms.
    fn run(p: &mut SlideParser, start: u64, segs: &[(ButtonClass, u64)], step: u64) -> (Vec<(u64, SlideEvent)>, u64) {
        let mut t = start;
        let mut out = Vec::new();
        for &(c, dur) in segs {
            let end = t + dur;
            while t < end {
                for e in p.update(c, t).as_slice() {
                    out.push((t, *e));
                }
                t += step;
            }
        }
        (out, t)
    }

    fn events(segs: &[(ButtonClass, u64)]) -> Vec<SlideEvent> {
        let mut p = SlideParser::new(0);
        let (ev, _) = run(&mut p, 0, segs, 10);
        ev.into_iter().map(|(_, e)| e).collect()
    }

    #[test]
    fn clicks_on_release() {
        assert_eq!(events(&[(C::None, 50), (C::Next, 120), (C::None, 100)]), vec![Click(Slide::Next)]);
        assert_eq!(events(&[(C::None, 50), (C::Prev, 120), (C::None, 100)]), vec![Click(Slide::Prev)]);
        // nothing while still pressed
        assert_eq!(events(&[(C::None, 50), (C::Next, 300)]), vec![]);
    }

    #[test]
    fn hold_threshold_800ms() {
        let mut p = SlideParser::new(0);
        let (ev, _) = run(&mut p, 0, &[(C::None, 100), (C::Next, 1_500), (C::None, 100)], 10);
        assert_eq!(ev.len(), 1, "{ev:?}");
        assert_eq!(ev[0].1, Hold(Slide::Next));
        // press starts at 100 (debounced at 125): hold at 900 (+ debounce latency)
        assert!((900..=930).contains(&ev[0].0), "{}", ev[0].0);
        // a 790 ms press is still a click (debounce latency is not counted)
        assert_eq!(events(&[(C::None, 50), (C::Prev, 790), (C::None, 100)]), vec![Click(Slide::Prev)]);
        assert_eq!(events(&[(C::None, 50), (C::Prev, 810), (C::None, 100)]), vec![Hold(Slide::Prev)]);
    }

    #[test]
    fn both_2s_and_10s() {
        let mut p = SlideParser::new(0);
        let (ev, _) = run(&mut p, 0, &[(C::None, 100), (C::Both, 11_000), (C::None, 100)], 10);
        let kinds: Vec<_> = ev.iter().map(|(_, e)| *e).collect();
        assert_eq!(kinds, vec![Both2s, Both10s]);
        assert!((2_100..=2_130).contains(&ev[0].0), "{}", ev[0].0);
        assert!((10_100..=10_130).contains(&ev[1].0), "{}", ev[1].0);
        // released after 1.9 s: nothing
        assert_eq!(events(&[(C::None, 50), (C::Both, 1_900), (C::None, 100)]), vec![]);
        // 5 s: only the 2 s event
        assert_eq!(events(&[(C::None, 50), (C::Both, 5_000), (C::None, 100)]), vec![Both2s]);
    }

    #[test]
    fn combination_never_clicks_the_first_button() {
        // › first, ‹ 100 ms later, held 2.5 s, released one after the other
        let segs = [(C::None, 50), (C::Next, 100), (C::Both, 2_500), (C::Prev, 100), (C::None, 100)];
        assert_eq!(events(&segs), vec![Both2s]);
        // short combination: no event at all
        let segs = [(C::None, 50), (C::Prev, 80), (C::Both, 300), (C::Next, 60), (C::None, 100)];
        assert_eq!(events(&segs), vec![]);
        // the Both timer starts when both are down, not at the first press
        let mut p = SlideParser::new(0);
        let (ev, _) = run(&mut p, 0, &[(C::None, 50), (C::Next, 700), (C::Both, 2_100), (C::None, 50)], 10);
        assert_eq!(ev.len(), 1);
        assert!(ev[0].0 >= 750 + 2_000, "{}", ev[0].0);
    }

    #[test]
    fn main_wins() {
        // › held, then ● pressed too, then ● released while › is still held: no event
        let segs = [(C::None, 50), (C::Next, 200), (C::Main, 300), (C::Next, 300), (C::None, 100)];
        assert_eq!(events(&segs), vec![]);
        // ● during a combination cancels it before 2 s
        let segs = [(C::None, 50), (C::Both, 1_500), (C::Main, 1_000), (C::Both, 1_000), (C::None, 100)];
        assert_eq!(events(&segs), vec![]);
        let mut p = SlideParser::new(0);
        run(&mut p, 0, &[(C::None, 50), (C::Main, 200)], 10);
        assert!(p.is_idle(), "a held main button is reported by the main parser");
        assert_eq!(p.level(), C::Main);
    }

    #[test]
    fn bounce_and_release_transients_are_filtered() {
        // releasing ● passes through the slide levels for a few ms: no slide event
        let segs = [(C::None, 50), (C::Main, 300), (C::Prev, 5), (C::Next, 5), (C::None, 200)];
        assert_eq!(events(&segs), vec![]);
        // 10 ms glitch of a slide level
        assert_eq!(events(&[(C::None, 50), (C::Next, 10), (C::None, 200)]), vec![]);
        let mut p = SlideParser::new(0);
        let segs = [(C::None, 50), (C::Next, 5), (C::None, 5), (C::Next, 150), (C::None, 100)];
        let (ev, _) = run(&mut p, 0, &segs, 1);
        assert_eq!(ev.iter().map(|(_, e)| *e).collect::<Vec<_>>(), vec![Click(Slide::Next)]);
    }

    #[test]
    fn direct_switch_between_slides_is_dropped() {
        let segs = [(C::None, 50), (C::Next, 200), (C::Prev, 200), (C::None, 100)];
        assert_eq!(events(&segs), vec![]);
    }

    #[test]
    fn down_since_and_idle() {
        let mut p = SlideParser::new(0);
        assert!(p.is_idle());
        run(&mut p, 0, &[(C::None, 100), (C::Prev, 500)], 10);
        assert_eq!(p.down_since(), Some(100));
        assert!(!p.is_idle());
        run(&mut p, 600, &[(C::None, 100)], 10);
        assert_eq!(p.down_since(), None);
        assert!(p.is_idle());
    }

    #[test]
    fn boot_with_button_held() {
        // woken by ‹ + › and still held: the 2 s count starts at the first sample
        let mut p = SlideParser::new_with(C::Both, 300);
        let (ev, _) = run(&mut p, 300, &[(C::Both, 2_100)], 10);
        assert_eq!(ev.len(), 1);
        assert_eq!(ev[0], (2_300, Both2s));
        let mut p = SlideParser::new_with(C::Next, 300);
        let (ev, _) = run(&mut p, 300, &[(C::Next, 100), (C::None, 100)], 10);
        assert_eq!(ev.iter().map(|(_, e)| *e).collect::<Vec<_>>(), vec![Click(Slide::Next)]);
        let p = SlideParser::new_with(C::Main, 300);
        assert_eq!(p.down_since(), Some(300));
    }
}
