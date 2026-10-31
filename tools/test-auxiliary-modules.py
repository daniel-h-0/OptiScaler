#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile the actual [Hotfix] AuxiliaryDxgiFactoryModules parser (OptiScaler/misc/AuxiliaryModules.h).

Checks the default (auto, empty), valid lists, whole-name case-insensitive matching (no suffix or stem matches),
and that every malformed list keeps the default and names the offending entry. hooks/Dxgi_Hooks.cpp uses the same
functions; the GPU checks separately exercise GTA V Enhanced's Social Club overlay.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

HARNESS = r'''
#include "misc/AuxiliaryModules.h"
#include <cstdio>
using namespace AuxiliaryModules;
static int failures = 0, checks = 0;
static void check(bool condition, const char* what) {
    ++checks;
    if (!condition) { std::printf("FAIL %s\n", what); ++failures; }
}
static std::vector<std::string> resolve(std::optional<std::string> value, std::optional<std::string>& rejected) {
    return Resolve(value, rejected);
}
static bool keepsDefault(const char* value, const char* entry) {
    std::optional<std::string> rejected;
    auto names = resolve(std::string(value), rejected);
    return names == std::vector<std::string> { "socialclubd3d12renderer.dll" } && rejected == std::string(entry);
}
int main() {
    const std::vector<std::string> fallback { "socialclubd3d12renderer.dll" };
    std::optional<std::string> rejected;
    check(resolve(std::nullopt, rejected) == fallback && !rejected, "auto keeps the default");
    check(resolve(std::string(), rejected) == fallback && !rejected, "an empty value keeps the default");
    check(resolve(std::string("SocialClubD3D12Renderer.dll"), rejected) == fallback && !rejected, "default spelled out");
    check(resolve(std::string("Overlay64.DLL|SocialClubD3D12Renderer.dll"), rejected) ==
              std::vector<std::string> { "overlay64.dll", "socialclubd3d12renderer.dll" } && !rejected,
          "two entries, lower case, in order");
    check(resolve(std::string(" a.dll |\tb.dll\t"), rejected) == std::vector<std::string> { "a.dll", "b.dll" } &&
              !rejected, "blanks around entries");
    check(resolve(std::string("a.dll|A.Dll|a.dll"), rejected) == std::vector<std::string> { "a.dll" } && !rejected,
          "duplicates kept once");
    check(resolve(std::string("my-overlay_2.0+x.dll"), rejected) == std::vector<std::string> { "my-overlay_2.0+x.dll" },
          "punctuation a file name can hold");
    check(resolve(std::string("OnlyOther.dll"), rejected) == std::vector<std::string> { "onlyother.dll" },
          "a list replaces the default");

    check(keepsDefault("a.dll||b.dll", ""), "empty entry");
    check(keepsDefault("|a.dll", ""), "leading separator");
    check(keepsDefault("a.dll|", ""), "trailing separator");
    check(keepsDefault("a.dll| |b.dll", ""), "blank entry");
    check(keepsDefault("none", "none"), "no extension");
    check(keepsDefault(".dll", ".dll"), "extension only");
    check(keepsDefault("GTA5_Enhanced.exe", "GTA5_Enhanced.exe"), "an executable");
    check(keepsDefault("overlay.asi", "overlay.asi"), "another extension");
    check(keepsDefault("a.dll.bak", "a.dll.bak"), "extension not last");
    check(keepsDefault("C:\\Social Club\\SocialClubD3D12Renderer.dll", "C:\\Social Club\\SocialClubD3D12Renderer.dll"),
          "a Windows path");
    check(keepsDefault("lib/a.dll", "lib/a.dll"), "a relative path");
    check(keepsDefault("*.dll", "*.dll"), "a wildcard");
    check(keepsDefault("social?.dll", "social?.dll"), "a single-character wildcard");
    check(keepsDefault("\"a.dll\"", "\"a.dll\""), "quotes");
    check(keepsDefault("a b.dll", "a b.dll"), "a blank inside");
    check(keepsDefault("a.dll b.dll", "a.dll b.dll"), "a forgotten separator");
    check(keepsDefault("a.dll,b.dll", "a.dll,b.dll"), "comma instead of |");
    check(keepsDefault("a.dll;b.dll", "a.dll;b.dll"), "semicolon instead of |");
    check(keepsDefault("a\x01.dll", "a\x01.dll"), "a control character");
    check(keepsDefault("a\x7f.dll", "a\x7f.dll"), "DEL");
    check(keepsDefault("caf\xc3\xa9.dll", "caf\xc3\xa9.dll"), "non-ASCII");
    check(keepsDefault("good.dll|bad", "bad"), "one bad entry rejects the list");
    check(keepsDefault((std::string(252, 'a') + ".dll").c_str(), (std::string(252, 'a') + ".dll").c_str()),
          "longer than 255");
    check(resolve(std::string(251, 'a') + ".dll", rejected).size() == 1 && !rejected, "255 characters");

    const auto names = *Parse("SocialClubD3D12Renderer.dll|Overlay64.dll");
    check(Contains(names, "SocialClubD3D12Renderer.dll"), "match");
    check(Contains(names, "SOCIALCLUBD3D12RENDERER.DLL"), "case-insensitive match");
    check(Contains(names, "overlay64.dll"), "second entry");
    check(!Contains(names, "socialclubd3d12renderer"), "no match without the extension");
    check(!Contains(names, "xsocialclubd3d12renderer.dll"), "no suffix match");
    check(!Contains(names, "socialclubd3d12renderer.dll.mui"), "no prefix match");
    check(!Contains(names, "GTA5_Enhanced.exe"), "the game is not auxiliary");
    check(!Contains(names, ""), "unknown caller");
    check(!Contains({}, "socialclubd3d12renderer.dll"), "empty list");

    std::printf("%d auxiliary-module checks: %s\n", checks, failures ? "FAIL" : "PASS");
    return failures ? 1 : 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='opti-auxiliary-modules-') as directory:
        root = Path(directory)
        (root / 'test.cpp').write_text(HARNESS)
        subprocess.run([os.environ.get('CXX', 'clang++'), '-std=c++20', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', '-I', str(args.source / 'OptiScaler'), str(root / 'test.cpp'),
                        '-o', str(root / 'test')], check=True)
        subprocess.run([str(root / 'test')], check=True)


if __name__ == '__main__':
    main()
