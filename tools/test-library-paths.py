#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile the real library-path reader, writer and CustomOptional against SimpleIni.

Checks independent runtime values and save/reload behavior for all combinations of
missing, automatic and explicit XeSS/XeFG/XeLL paths. No Windows, GPU or game needed.
--source can also point at an older checkout to demonstrate the regression.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    header = (args.source / 'OptiScaler/Config.h').read_text(encoding='utf-8-sig')
    source = (args.source / 'OptiScaler/Config.cpp').read_text(encoding='utf-8-sig')
    optional = header[header.index('enum HasDefaultValue'):header.index('constexpr inline int UnboundKey')]
    begin = source.index('XeSSLibrary.set_from_config(readWString("Libraries", "XeSSPath"))')
    end = source.index('XeSSDx11Library.set_from_config', begin)
    reader = source[begin:end]
    writers = re.findall(r'ini.SetValue\("Libraries", "(?:XeSSPath|XeFGPath|XeLLPath)",[\s\S]*?;', source)
    assert len(writers) == 3, 'Expected three library-path writers'
    harness = r'''
#include <concepts>
#include <optional>
#include <string>
#include <utility>
#include <array>
#include <cstdio>
#include "SimpleIni.h"
@OPTIONAL@
static CSimpleIniA ini;
static std::string wstring_to_string(const std::wstring& value) { return {value.begin(), value.end()}; }
struct Config {
    CustomOptional<std::wstring, NoDefault> XeSSLibrary, XeFGLibrary, XeLLLibrary;
    inline static Config* instance;
    static Config* Instance() { return instance; }
    std::optional<std::wstring> readWString(const char* section, const char* key) {
        const char* value = ini.GetValue(section, key, "auto");
        if (!*value || std::string(value) == "auto") return std::nullopt;
        std::string text(value); return std::wstring(text.begin(), text.end());
    }
    void read() { @READER@ }
    void save() { @WRITERS@ }
};
static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::printf("FAIL line %d: %s\n", __LINE__, #condition); ++failures; } } while (0)
int main() {
    const std::array<const char*, 3> keys = {"XeSSPath", "XeFGPath", "XeLLPath"};
    const std::array<const char*, 3> paths = {"custom/SR.dll", ".\\libxess_fg.dll", ".\\libxell.dll"};
    for (int test = 0; test < 27; ++test) {
        ini.Reset(); int flags = test;
        std::array<std::optional<std::wstring>, 3> expected;
        for (int i = 0; i < 3; ++i) {
            int state = flags % 3; flags /= 3;
            if (state == 1) ini.SetValue("Libraries", keys[i], "auto");
            if (state == 2) {
                ini.SetValue("Libraries", keys[i], paths[i]);
                std::string text(paths[i]); expected[i] = std::wstring(text.begin(), text.end());
            }
        }
        ini.SetValue("Other", "Preserved", "yes");
        Config first; Config::instance = &first; first.read();
        auto check = [&](Config& cfg) {
            CHECK(static_cast<std::optional<std::wstring>>(cfg.XeSSLibrary) == expected[0]);
            CHECK(static_cast<std::optional<std::wstring>>(cfg.XeFGLibrary) == expected[1]);
            CHECK(static_cast<std::optional<std::wstring>>(cfg.XeLLLibrary) == expected[2]);
        };
        check(first); first.save();
        for (int i = 0; i < 3; ++i)
            CHECK(std::string(ini.GetValue("Libraries", keys[i], "missing")) == (expected[i] ? paths[i] : "auto"));
        std::string saved; CHECK(ini.Save(saved) == SI_OK);
        ini.Reset(); CHECK(ini.LoadData(saved) == SI_OK);
        Config second; Config::instance = &second; second.read(); check(second); second.save();
        CHECK(std::string(ini.GetValue("Other", "Preserved", "missing")) == "yes");
    }
    std::printf("27 library-path combinations, runtime and save/reload: %s (%d failures)\n", failures ? "FAIL" : "PASS", failures);
    return failures ? 1 : 0;
}
'''
    for key, value in [('OPTIONAL', optional), ('READER', reader), ('WRITERS', '\n'.join(writers))]:
        harness = harness.replace('@' + key + '@', value)
    with tempfile.TemporaryDirectory(prefix='opti-library-paths-') as temporary:
        root = Path(temporary)
        (root / 'test.cpp').write_text(harness)
        subprocess.run([os.environ.get('CXX', 'clang++'), '-std=c++20', '-I',
                        str(args.source / 'external/simpleini'), str(root / 'test.cpp'), '-o', str(root / 'test')], check=True)
        subprocess.run([str(root / 'test')], check=True)


if __name__ == '__main__':
    main()
