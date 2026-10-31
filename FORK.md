# BC-250 fork of OptiScaler

## Social Club auxiliary swapchains

Social Club's D3D12 renderer creates its own swapchain in GTA V Enhanced. Passing that auxiliary swapchain to
XeFG can replace the game's context and crash inside the Intel runtime, even with interpolation disabled.
The existing size heuristic is insufficient: the descriptor can be 0×0 (window-derived), and the client size
varies between systems. A local reproduction measured 119×100, outside the existing below-100-pixel cutoff.

Factories created by `SocialClubD3D12Renderer.dll` now carry a private DXGI marker. The regular and DLSSG
swapchain hooks pass marked factories through unchanged, before changing the game's FG state. DXGI owns the
marker with its factory, so there is no stale-pointer registry to maintain. The policy does not enable factory
wrapping, disable the Social Club renderer, or change other callers' factories. The separate existing size guard
also resolves zero axes from the output window without rewriting the caller's descriptor. An empty client axis or
a minimized window leaves that axis unknown, as a zero descriptor axis always was: the empty client area of a
window that is minimized or not yet mapped says nothing about the size the game renders at, so a game that
creates its swapchain then keeps FG instead of being taken for an overlay for the whole session.

The modules are `[Hotfix] AuxiliaryDxgiFactoryModules` in `OptiScaler.ini`: DLL file names separated by `|`,
compared whole and case-insensitively; a list replaces the default `SocialClubD3D12Renderer.dll`. The parser
(`misc/AuxiliaryModules.h`) is strict, because an entry matching too much (a pattern, a path, part of a name, the
game's executable) would keep the game's own swapchain out of FG without a sign: a malformed list is logged and
the default kept. The marker assumes that every `CreateDXGIFactory*` call returns a distinct factory; a factory
shared with the game would keep the game's swapchains native too, so the first marked factory logs that assumption.

`tools/test-window-swapchain-size.py` compiles the actual guard and marker helpers with controlled API results
under ASan/UBSan. It checks 24 size cases and 13 marker/ownership cases, including the single assumption line.
`tools/test-auxiliary-modules.py` compiles the list parser and runs 41 checks. Runtime qualification additionally uses
real D3D12 main/auxiliary swapchains and normal GTA Story Mode starts. Factory wrapping avoided the reproduced
crash but stalled at initialization on the tested stack; it is not the remedy implemented here.

## Required launch argument

`[BC250] RequireArgument` in `OptiScaler.ini` names one launch argument without which OptiScaler must stay out of
the process, such as GTA V Enhanced's `-nobattleye`, which starts Story Mode without BattlEye. When it is set and
the process command line lacks that whole argument (split by the Microsoft C runtime's rules after the program
name; ASCII letters compared case-insensitively), OptiScaler works as a plain pass-through proxy, exactly as for a
process that `[ProcessFilter]` excludes: it loads the original DLL and forwards its exports, with no hooks, no
plugins and no frame generation, and logs one line naming the argument. A value that is not one argument (blanks,
quotes, control characters) has the same effect. Unset (`auto`, the default) or empty, the command line is not
read and nothing changes. OptiScaler's own settings save keeps the key as it was loaded: the installer that wrote
it owns it. The DLL itself stays loaded, so an anti-cheat that lists modules still sees it; nothing of it acts.

`tools/test-required-argument.py` compiles the check (`misc/RequiredArgument.h`) and runs 46 checks, among them
2,000 random command lines quoted by Python's `subprocess.list2cmdline` and split back.

## Candidate build of 30 October 2026

A candidate with the changes above (minimized windows, configurable auxiliary modules, required launch argument,
build record). It is not yet qualified on the GPU; FreeFG still pins `273e8d44` (`044cac6b…`).

| | |
| --- | --- |
| File | `OptiScaler.dll`, 29,409,280 bytes |
| sha256 | `e82bb9908ba81cdc9fc909f8e2d4eefa3481f6e73a3371b13ced986f2742a87b` |
| Version string | `OptiScaler v10.0.0-dev (ba0dedb46818-bc250) (BC250 private)` |
| Source | commit `ba0dedb4681875a1a0b88a35385d5aeb91db4063`, clean (`dirty: false`); the commit adding this record changes no source |
| Default INI | `OptiScaler.ini`, sha256 `060d8fcfb1374f69dfbe4df6b22fed30d6349b97e9b5f6272cad9f494c440cb8`: two keys more than `273e8d44`'s, `Hotfix.AuxiliaryDxgiFactoryModules` and `BC250.RequireArgument` |
| Built | 30 October 2026, Linux, `tools/bc250-build.py --jobs 4`: clang-cl, lld-link and llvm-rc 23.1.4, ninja 1.13.2, MSVC 14.44.35207, SDK 10.0.26100.0 |

## FreeFG 1.1.6 candidate

The candidate merges upstream `e7e3872d410f704479d94d318d68d163b6b58947` (29 October 2026) into the accepted fork.
Its upstream custom provider mechanism loads HLX DLSS and HLX FSR 4 from separate folders. The fork forwards the
original input API and the reactive-mask choice to HLX DLSS using HelixSR Scaler 2.1.0’s parameter contract. For an
FFX provider whose reported name starts with `HLX FSR 4`, it preserves HLX’s exposure implementation and logs the
actual provider identity so AMD fallback cannot be mistaken for HLX qualification. No Helix code or model data is
part of this fork. Existing library-path, INI-save and adaptive frame-start changes are retained.

Runtime qualification and the final candidate build identity are recorded with FreeFG’s 1.1.6 candidate report.
The release details below describe the prior accepted October 25 build.

This build merges upstream `08e13adf55b3fd71a67071eac2e95973ac598df3`, the commit used by the official
`nightly-20261025` DLL, into the released FreeFG fork. It retains independent XeSS/XeFG/XeLL library paths,
automatic INI saving and adaptive 3×/4× frame starts. Upstream's non-blocking Streamline module census
uses this fork's loader-first lock order.

FreeFG 1.1.3 shipped `1e802562…` from `be42012a` (`bc250-be42012`), based on OptiScaler master of 19 October.
FreeFG 1.0.0–1.1.2 shipped `5e570dff…` from `f971ed14` (`bc250-f971ed1`). Their tags remain available.

| | |
| --- | --- |
| File | `OptiScaler.dll` (`opti/OptiScaler.dll`), 29,214,208 bytes |
| sha256 | `b3602882c7e194af523e50861a222d63c0c56b013cff4bfb5b187ca4f6666656` |
| Version string | `OptiScaler v10.0.0-dev (03db4f869287-bc250-e3b0c442) (BC250 private)` |
| Source | commit `03db4f8692878e65748769ebe583c053cae96360` (tree `65fb869215201128d9468bb3316bb3af7b9223dc`) and its nine pinned submodules |
| Tag | `bc250-03db4f8`, the build commit plus this updated document |
| Built | 25 October 2026, Linux, clang-cl/lld-link 23.1.3, MSVC 14.44.35207 and SDK 10.0.26100.0, `tools/bc250-build.py --jobs 8` |

## Adaptive FreeFG frame starts

When XeLL does not hold the game back at 3×/4×, simulation starts can alternate short and long even though the
presentation layer displays frames evenly. This fork calls FreeFG's earlier MIT controller after its own XeLL sleep,
without adding hooks to Intel's runtime. It acts only with the FreeFG proxy loaded and an active 3×/4× XeFG output;
2× and marker-only XeLL contexts do not use it. The existing Present update publishes the actual multiplier to the
per-context controller, so the sleeping thread does not access a changing frame-generation feature.

The controller detects 16 alternating start intervals, tops up clearly early starts, and resets after loading gaps,
large gameplay stalls, multiplier changes or eight consecutive holds. A stall over 2.5 learned periods (at least 50 ms,
at most 250 ms) resets the estimate immediately. The last rule prevents a burst of stalls from making the controller
follow its own delay. It no longer treats a variable Present wait as proof that the GPU needs the old period: another
output scheduler can cause that wait. `BC250_XELL_PACE=0` disables this correction for comparison.

`tests/test_xell_pace.c` checks the CPU pipeline model, throughput, an already-working XeLL, noisy work, load changes,
hitches and stall-burst recovery. Run it with `cc -O1 -g -fsanitize=address,undefined tests/test_xell_pace.c -lm -o /tmp/test-xell-pace`
and then `/tmp/test-xell-pace`. FreeFG's MEASUREMENTS records the live TV checks and their limits.

## Library-path configuration fix

The older config reader assigned `XeFGPath` and `XeLLPath` to `XeSSLibrary`. `CustomOptional::set_from_config` keeps
the first non-automatic value, so with automatic XeSS and explicit XeFG the FG DLL became the upscaler override.
Save Settings then wrote that value as `XeSSPath`, with the actual XeFG/XeLL fields still automatic. The corrected
reader assigns each key to its matching field; automatic discovery and explicit custom paths remain independent.

Run `python3 tools/test-library-paths.py` after checking out `external/simpleini`. It compiles the real reader/writer
fragments and `CustomOptional` against SimpleIni and checks all 27 missing/automatic/explicit path combinations at
runtime and through save/reload. The old reader fails 84 assertions; the corrected reader passes all combinations.

The version string's last field is fixed text that the build script writes in place of a build date, so that
rebuilding gives the same bytes. It does not mean that the source is private.

This is not an official OptiScaler or OptiScaler Client release, and the OptiScaler project does not support it.
Report problems with this build to FreeFG (https://github.com/daniel-h-0/freefg), not to OptiScaler.

## Licence

OptiScaler is licensed under the GNU General Public License version 3 (`LICENSE`, unchanged from upstream). This fork,
including the changes below, is distributed under the same licence. `tools/bc250-build.py`, `tools/test-library-paths.py`, the FreeFG pacing controller and its tests carry MIT licence
headers; MIT is compatible with the GPL, and it is distributed here as part of the GPL-3.0 work. There is no warranty,
to the extent permitted by applicable law (GPL-3.0 sections 15 and 16).

## Earlier FreeFG changes

| Commit | What it changes | Needed by FreeFG |
| --- | --- | --- |
| `f971ed14` Take the loader lock before a Streamline plugin mutex | The Streamline plugin hooks lock in a fixed order: the loader lock first, then the plugin mutex; no plugin mutex is held across a library load (below). `hooks/LibraryLoad_Hooks.cpp`, `hooks/Streamline_Hooks.cpp`/`.h`, `proxies/Ntdll_Proxy.h` (`LdrLockLoaderLock`/`LdrUnlockLoaderLock`). | **Yes, essential** (it replaces the 29 September fork's revert of upstream `f6db41df`). |
| `e7982d30` Save menu changes automatically | As on the 29 September fork (`e135c714`): once the user operates a menu control, the overlay menu saves `OptiScaler.ini` at most every 500 ms and when the menu closes, only when the serialized settings changed. The menu part was re-applied by hand to the restructured `menu_common.cpp`. | No. A convenience. |
| `c28cf7ea` Clang-cl portability fixes for the Linux cross-build | No change in behaviour: `framegen/ffx/FSRFG_Dx12.cpp`, `hooks/Gdi32_Hooks.h`, `hooks/Kernel_Hooks.h`, `inputs/FfxApiExe_Dx12.cpp` (as in `e1efe7ab`) and `inputs/FG/XeFG_Inputs_Dx12.h` (new upstream code: a default member initializer clang-cl refuses inside the class's own static array initializers). | Yes, for this build method. |

Not carried from the 29 September fork:
- `3c232628` (`smallerColor[2] = {}`): upstream has it as `73deae91` (17 October 2026).
- The "XeFG scaling" menu of `e1efe7ab` (`menu/bc250_fg_contract.h`, `menu/bc250_fg_controls.h`): it talks only to the
  multi-frame add-on of earlier private test builds and never draws without it.
- `e1efe7ab`'s `with_dx12/dx11_with_dx12.h` change: upstream replaced that static cache with per-feature caches.

### The deadlock and its fix

Upstream `f6db41df` (26 September 2026) added a mutex per Streamline plugin (`sl.dlss`, `sl.dlss_g`, local
`sl.dlss_g`, `sl.reflex`, `sl.pcl`, `sl.common`). `LibraryLoadHooks::LoadLibraryCheckW` held the plugin's mutex while
it loaded the plugin with `NtdllProxy::LoadLibraryExW_Ldr`, which needs the Windows loader lock.
`LibraryLoadHooks::CheckModulesInMemory` takes the same mutexes, and `LoadLibraryCheckW` calls it for every other DLL;
it runs inside OptiScaler's `LdrLoadDll` hook, so also on a thread that already holds the loader lock (a DLL loaded
from another DLL's initialisation). Thread A then held a plugin mutex and waited for the loader lock, while thread B
held the loader lock and waited for the plugin mutex. CONTROL Resonant (Streamline, DLSS frame generation as
OptiScaler's input, Proton on a BC-250) hung on a black screen at start-up in about half of its starts this way; the
29 September fork reverted `f6db41df`, and 32 of 32 starts then booted on 18 October 2026.

Upstream `4abfd7b6` (4 October 2026) built per-copy hook slots on these mutexes (its header says callers of
`hook*`/`unhook*` must hold them), and master of 19 October still holds them across the loads, so a revert no
longer applies. This fork keeps the slots and the mutexes and fixes the lock order instead:

- `StreamlineHooks::PluginLock` takes the loader lock (`LdrLockLoaderLock`, recursive) first and the plugin mutex
  second. Every hook path uses it, so a plugin mutex is only ever held by a thread that also holds the loader lock,
  and no thread waits for the loader lock while it holds a plugin mutex. Hooking needs the loader lock anyway
  (`GetProcAddress`, `GetModuleFileNameW`).
- `LoadLibraryCheckW` loads the plugin first, without any lock, and hooks it afterwards under a `PluginLock`.
  `hookPlugin` skips a module that already has a slot, so two threads loading the same plugin still hook it once.
- `CheckModulesInMemory` tries `PluginLock`s without waiting, preserving upstream's October 25 census behavior.
- `StreamlineHooks::onModuleFreed` tries both locks and skips the round when either is busy, as its `try_lock` did.
- Without `LdrLockLoaderLock` in ntdll, `PluginLock` falls back to the plugin mutex alone (upstream's behaviour).
- The plugin hooks in `dllmain.cpp` (`CheckWorkingMode`, run from `DLL_PROCESS_ATTACH`, so under the loader lock)
  are upstream's, unchanged.

This is reasoned from the source. FreeFG's README (Status) records how this build was checked in games.

## Building

The build runs on Linux and cross-compiles with LLVM's MSVC-compatible tools against Microsoft's headers and
libraries. `tools/bc250-build.py` reads the compile and link settings from `OptiScaler/OptiScaler.vcxproj`
(Release|x64), writes a ninja file and runs it; the source checkout is not written. Its header comment lists every
option.

You need:
- Linux x86-64 with git, Python 3.9 or later and ninja.
- LLVM's `clang-cl`, `lld-link` and `llvm-rc`: LLVM 23.1.3 for this candidate, and ninja 1.13.2. The previous
  `f971ed14` build used LLVM 22.1.8; the candidate's build record records the current compiler.
- The MSVC 14.44 headers and libraries, ATL and the Windows SDK 10.0.26100, installed with
  [msvc-wine](https://github.com/mstorsjo/msvc-wine). Downloading them means accepting Microsoft's licence terms.
  The reference installation: msvc-wine commit `514f8ea34842cd6d831804d0e9658d3a32870ae1`, the Visual Studio
  17.14.41 (September 2026) channel manifest (17,954,732 bytes, sha256
  `f0a50ea157222c29abd5ea6ff01bfc3c33b04e011c5e45ee2ca38ef0778e5643`), 95 packages: MSVC toolset folder 14.44.35207
  (CRT headers 14.44.35220, ATL 14.44.35208) and `Win11SDK_10.0.26100` 10.0.26100.15.

```sh
git clone https://github.com/mstorsjo/msvc-wine
cd msvc-wine
git checkout 514f8ea34842cd6d831804d0e9658d3a32870ae1
# Without --manifest, vsdownload.py fetches the current manifest. This msvc-wine commit defaults to Visual Studio 18,
# so --major 17 is needed. --save-manifest keeps the manifest it used.
python3 vsdownload.py --major 17 --save-manifest --accept-license --architecture x64 --with-default no \
  --with-msvc yes --with-sdk yes --with-atl yes --dest "$MSVC_ROOT" --cache "$MSVC_CACHE"
./install.sh "$MSVC_ROOT"
```

A Visual Studio 17.14 servicing release newer than 17.14.41 can bring newer CRT or STL headers, and then the DLL's
bytes can differ. With the reference manifest, pass `--manifest FILE` instead of `--major 17 --save-manifest`.

Then, in a checkout of this branch with its submodules:

```sh
git submodule update --init
MSVC_ROOT=/path/to/msvc python3 tools/bc250-build.py --out ../optiscaler-build --jobs 4
```

- The DLL is `../optiscaler-build/OptiScaler.dll`; `bc250-build-record.json` beside it has its sha256, the source
  commit, the version label, `dirty` (whether the checkout had local changes) and the tool versions. `llvm-rc` has
  no `--version` option, so the script starts it under the name `llvm-windres`, which reports its LLVM version.
  Records up to `273e8d44` hold llvm-rc's usage message there instead.
- The output directory must be outside the checkout.
- Instead of `MSVC_ROOT`, `MSVC_INCLUDE` and `MSVC_LIB` can name the header and library directories; `CLANG_CL`,
  `LLD_LINK`, `LLVM_RC` and `NINJA` can name the tools.
- The version string names the checkout's HEAD commit, followed by the first 8 hex digits of the sha256 of its local
  changes (`git diff --binary HEAD`) when there are any. Builds up to `273e8d44` appended a digest to a clean
  checkout's label too: `e3b0c442`, the sha256 of no input; their tags keep the script that made them. A build of
  this commit, rather than of the build commit named above, has a different version string and a different sha256.
- `python3 tools/test-build-record.py` checks the label and the llvm-rc probe (no build).
- Build from a checkout with Unix line endings (git's default on Linux). A checkout with `core.autocrlf=true` changes
  the sources' bytes and can change the DLL.
- The reference build took about six minutes with four jobs.


## Reproducing this build

```sh
git clone https://github.com/daniel-h-0/OptiScaler optiscaler-bc250
cd optiscaler-bc250
git checkout bc250-03db4f8                  # this file and tools/
cp tools/bc250-build.py ../bc250-build.py
git checkout --detach 03db4f8692878e65748769ebe583c053cae96360
git submodule update --init
git status --porcelain                      # must print nothing
MSVC_ROOT=/path/to/msvc python3 ../bc250-build.py --out ../build-b3602882 --jobs 8 \
  --expect-sha256 b3602882c7e194af523e50861a222d63c0c56b013cff4bfb5b187ca4f6666656
```

The candidate was built on 25 October 2026 with LLVM 23.1.3, msvc-wine 514f8ea3, MSVC 14.44.35207 and SDK
10.0.26100.0. The build record identifies the compiler, source commit, empty source patch and resulting DLL hash.

## Submodules

These are the submodules pinned by upstream `08e13adf`. The October 25 merge updates Vulkan-Headers;
the other eight pins are unchanged from the preceding FreeFG build. The corresponding source archive records
the exact commits and trees and includes the redistributable source.

| Path | Repository | Commit |
| --- | --- | --- |
| `external/FidelityFX-SDK` | https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK | `c6efa6bf7f2027b3ec94f28578bb5965eabb9e55` |
| `external/FidelityFX-SDK-v2` | https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK | `60f4ea81909200d8542eca14dccb2628b763a9a3` (v2.3.0) |
| `external/magic_enum` | https://github.com/Neargye/magic_enum | `a733a2ea665ca5d72b7270f0334bf2e7b82bd0cc` |
| `external/nvapi` | https://github.com/NVIDIA/nvapi | `9b181ea572f680327fe01a14a0f1f41c78034104` |
| `external/simpleini` | https://github.com/brofield/simpleini | `6048871ea9ee0ec24be5bd099d161a10567d7dc2` |
| `external/spdlog` | https://github.com/gabime/spdlog | `faa0a7a9c5a3550ed5461fab7d8e31c37fd1a2ef` |
| `external/unordered_dense` | https://github.com/martinus/unordered_dense | `73f3cbb237e84d483afafc743f1f14ec53e12314` |
| `external/vulkan` | https://github.com/KhronosGroup/Vulkan-Headers | `8864cdc896bbc2a9b6eb36b3218fc9ef57908d77` |
| `external/xess` | https://github.com/intel/xess | `8fe81bdbbaf00b3c1b733fd0d830c333dc84e6f0` |

The build reads headers from these submodules and links static libraries that the OptiScaler tree itself carries.


## Upstream status (25 October 2026)

`nightly-20261025` was published at 09:02 UTC. Its notes list `539c9a1e`, but the shipped DLL identifies the later
FPS-overlay merge `08e13adf`; this fork includes that actual build commit. Its support DLLs and licence files match
the previous dependency pins; its OptiScaler DLL and default INI changed. The earlier `bc250-7bc8f8d` candidate
merged only the notes' commit and remains available for reproducibility. FreeFG's measurements document records
the tested game routes.
