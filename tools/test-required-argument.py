#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile the actual [BC250] RequireArgument check (OptiScaler/misc/RequiredArgument.h).

Checks that an unset or empty setting never reads the command line, that a malformed setting is refused without
reading it, the Microsoft C runtime's argument splitting (its documented examples, quoting, backslashes, the
program name), and whole-argument, case-insensitive matching. dllmain.cpp turns every verdict but NotRequired and
Present into OptiScaler's pass-through mode; the GPU checks separately start a game with and without the argument.
Also splits 2,000 random command lines that Python's subprocess.list2cmdline quoted by the same runtime's rules.
"""
import argparse
import os
from pathlib import Path
import random
import subprocess
import tempfile

HARNESS = r'''
#include "misc/RequiredArgument.h"
#include <cstdio>
#include <fstream>
#include <iterator>
using namespace RequiredArgument;
static int failures = 0, checks = 0;
static void check(bool condition, const char* what) {
    ++checks;
    if (!condition) { std::printf("FAIL %s\n", what); ++failures; }
}
static bool splits(const wchar_t* line, std::vector<std::wstring> expected) { return Arguments(line) == expected; }
static bool has(const wchar_t* line) { return Present(line, L"-nobattleye"); }
int main() {
    int reads = 0;
    auto reader = [&](const wchar_t* line) { return [&reads, line] { ++reads; return std::wstring_view(line); }; };
    const wchar_t* with = L"\"C:\\Games\\GTA V\\GTA5_Enhanced.exe\" -nobattleye -windowed";
    const wchar_t* without = L"\"C:\\Games\\GTA V\\GTA5_Enhanced.exe\" -windowed";

    check(Check(std::nullopt, reader(with)) == Verdict::NotRequired && reads == 0, "unset: command line not read");
    check(Check(std::wstring(), reader(with)) == Verdict::NotRequired && reads == 0, "empty: command line not read");
    check(Check(std::wstring(L"-nobattleye"), reader(with)) == Verdict::Present && reads == 1, "present");
    check(Check(std::wstring(L"-NoBattlEye"), reader(with)) == Verdict::Present && reads == 2, "setting case");
    check(Check(std::wstring(L"-nobattleye"), reader(without)) == Verdict::Missing && reads == 3, "missing");
    check(Check(std::wstring(L"-no battleye"), reader(with)) == Verdict::Invalid && reads == 3, "blank: not read");
    check(Check(std::wstring(L"\"-nobattleye\""), reader(with)) == Verdict::Invalid && reads == 3, "quoted setting");
    check(Check(std::wstring(L"-nobattleye\t"), reader(with)) == Verdict::Invalid, "tab");
    check(Check(std::wstring(L"-no\x01" L"battleye"), reader(with)) == Verdict::Invalid, "control character");
    check(Check(std::wstring(L"-no\x85" L"battleye"), reader(with)) == Verdict::Invalid, "next-line character");
    check(Check(std::wstring(L"-no\x2028" L"battleye"), reader(with)) == Verdict::Invalid, "line separator");
    check(Check(std::wstring(257, L'a'), reader(with)) == Verdict::Invalid, "longer than 256");
    check(IsValid(std::wstring(256, L'a')) && IsValid(L"/nobattleye") && IsValid(L"-mode=story") &&
              IsValid(L"-\x00e9t\x00e9"), "valid forms");

    // The C runtime's documented examples, after a program name
    check(splits(L"x.exe \"abc\" d e", { L"abc", L"d", L"e" }), "\"abc\" d e");
    check(splits(L"x.exe a\\\\b d\"e f\"g h", { L"a\\\\b", L"de fg", L"h" }), "a\\\\b d\"e f\"g h");
    check(splits(L"x.exe a\\\\\\\"b c d", { L"a\\\"b", L"c", L"d" }), "a\\\\\\\"b c d");
    check(splits(L"x.exe a\\\\\\\\\"b c\" d e", { L"a\\\\b c", L"d", L"e" }), "a\\\\\\\\\"b c\" d e");
    check(splits(L"x.exe a\"b\"\" c d", { L"ab\" c d" }), "a\"b\"\" c d");
    // Program name: quotes group, backslashes stay, nothing else is an argument
    check(splits(L"\"C:\\Program Files\\x.exe\" a", { L"a" }), "quoted program name");
    check(splits(L"\"C:\\Games\\x.exe\\\" a", { L"a" }), "program name: a backslash does not escape its quote");
    check(splits(L"C:\\Games\\x.exe\\\" a", {}), "program name: an opened quote takes the rest");
    check(splits(L"x.exe", {}), "no arguments");
    check(splits(L"x.exe   \t ", {}), "trailing blanks");
    check(splits(L"", {}), "empty command line");
    check(splits(L" a", { L"a" }), "leading blank: empty program name");
    check(splits(L"x.exe \"\"", { L"" }), "empty quoted argument");
    check(splits(L"x.exe \"a b", { L"a b" }), "unterminated quote");

    check(has(with), "after the program name");
    check(has(L"PlayGTAV.exe -nobattleye"), "unquoted program name");
    check(has(L"x.exe -NOBATTLEYE"), "case-insensitive");
    check(has(L"x.exe \"-nobattleye\""), "quoted argument");
    check(has(L"x.exe -nobattleye\"\""), "empty quoted part");
    check(has(L"x.exe\t-nobattleye"), "tab separator");
    check(has(L" -nobattleye"), "after an empty program name");
    check(!has(without), "absent");
    check(!has(L"x.exe -nobattleyes"), "longer argument");
    check(!has(L"x.exe x-nobattleye"), "suffix of an argument");
    check(!has(L"x.exe -nobattley"), "prefix of the argument");
    check(!has(L"x.exe \"-nobattleye -windowed\""), "inside a quoted argument");
    check(!has(L"x.exe \\\"-nobattleye\\\""), "with escaped quotes");
    check(!has(L"x.exe -nobattleye=0"), "with a value");
    check(!has(L"-nobattleye"), "as the program name");
    check(!has(L"\"C:\\-nobattleye\\x.exe\" -windowed"), "inside the program path");
    check(!has(L"C:\\-nobattleye -windowed"), "program name with the token's text");
    check(!Present(L"x.exe -nobattleye", L""), "empty token");

    // Round trips: count, command line, arguments, each NUL-terminated (ASCII)
    std::ifstream file(ROUND_TRIPS, std::ios::binary);
    std::string data((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    size_t at = 0, trips = 0, wrong = 0;
    auto field = [&] {
        size_t end = data.find('\0', at);
        std::wstring out(data.begin() + at, data.begin() + end);
        at = end + 1;
        return out;
    };
    while (at < data.size()) {
        size_t count = std::stoul(std::string(data.begin() + at, data.begin() + data.find('\0', at)));
        at = data.find('\0', at) + 1;
        std::wstring line = field();
        std::vector<std::wstring> expected;
        for (size_t k = 0; k < count; ++k)
            expected.push_back(field());
        ++trips;
        if (Arguments(line) != expected)
            ++wrong;
    }
    check(trips == 2000 && wrong == 0, "round trips through list2cmdline");

    std::printf("%d required-argument checks (%zu round trips): %s\n", checks, trips, failures ? "FAIL" : "PASS");
    return failures ? 1 : 0;
}
'''


def round_trips(count=2000):
    """Random argument lists (blanks, quotes, backslashes, empty arguments) and their command lines."""
    rng = random.Random(250)
    alphabet = ['a', 'b', '-', '=', ' ', '\t', '"', '\\', '\\', 'x']
    out = bytearray()
    for _ in range(count):
        arguments = [''.join(rng.choice(alphabet) for _ in range(rng.randrange(0, 7))) for _ in range(rng.randrange(0, 5))]
        line = subprocess.list2cmdline(['C:\\Games\\x.exe', *arguments])
        for value in [str(len(arguments)), line, *arguments]:
            out += value.encode('ascii') + b'\0'
    return bytes(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='opti-required-argument-') as directory:
        root = Path(directory)
        (root / 'test.cpp').write_text(HARNESS)
        (root / 'round-trips.bin').write_bytes(round_trips())
        subprocess.run([os.environ.get('CXX', 'clang++'), '-std=c++20', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', '-I', str(args.source / 'OptiScaler'),
                        '-DROUND_TRIPS="' + str(root / 'round-trips.bin') + '"', str(root / 'test.cpp'),
                        '-o', str(root / 'test')], check=True)
        subprocess.run([str(root / 'test')], check=True)


if __name__ == '__main__':
    main()
