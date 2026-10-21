// SPDX-License-Identifier: MIT OR Apache-2.0
//! Small math helpers that `core` does not provide on a bare-metal target.

/// Natural logarithm for `x > 0` (returns `f32::NEG_INFINITY` for `x <= 0`).
///
/// `x = m * 2^e` with `m` in `[1, 2)`, `ln(x) = e*ln(2) + ln(m)` and
/// `ln(m) = 2*atanh(z)`, `z = (m-1)/(m+1)` in `[0, 1/3)`, summed as a series.
/// Absolute error < 1e-6 over the range used here.
pub fn ln_f32(x: f32) -> f32 {
    if x.is_nan() || x <= 0.0 {
        return f32::NEG_INFINITY;
    }
    if x.is_infinite() {
        return f32::INFINITY;
    }
    let mut bits = x.to_bits();
    let mut exp: i32 = ((bits >> 23) & 0xff) as i32;
    if exp == 0 {
        // Subnormal: normalise first (not reachable with real sensor values).
        let y = x * 8_388_608.0; // 2^23
        bits = y.to_bits();
        exp = ((bits >> 23) & 0xff) as i32 - 23;
    }
    let e = exp - 127;
    let m = f32::from_bits((bits & 0x007f_ffff) | 0x3f80_0000); // [1, 2)
    let z = (m - 1.0) / (m + 1.0);
    let z2 = z * z;
    // 2 * (z + z^3/3 + z^5/5 + ... + z^13/13)
    let mut term = z;
    let mut sum = z;
    let mut k = 3.0f32;
    while k < 14.0 {
        term *= z2;
        sum += term / k;
        k += 2.0;
    }
    e as f32 * core::f32::consts::LN_2 + 2.0 * sum
}

/// Integer division of `a` by `b`, rounded to the nearest integer.
pub const fn div_round(a: u64, b: u64) -> u64 {
    (a + b / 2) / b
}

/// Integer division rounded up.
pub const fn div_ceil(a: u64, b: u64) -> u64 {
    a.div_ceil(b)
}

/// Linear interpolation `y0 + (y1 - y0) * (x - x0) / (x1 - x0)` in i64.
pub fn lerp_i64(x: i64, x0: i64, x1: i64, y0: i64, y1: i64) -> i64 {
    if x1 == x0 {
        return y0;
    }
    y0 + (y1 - y0) * (x - x0) / (x1 - x0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ln_matches_std() {
        let mut x = 0.001f32;
        while x < 1000.0 {
            let a = ln_f32(x);
            let b = (x as f64).ln() as f32;
            assert!((a - b).abs() < 2e-6, "x={x} ln={a} std={b}");
            x *= 1.07;
        }
        assert_eq!(ln_f32(1.0), 0.0);
        assert!(ln_f32(0.0).is_infinite());
        assert!(ln_f32(-1.0).is_infinite());
    }

    #[test]
    fn rounding_helpers() {
        assert_eq!(div_round(5, 2), 3);
        assert_eq!(div_round(4, 3), 1);
        assert_eq!(div_ceil(4, 3), 2);
        assert_eq!(div_ceil(3, 3), 1);
        assert_eq!(lerp_i64(5, 0, 10, 100, 200), 150);
        assert_eq!(lerp_i64(5, 5, 5, 7, 9), 7);
    }
}
