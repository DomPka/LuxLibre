// SPDX-License-Identifier: MIT OR Apache-2.0
//! Button debouncing and gesture recognition.
//!
//! * debounce: a level change must be stable for [`DEBOUNCE_MS`];
//! * click: press shorter than [`CLICK_MAX_MS`];
//! * clicks belong together while the gap between them is shorter than [`CLICK_GAP_MS`];
//! * hold: press reaching [`CLICK_MAX_MS`]; while held, a repeat every [`HOLD_REPEAT_MS`].
//!
//! Events carry the number of complete clicks that preceded the press, so
//! "click + click-and-hold" is `HoldStart(1)` and a plain hold `HoldStart(0)`.

use crate::config::{CLICK_GAP_MS, CLICK_MAX_MS, DEBOUNCE_MS, HOLD_REPEAT_MS};

/// Debounced edge filter.
#[derive(Clone, Copy, Debug)]
pub struct Debouncer {
    stable: bool,
    candidate: bool,
    since: u64,
}

impl Debouncer {
    pub fn new(initial: bool, now: u64) -> Self {
        Self {
            stable: initial,
            candidate: initial,
            since: now,
        }
    }

    /// Debounced level.
    pub fn level(&self) -> bool {
        self.stable
    }

    /// Start time of a change that is still being debounced.
    pub fn pending_since(&self) -> Option<u64> {
        (self.candidate != self.stable).then_some(self.since)
    }

    /// Feed a raw sample. Returns `Some((level, t))` when a change has been
    /// stable for the debounce time; `t` is when the change started.
    pub fn update(&mut self, raw: bool, now: u64) -> Option<(bool, u64)> {
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

/// A recognised button event.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum GestureEvent {
    /// Debounced press (every press, also inside multi-click gestures).
    Press,
    /// Debounced release.
    Release,
    /// `n` clicks completed (the gap after the last one has expired).
    Clicks(u8),
    /// A press became a hold; argument = clicks before this press.
    HoldStart(u8),
    /// Repeat while the hold continues (every [`HOLD_REPEAT_MS`]).
    HoldRepeat(u8),
    /// The hold ended (button released).
    HoldEnd(u8),
}

/// Small fixed buffer of events produced by one update.
#[derive(Clone, Copy, Debug)]
pub struct Events {
    buf: [GestureEvent; 8],
    len: usize,
}

impl Events {
    const fn new() -> Self {
        Self {
            buf: [GestureEvent::Press; 8],
            len: 0,
        }
    }

    fn push(&mut self, e: GestureEvent) {
        if self.len < self.buf.len() {
            self.buf[self.len] = e;
            self.len += 1;
        }
    }

    pub fn as_slice(&self) -> &[GestureEvent] {
        &self.buf[..self.len]
    }

