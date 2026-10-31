#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile the actual auxiliary-window guard against controlled HWND queries.

Checks zero-axis resolution, explicit-axis precedence, the existing 100-pixel
boundary, unknown windows, empty client axes and minimized windows (both
unknown, so a game window created minimized keeps FG), and per-factory marker
ownership. The GPU probe separately exercises DXGI.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    source = (args.source / 'OptiScaler/hooks/DxgiFactory_Hooks.cpp').read_text(encoding='utf-8-sig')
    start = source.index('static bool IsTinyWindowSwapchain(')
    end = source.index('\nHRESULT DxgiFactoryHooks::CreateSwapChain(', start)
    guard = source[start:end]
    factory = source[source.index('static const GUID AuxiliaryFactoryMarker'):source.index('\n#ifdef DETAILED_SC_LOGS')]
    harness = r'''
#include <cstdio>
#include <cstring>
#define LOG_DEBUG(...) ((void)0)
#define LOG_WARN(...) ((void)0)
using HRESULT = int;
#define FAILED(hr) ((hr) < 0)
#define SUCCEEDED(hr) ((hr) >= 0)
#define IID_PPV_ARGS(ptr) 0, reinterpret_cast<void**>(ptr)
struct GUID { unsigned int a; unsigned short b, c; unsigned char d[8]; };
using UINT = unsigned int;
struct RECT { long left, top, right, bottom; };
struct Window { bool valid; RECT client; bool iconic = false; };
using HWND = Window*;
static int queries = 0, iconicQueries = 0;
static bool GetClientRect(HWND window, RECT* rect) {
    ++queries;
    if (!window || !window->valid) return false;
    *rect = window->client; return true;
}
static bool IsIconic(HWND window) { ++iconicQueries; return window && window->valid && window->iconic; }
struct IDXGIFactory {
    unsigned int value = 0, length = 0;
    int refs = 1;
    bool queryFails = false, writeFails = false;
    HRESULT QueryInterface(int, void** out) {
        if (queryFails) return -1;
        ++refs; *out = this; return 0;
    }
    int Release() { return --refs; }
    HRESULT SetPrivateData(const GUID&, UINT size, const void* data) {
        if (writeFails) return -1;
        length = size; std::memcpy(&value, data, size); return 0;
    }
    HRESULT GetPrivateData(const GUID&, UINT* size, void* data) {
        if (!length || *size < length) return -1;
        *size = length; std::memcpy(data, &value, length); return 0;
    }
};
using IDXGIObject = IDXGIFactory;
using IUnknown = IDXGIFactory;
struct DxgiFactoryHooks { static void MarkAuxiliaryFactory(IUnknown* factory); };
@FACTORY@
@GUARD@
#define CHECK(condition) do { if (!(condition)) { std::printf("FAIL marker: %s\n", #condition); ++failures; } } while (0)
int main() {
    Window tiny {true, {0, 0, 111, 66}};
    Window normal {true, {0, 0, 1280, 720}};
    Window boundary {true, {0, 0, 100, 100}};
    Window empty {true, {0, 0, 0, 0}};
    Window emptyWidth {true, {0, 0, 0, 66}};
    Window emptyHeight {true, {0, 0, 1280, 0}};
    Window minimized {true, {0, 0, 111, 66}, true};
    Window invalid {false, {0, 0, 1, 1}};
    // queries: GetClientRect calls; the window is asked IsIconic first whenever an axis is unresolved.
    struct Case { const char* name; HWND w; UINT width, height; bool tiny; int queries; };
    Case cases[] = {
        {"explicit tiny", &normal, 111, 66, true, 0},
        {"explicit normal", &tiny, 1280, 720, false, 0},
        {"resolved tiny", &tiny, 0, 0, true, 1},
        {"resolved normal", &normal, 0, 0, false, 1},
        {"zero height", &tiny, 1920, 0, true, 1},
        {"zero width with explicit normal height", &tiny, 0, 720, false, 1},
        {"zero width with explicit tiny height", &normal, 0, 66, true, 1},
        {"explicit boundary", &tiny, 100, 100, false, 0},
        {"below boundary", &normal, 99, 100, true, 0},
        {"resolved boundary", &boundary, 0, 0, false, 1},
        {"empty client", &empty, 0, 0, false, 1},
        {"empty client with explicit tiny width", &empty, 66, 0, true, 1},
        {"empty client with explicit normal height", &empty, 0, 720, false, 1},
        {"empty client width with tiny height", &emptyWidth, 0, 0, true, 1},
        {"empty client height with normal width", &emptyHeight, 0, 0, false, 1},
        {"empty client height with explicit tiny height", &emptyHeight, 0, 66, true, 1},
        {"minimized window", &minimized, 0, 0, false, 0},
        {"minimized with explicit tiny width", &minimized, 66, 0, true, 0},
        {"minimized with explicit normal axes", &minimized, 1280, 720, false, 0},
        {"unknown window", nullptr, 0, 0, false, 0},
        {"unknown with known small axis", nullptr, 0, 66, true, 0},
        {"failed query", &invalid, 0, 0, false, 1},
        {"failed query with known normal axis", &invalid, 111, 0, false, 1},
        {"failed query with explicit tiny axis", &invalid, 66, 0, true, 1},
    };
    int failures = 0;
    for (auto test : cases) {
        queries = iconicQueries = 0;
        bool actual = IsTinyWindowSwapchain(test.w, test.width, test.height);
        int iconic = test.w && (!test.width || !test.height) ? 1 : 0;
        if (actual != test.tiny || queries != test.queries || iconicQueries != iconic) {
            std::printf("FAIL %s: tiny=%d queries=%d iconic=%d\n", test.name, actual, queries, iconicQueries);
            ++failures;
        }
    }
    std::printf("%zu auxiliary-window size cases: %s\n", sizeof(cases) / sizeof(cases[0]), failures ? "FAIL" : "PASS");
    const int sizeFailures = failures;
    IDXGIFactory overlay, game, failedQuery, failedWrite, malformed;
    CHECK(!IsAuxiliaryFactory(nullptr));
    CHECK(!IsAuxiliaryFactory(&overlay));
    DxgiFactoryHooks::MarkAuxiliaryFactory(nullptr);
    DxgiFactoryHooks::MarkAuxiliaryFactory(&overlay);
    CHECK(IsAuxiliaryFactory(&overlay));
    CHECK(overlay.refs == 1);
    CHECK(!IsAuxiliaryFactory(&game));
    DxgiFactoryHooks::MarkAuxiliaryFactory(&overlay);
    CHECK(overlay.refs == 1);
    failedQuery.queryFails = true;
    DxgiFactoryHooks::MarkAuxiliaryFactory(&failedQuery);
    CHECK(!IsAuxiliaryFactory(&failedQuery) && failedQuery.refs == 1);
    failedWrite.writeFails = true;
    DxgiFactoryHooks::MarkAuxiliaryFactory(&failedWrite);
    CHECK(!IsAuxiliaryFactory(&failedWrite) && failedWrite.refs == 1);
    malformed.length = 2; malformed.value = 1;
    CHECK(!IsAuxiliaryFactory(&malformed));
    malformed.length = sizeof(UINT); malformed.value = 2;
    CHECK(!IsAuxiliaryFactory(&malformed));
    std::printf("10 factory-marker checks: %s\n", failures > sizeFailures ? "FAIL" : "PASS");
    return failures ? 1 : 0;
}
'''.replace('@GUARD@', guard).replace('@FACTORY@', factory)
    with tempfile.TemporaryDirectory(prefix='opti-window-size-') as directory:
        root = Path(directory)
        (root / 'test.cpp').write_text(harness)
        subprocess.run([os.environ.get('CXX', 'clang++'), '-std=c++20', '-fsanitize=address,undefined',
                        str(root / 'test.cpp'), '-o', str(root / 'test')], check=True)
        subprocess.run([str(root / 'test')], check=True)


if __name__ == '__main__':
    main()
