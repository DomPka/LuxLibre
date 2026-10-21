// SPDX-License-Identifier: GPL-3.0-or-later
// Minimal test framework for the host build (no external dependencies).
#pragma once

#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

namespace lxt {

struct Test {
    const char* name;
    void (*fn)();
};

inline std::vector<Test>& registry() {
    static std::vector<Test> r;
    return r;
}
inline int& failures() {
    static int f = 0;
    return f;
}
inline int& checks() {
    static int c = 0;
    return c;
}
inline const char*& current() {
    static const char* c = "";
    return c;
}

struct Reg {
    Reg(const char* n, void (*f)()) { registry().push_back({n, f}); }
};

inline void fail(const char* file, int line, const std::string& what) {
    failures()++;
    std::printf("  FAIL %s (%s:%d): %s\n", current(), file, line, what.c_str());
}

inline int run_all(const char* suite) {
    std::printf("%s: %zu tests\n", suite, registry().size());
    for (const Test& t : registry()) {
        current() = t.name;
        int before = failures();
        t.fn();
        std::printf("  %s %s\n", failures() == before ? "ok  " : "FAIL", t.name);
    }
    std::printf("%s: %d checks, %d failed\n", suite, checks(), failures());
    return failures() ? 1 : 0;
}

}  // namespace lxt

#define TEST(name)                                         \
    static void name();                                    \
    static lxt::Reg lxt_reg_##name(#name, name);           \
    static void name()

#define CHECK(cond)                                                     \
    do {                                                                \
        lxt::checks()++;                                                \
        if (!(cond)) lxt::fail(__FILE__, __LINE__, #cond);              \
    } while (0)

#define CHECK_MSG(cond, ...)                                            \
    do {                                                                \
        lxt::checks()++;                                                \
        if (!(cond)) {                                                  \
            char lxt_buf[256];                                          \
            std::snprintf(lxt_buf, sizeof lxt_buf, __VA_ARGS__);        \
            lxt::fail(__FILE__, __LINE__, std::string(#cond) + " - " + lxt_buf); \
        }                                                               \
    } while (0)
