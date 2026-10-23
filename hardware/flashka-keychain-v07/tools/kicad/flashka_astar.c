// SPDX-License-Identifier: GPL-3.0-or-later
// A* grid search core of tools/kicad/route.py (FlashKa Keychain v0.6), same moves and costs as
// the Python version: 8 neighbours per layer, layer changes (vias) where vh allows them and no
// earlier via of the path is closer than the via pitch.  route.py compiles this file with the
// system C compiler on first use (ctypes); without a compiler it falls back to the Python loop.
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef struct { double f, g; int r, j, i; } node;

static int less(const node *a, const node *b) {
    if (a->f != b->f) return a->f < b->f;
    if (a->g != b->g) return a->g < b->g;
    if (a->r != b->r) return a->r < b->r;
    if (a->j != b->j) return a->j < b->j;
    return a->i < b->i;
}

typedef struct { node *v; long n, cap; } heap;

static int push(heap *h, node x) {
    if (h->n == h->cap) {
        long nc = h->cap ? h->cap * 2 : 4096;
        node *nv = realloc(h->v, nc * sizeof(node));
        if (!nv) return -1;
        h->v = nv; h->cap = nc;
    }
    long k = h->n++;
    while (k > 0) {
        long p = (k - 1) / 2;
        if (!less(&x, &h->v[p])) break;
        h->v[k] = h->v[p]; k = p;
    }
    h->v[k] = x;
    return 0;
}

static node pop(heap *h) {
    node top = h->v[0];
    node x = h->v[--h->n];
    long k = 0;
    for (;;) {
        long c = 2 * k + 1;
        if (c >= h->n) break;
        if (c + 1 < h->n && less(&h->v[c + 1], &h->v[c])) c++;
        if (!less(&h->v[c], &x)) break;
        h->v[k] = h->v[c]; k = c;
    }
    if (h->n) h->v[k] = x;
    return top;
}

/* returns the flat index of the goal node, -1 (no path) or -2 (expansion limit / memory) */
long astar(int nl, int ny, int nx,
           const uint8_t *A, const uint8_t *C, const float *Hr, const float *Hv,
           const uint8_t *vh, const uint8_t *vconf, const uint8_t *T, const uint8_t *S,
           int jlo, int jhi, int ilo, int ihi,
           int has_tb, int tj0, int tj1, int ti0, int ti1,
           const double *lcost, double pfac, double via_cost, int via_target, long max_expand,
           double via_lim, int back,
           const int *src, int nsrc, float *gb, int64_t *prev)
{
    const long L = (long)ny * nx;
    static const int dj[8] = {0, 0, 1, -1, 1, 1, -1, -1};
    static const int di[8] = {1, -1, 0, 0, 1, -1, 1, -1};
    static const double dc[8] = {1.0, 1.0, 1.0, 1.0, 1.414, 1.414, 1.414, 1.414};
    heap h = {0, 0, 0};
    long n = 0, goal = -1;
#define HEUR(J, I) (has_tb ? ({ int a_ = tj0 - (J) > 0 ? tj0 - (J) : 0; if ((J) - tj1 > a_) a_ = (J) - tj1; \
                     int b_ = ti0 - (I) > 0 ? ti0 - (I) : 0; if ((I) - ti1 > b_) b_ = (I) - ti1; \
                     (a_ > b_ ? a_ : b_) + 0.414 * (a_ < b_ ? a_ : b_); }) : 0.0)
    for (int s = 0; s < nsrc; s++) {
        int r = src[3 * s], j = src[3 * s + 1], i = src[3 * s + 2];
        gb[r * L + (long)j * nx + i] = 0.0f;
        node x = {HEUR(j, i), 0.0, r, j, i};
        if (push(&h, x)) { goal = -2; goto done; }
    }
    while (h.n) {
        node x = pop(&h);
        int r = x.r, j = x.j, i = x.i;
        long id = r * L + (long)j * nx + i;
        double g = x.g;
        if (g > gb[id] + 1e-6) continue;
        if (T[id] || (via_target && vh[(long)j * nx + i] && !S[id])) { goal = id; break; }
        if (++n > max_expand) { goal = -2; break; }
        double lc = lcost[r];
        for (int d = 0; d < 8; d++) {
            int j2 = j + dj[d], i2 = i + di[d];
            if (j2 < jlo || j2 >= jhi || i2 < ilo || i2 >= ihi) continue;
            long id2 = r * L + (long)j2 * nx + i2;
            if (!A[id2]) continue;
            if (dj[d] && di[d] && !(A[r * L + (long)j * nx + i2] || A[r * L + (long)j2 * nx + i])) continue;
            /* costs are kept in single precision like the float32 table gb */
            float g2 = (float)(g + dc[d] * lc * (1.0 + Hr[id2]) + (C[id2] ? pfac : 0.0));
            if (g2 < gb[id2]) {
                gb[id2] = g2;
                prev[id2] = id;
                node y = {g2 + HEUR(j2, i2), g2, r, j2, i2};
                if (push(&h, y)) { goal = -2; goto done; }
            }
        }
        long c2 = (long)j * nx + i;
        if (vh[c2]) {
            /* no earlier via of this path closer than the via pitch */
            int ok = 1, cr = r, k = 0;
            int64_t p = prev[id];
            while (p >= 0 && k < back) {
                int r0 = (int)(p / L);
                long rem = p % L;
                int j0 = (int)(rem / nx), i0 = (int)(rem % nx);
                if (r0 != cr && (double)(j0 - j) * (j0 - j) + (double)(i0 - i) * (i0 - i) < via_lim) { ok = 0; break; }
                cr = r0;
                p = prev[p];
                k++;
            }
            if (ok) {
                double vc = via_cost * (1.0 + Hv[c2]) + (vconf[c2] ? 3.0 * pfac : 0.0);
                for (int r2 = 0; r2 < nl; r2++) {
                    if (r2 == r) continue;
                    long id2 = r2 * L + c2;
                    if (!A[id2]) continue;
                    float g2 = (float)(g + vc);
                    if (g2 < gb[id2]) {
                        gb[id2] = g2;
                        prev[id2] = id;
                        node y = {g2 + HEUR(j, i), g2, r2, j, i};
                        if (push(&h, y)) { goal = -2; goto done; }
                    }
                }
            }
        }
    }
done:
    free(h.v);
    return goal;
}
