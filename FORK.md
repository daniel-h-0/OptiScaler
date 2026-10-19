# BC-250 fork of OptiScaler (rebase on master of 19 October 2026)

This branch is [OptiScaler](https://github.com/optiscaler/OptiScaler) master as of 19 October 2026 (upstream commit
`c2e44a8bc911010d7ed3e4fa63843185fbb55d03`, 13:19 UTC): the nightly of 19 October (`1db5042a`) plus Dynamic MFG for the
XeFG output (pull request #1220: `b7536f77`, `071bb0a6`, `b35346e9`) and `c2e44a8b`. No published nightly is built from
it yet; the first nightly with these commits is due on 20 October 2026. It carries three commits for
[FreeFG](https://github.com/daniel-h-0/freefg), a frame-generation accelerator for the AMD BC-250 under Proton.
FreeFG's packages ship an `OptiScaler.dll` built from commit `f971ed14` of this branch, from FreeFG 1.0.0 on. It
replaces the build of 29 September 2026 (`244eca5c…`, tag `bc250-a793287`).

| | |
| --- | --- |
| File | `OptiScaler.dll` (`opti/OptiScaler.dll` in FreeFG's packages), 28,930,560 bytes |
| sha256 | `5e570dff6299866c508b60634d0dcfc5a53975840888f2aa5e69ba31c3819da6` |
| Version string | `OptiScaler v10.0.0-dev (f971ed143de0-bc250-e3b0c442) (BC250 private)` |
| Source | commit `f971ed143de0bdbbbac6d526c95a20227c22e1c6` (tree `5dce4c9aa75e1a8216de75ef41e330f9daff806a`) and the nine submodules at the commits it records |
| Tag | `bc250-f971ed1`, on a commit after `f971ed14` that adds only this file and `tools/bc250-build.py`: the build commit plus its documentation and build script |
| Built | 19 October 2026 on Linux with clang-cl and lld-link, by `tools/bc250-build.py`, twice, with the same bytes |

The version string's last field is fixed text that the build script writes in place of a build date, so that
rebuilding gives the same bytes. It does not mean that the source is private.

This is not an official OptiScaler or OptiScaler Client release, and the OptiScaler project does not support it.
Report problems with this build to FreeFG (https://github.com/daniel-h-0/freefg), not to OptiScaler.

## Licence

OptiScaler is licensed under the GNU General Public License version 3 (`LICENSE`, unchanged from upstream). This fork,
including the changes below, is distributed under the same licence. `tools/bc250-build.py` carries an MIT licence
header; MIT is compatible with the GPL, and it is distributed here as part of the GPL-3.0 work. There is no warranty,
to the extent permitted by applicable law (GPL-3.0 sections 15 and 16).

## The three commits

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
- `CheckModulesInMemory` takes `PluginLock`s instead of plain mutex locks.
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
- LLVM's `clang-cl`, `lld-link` and `llvm-rc`. The reference build used LLVM 22.1.8: Arch Linux packages
  `clang 22.1.8-1`, `lld 22.1.8-1` and `llvm 22.1.8-2` (the Arch Linux Archive snapshot of 3 September 2026 has
  clang, lld and llvm-libs at these versions), and `ninja 1.13.2-3`.
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
  commit, the version label and the tool versions. `llvm-rc` has no `--version` option, so its entry there holds
  llvm-rc's usage message instead; it comes from the same LLVM release as `clang-cl`.
- The output directory must be outside the checkout.
- Instead of `MSVC_ROOT`, `MSVC_INCLUDE` and `MSVC_LIB` can name the header and library directories; `CLANG_CL`,
  `LLD_LINK`, `LLVM_RC` and `NINJA` can name the tools.
- The version string names the checkout's HEAD commit and a hash of its local changes (`git diff --binary HEAD`), so a
  build of this commit, rather than of the build commit named above, has a different version string and a different sha256.
- Build from a checkout with Unix line endings (git's default on Linux). A checkout with `core.autocrlf=true` changes
  the sources' bytes and can change the DLL.
- The reference build took about six minutes with four jobs.


## Reproducing this build

```sh
git clone https://github.com/daniel-h-0/OptiScaler optiscaler-bc250
cd optiscaler-bc250
git checkout bc250-f971ed1                  # this file and tools/
cp tools/bc250-build.py ../bc250-build.py
git checkout --detach f971ed143de0bdbbbac6d526c95a20227c22e1c6
git submodule update --init
git status --porcelain                      # must print nothing
MSVC_ROOT=/path/to/msvc python3 ../bc250-build.py --out ../build-5e570dff --jobs 4 \
  --expect-sha256 5e570dff6299866c508b60634d0dcfc5a53975840888f2aa5e69ba31c3819da6
```

Checked on 19 October 2026: these steps built `5e570dff…` twice, into two directories, with the same bytes (LLVM
22.1.8, msvc-wine 514f8ea3 with MSVC 14.44.35207 and SDK 10.0.26100.0, the reference installation above). The DLL
holds no file system path of the machine it was built on (string scan).

## Submodules

Unchanged from upstream `92337ebf` (nightly of 29 September 2026) to `c2e44a8b`. Each commit exists in its public repository (checked 18 October 2026, and again
on 19 October 2026 by fetching each commit from the repository below).

| Path | Repository | Commit |
| --- | --- | --- |
| `external/FidelityFX-SDK` | https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK | `c6efa6bf7f2027b3ec94f28578bb5965eabb9e55` |
| `external/FidelityFX-SDK-v2` | https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK | `60f4ea81909200d8542eca14dccb2628b763a9a3` (v2.3.0) |
| `external/magic_enum` | https://github.com/Neargye/magic_enum | `a733a2ea665ca5d72b7270f0334bf2e7b82bd0cc` |
| `external/nvapi` | https://github.com/NVIDIA/nvapi | `9b181ea572f680327fe01a14a0f1f41c78034104` |
| `external/simpleini` | https://github.com/brofield/simpleini | `6048871ea9ee0ec24be5bd099d161a10567d7dc2` |
| `external/spdlog` | https://github.com/gabime/spdlog | `faa0a7a9c5a3550ed5461fab7d8e31c37fd1a2ef` |
| `external/unordered_dense` | https://github.com/martinus/unordered_dense | `73f3cbb237e84d483afafc743f1f14ec53e12314` |
| `external/vulkan` | https://github.com/KhronosGroup/Vulkan-Headers | `d64e9e156ac818c19b722ca142230b68e3daafe3` |
| `external/xess` | https://github.com/intel/xess | `8fe81bdbbaf00b3c1b733fd0d830c333dc84e6f0` |

The build reads headers from these submodules and links static libraries that the OptiScaler tree itself carries.


## Upstream status (19 October 2026)

- `nightly-20261019` (published 09:40 UTC) is master `1db5042a`; the nightly workflow builds master as it stands at
  its run (scheduled 04:00 UTC). This branch's base `c2e44a8b` is master at 13:19 UTC; a nightly of 20 October built
  from a later master would carry more commits.