    pub fn is_empty(&self) -> bool {
        self.len == 0
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum State {
    Idle,
    Pressed { since: u64, clicks: u8 },
    Holding { clicks: u8, next_repeat: u64 },
    Released { at: u64, clicks: u8 },
}

/// Debouncer + gesture state machine.
#[derive(Clone, Copy, Debug)]
pub struct GestureParser {
    deb: Debouncer,
    state: State,
}

impl GestureParser {
    /// Button released at start.
    pub fn new(now: u64) -> Self {
        Self {
            deb: Debouncer::new(false, now),
            state: State::Idle,
        }
    }

    /// Woken from deep sleep by the button, which is still pressed: the press
    /// is taken to have started now (the boot time is not counted).
    pub fn new_pressed(now: u64) -> Self {
        Self {
            deb: Debouncer::new(true, now),
            state: State::Pressed {
                since: now,
                clicks: 0,
            },
        }
    }

    /// Woken by the button, but it was released again before the firmware
    /// could sample it: counts as one complete click ending now.
    pub fn new_after_click(now: u64) -> Self {
        Self {
            deb: Debouncer::new(false, now),
            state: State::Released { at: now, clicks: 1 },
        }
    }

    /// No gesture in progress and the button is released.
    pub fn is_idle(&self) -> bool {
        self.state == State::Idle && !self.deb.level()
    }

    /// Debounced button level.
    pub fn pressed(&self) -> bool {
        self.deb.level()
    }

    /// Feed a raw button sample (`true` = pressed). Call every 5-20 ms while
    /// [`Self::is_idle`] is false, otherwise at least on every edge.
    pub fn update(&mut self, raw_pressed: bool, now: u64) -> Events {
        let mut ev = Events::new();
        if let Some((level, t)) = self.deb.update(raw_pressed, now) {
            self.run_timers(t, &mut ev);
            self.edge(level, t, &mut ev);
        }
        // While an edge is still being debounced, time only advances up to the
        // moment that edge started: otherwise a 390 ms click would become a
        // hold (or a double click split in two) just because of the 25 ms
        // debounce latency.
        let horizon = self.deb.pending_since().unwrap_or(now).min(now);
        self.run_timers(horizon, &mut ev);
        ev
    }

    fn run_timers(&mut self, t: u64, ev: &mut Events) {
        match self.state {
            State::Pressed { since, clicks } => {
                if t.saturating_sub(since) >= CLICK_MAX_MS {
                    ev.push(GestureEvent::HoldStart(clicks));
                    self.state = State::Holding {
                        clicks,
                        next_repeat: since + CLICK_MAX_MS + HOLD_REPEAT_MS,
                    };
                    self.run_timers(t, ev);
                }
            }
            State::Holding { clicks, next_repeat } => {
                let mut next = next_repeat;
                let mut n = 0;
                while t >= next && n < 4 {
                    ev.push(GestureEvent::HoldRepeat(clicks));
                    next += HOLD_REPEAT_MS;
                    n += 1;
                }
                if t >= next {
                    // stalled for a long time: skip the missed repeats
                    next = t + HOLD_REPEAT_MS;
                }
                self.state = State::Holding {
                    clicks,
                    next_repeat: next,
                };
            }
            State::Released { at, clicks } => {
                if t.saturating_sub(at) >= CLICK_GAP_MS {
                    ev.push(GestureEvent::Clicks(clicks));
                    self.state = State::Idle;
                }
            }
            State::Idle => {}
        }
    }

    fn edge(&mut self, pressed: bool, t: u64, ev: &mut Events) {
        self.state = match (self.state, pressed) {
            (State::Idle, true) => {
                ev.push(GestureEvent::Press);
                State::Pressed { since: t, clicks: 0 }
            }
            (State::Released { clicks, .. }, true) => {
                ev.push(GestureEvent::Press);
                State::Pressed { since: t, clicks }
            }
            (State::Pressed { clicks, .. }, false) => {
                ev.push(GestureEvent::Release);
                State::Released {
                    at: t,
                    clicks: clicks.saturating_add(1),
                }
            }
            (State::Holding { clicks, .. }, false) => {
                ev.push(GestureEvent::Release);
                ev.push(GestureEvent::HoldEnd(clicks));
                State::Idle
            }
            (s, _) => s,
        };
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use GestureEvent::*;

    /// Drive the parser with a list of (level, duration_ms) segments, sampling
    /// every `step` ms; returns all non-Press/Release events with timestamps.
    pub fn run(p: &mut GestureParser, start: u64, segs: &[(bool, u64)], step: u64) -> (Vec<(u64, GestureEvent)>, u64) {
        let mut t = start;
        let mut out = Vec::new();
        for &(level, dur) in segs {
            let end = t + dur;
            while t < end {
                for e in p.update(level, t).as_slice() {
                    if !matches!(e, Press | Release) {
                        out.push((t, *e));
                    }
                }
                t += step;
            }
        }
        (out, t)
    }

    fn events(segs: &[(bool, u64)]) -> Vec<GestureEvent> {
        let mut p = GestureParser::new(0);
        let (ev, _) = run(&mut p, 0, segs, 5);
        assert!(p.is_idle() || segs.last().unwrap().0, "parser not idle");
        ev.into_iter().map(|(_, e)| e).collect()
    }

    const UP: bool = false;
    const DN: bool = true;

    #[test]
    fn single_click() {
        assert_eq!(events(&[(UP, 50), (DN, 150), (UP, 600)]), vec![Clicks(1)]);
    }

    #[test]
    fn multi_clicks() {
        let two = [(UP, 50), (DN, 120), (UP, 200), (DN, 120), (UP, 600)];
        assert_eq!(events(&two), vec![Clicks(2)]);
        let three = [(UP, 50), (DN, 100), (UP, 150), (DN, 100), (UP, 150), (DN, 100), (UP, 600)];
        assert_eq!(events(&three), vec![Clicks(3)]);
        let four = [
            (UP, 50),
            (DN, 100),
            (UP, 150),
            (DN, 100),
            (UP, 150),
            (DN, 100),
            (UP, 150),
            (DN, 100),
            (UP, 600),
        ];
        assert_eq!(events(&four), vec![Clicks(4)]);
    }

    #[test]
    fn gap_too_long_splits_gestures() {
        let segs = [(UP, 50), (DN, 100), (UP, 450), (DN, 100), (UP, 600)];
        assert_eq!(events(&segs), vec![Clicks(1), Clicks(1)]);
    }

    #[test]
    fn hold_and_repeats() {
        // held 2 s: HoldStart at 400 ms, repeats at 1000, 1600
        let mut p = GestureParser::new(0);
        let (ev, _) = run(&mut p, 0, &[(UP, 50), (DN, 2_000), (UP, 100)], 5);
        let kinds: Vec<_> = ev.iter().map(|(_, e)| *e).collect();
        assert_eq!(kinds, vec![HoldStart(0), HoldRepeat(0), HoldRepeat(0), HoldEnd(0)]);
        // timing: press starts at t=50 -> hold at 450 (+debounce latency 25)
        let t_hold = ev[0].0;
        assert!((450..=480).contains(&t_hold), "{t_hold}");
        assert!((ev[1].0 - t_hold).abs_diff(600) <= 5);
    }

    #[test]
    fn click_then_hold() {
        let segs = [(UP, 50), (DN, 120), (UP, 150), (DN, 900), (UP, 50)];
        let ev = events(&segs);
        assert_eq!(ev[0], HoldStart(1));
        assert_eq!(*ev.last().unwrap(), HoldEnd(1));
    }

    #[test]
    fn bounce_is_ignored() {
        // 10 ms glitches never reach the debounce time
        let segs = [(UP, 50), (DN, 10), (UP, 10), (DN, 10), (UP, 600)];
        assert_eq!(events(&segs), vec![]);
        // contact bounce at the start of a real press
        let segs = [(UP, 50), (DN, 5), (UP, 5), (DN, 150), (UP, 600)];
        assert_eq!(events(&segs), vec![Clicks(1)]);
    }

    #[test]
    fn boundary_400ms_is_hold() {
        let mut p = GestureParser::new(0);
        // exactly 400 ms pressed (debounced edges at 100 and 500)
        let (ev, _) = run(&mut p, 0, &[(UP, 100), (DN, 400), (UP, 600)], 1);
        let kinds: Vec<_> = ev.iter().map(|(_, e)| *e).collect();
        assert_eq!(kinds, vec![HoldStart(0), HoldEnd(0)]);
        let mut p = GestureParser::new(0);
        let (ev, _) = run(&mut p, 0, &[(UP, 100), (DN, 399), (UP, 600)], 1);
        let kinds: Vec<_> = ev.iter().map(|(_, e)| *e).collect();
        assert_eq!(kinds, vec![Clicks(1)]);
    }

    /// With the firmware's 10 ms sampling the debounce latency must not turn a
    /// long click into a hold, nor split a double click whose gap is just
    /// under 400 ms.
    #[test]
    fn debounce_latency_at_boundaries() {
        let mut p = GestureParser::new(0);
        let (ev, _) = run(&mut p, 0, &[(UP, 50), (DN, 390), (UP, 600)], 10);
        assert_eq!(ev.iter().map(|(_, e)| *e).collect::<Vec<_>>(), vec![Clicks(1)]);
        let mut p = GestureParser::new(0);
        let (ev, _) = run(&mut p, 0, &[(UP, 50), (DN, 100), (UP, 390), (DN, 100), (UP, 600)], 10);
        assert_eq!(ev.iter().map(|(_, e)| *e).collect::<Vec<_>>(), vec![Clicks(2)]);
        let mut p = GestureParser::new(0);
        let (ev, _) = run(&mut p, 0, &[(UP, 50), (DN, 100), (UP, 410), (DN, 100), (UP, 600)], 10);
        assert_eq!(ev.iter().map(|(_, e)| *e).collect::<Vec<_>>(), vec![Clicks(1), Clicks(1)]);
    }

    #[test]
    fn wake_pressed_hold() {
        let mut p = GestureParser::new_pressed(1_000);
        assert!(!p.is_idle());
        let (ev, _) = run(&mut p, 1_000, &[(DN, 500), (UP, 100)], 5);
        let kinds: Vec<_> = ev.iter().map(|(_, e)| *e).collect();
        assert_eq!(kinds, vec![HoldStart(0), HoldEnd(0)]);
    }

    #[test]
    fn wake_pressed_short_is_click() {
        let mut p = GestureParser::new_pressed(1_000);
        let (ev, _) = run(&mut p, 1_000, &[(DN, 60), (UP, 600)], 5);
        let kinds: Vec<_> = ev.iter().map(|(_, e)| *e).collect();
        assert_eq!(kinds, vec![Clicks(1)]);
    }

    #[test]
    fn wake_after_click_then_second_click() {
        // the first click happened during boot; a second one follows: double click
        let mut p = GestureParser::new_after_click(500);
        let (ev, _) = run(&mut p, 500, &[(UP, 100), (DN, 120), (UP, 600)], 5);
        let kinds: Vec<_> = ev.iter().map(|(_, e)| *e).collect();
        assert_eq!(kinds, vec![Clicks(2)]);
        let mut p = GestureParser::new_after_click(500);
        let (ev, _) = run(&mut p, 500, &[(UP, 600)], 5);
        assert_eq!(ev.iter().map(|(_, e)| *e).collect::<Vec<_>>(), vec![Clicks(1)]);
    }

    #[test]
    fn long_stall_does_not_flood() {
        let mut p = GestureParser::new(0);
        p.update(true, 0);
        p.update(true, 30); // debounced press at 0
        let ev = p.update(true, 100_000);
        assert!(ev.as_slice().len() <= 8);
        assert_eq!(ev.as_slice()[0], HoldStart(0));
        let ev = p.update(true, 100_010);
        assert!(ev.is_empty());
    }
}
