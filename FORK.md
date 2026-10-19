# BC-250 fork of OptiScaler

This branch is [OptiScaler](https://github.com/optiscaler/OptiScaler) at its nightly of 29 September 2026 (upstream
commit `92337ebfbf07d533eabe3731fd8de1bb19437aea`) with four commits for FreeFG, a frame-generation accelerator for
the AMD BC-250 under Proton. FreeFG's packages ship an `OptiScaler.dll` built from commit `a7932870` of this branch:

| | |
| --- | --- |
| File | `OptiScaler.dll` (`opti/OptiScaler.dll` in FreeFG's packages), 27,790,848 bytes |
| sha256 | `244eca5c0927dff802d7f2a506afe9e7776bcdc489bdc3acdf56e9c92f7b437d` |
| Version string | `OptiScaler v10.0.0-dev (a7932870f998-bc250-e3b0c442) (BC250 private)` |
| Source | commit `a7932870f9988b86692aabf9e8908e2adc61e1f0` (tree `74d774430e56919ab2246476004ed43b731d259f`) and the nine submodules at the commits it records |
| Tag | `bc250-a793287`, on a commit after `a7932870` that adds only this file and `tools/bc250-build.py`: the build commit plus its documentation and build script |
| Built | 18 October 2026 on Linux with clang-cl and lld-link, by `tools/bc250-build.py` |

The version string's last field is fixed text that the build script writes in place of a build date, so that
rebuilding gives the same bytes. It does not mean that the source is private.

This is not an official OptiScaler or OptiScaler Client release, and the OptiScaler project does not support it.
Report problems with this build to FreeFG (https://github.com/daniel-h-0/freefg), not to OptiScaler.

## Licence

OptiScaler is licensed under the GNU General Public License version 3 (`LICENSE`, unchanged from upstream). This fork,
including the changes below, is distributed under the same licence. The changes were made between 22 and 29 September
2026 (each commit carries its date); this file and `tools/bc250-build.py` were added on 18 October 2026, and this file
was updated on 19 October 2026.

Three files of this fork carry an MIT licence header: `OptiScaler/menu/bc250_fg_contract.h`,
`OptiScaler/menu/bc250_fg_controls.h` and `tools/bc250-build.py`. MIT is compatible with the GPL, and they are
distributed here as part of the GPL-3.0 work.

There is no warranty, to the extent permitted by applicable law (GPL-3.0 sections 15 and 16).

## The four commits

| Commit | What it changes | Needed by FreeFG's 2× build |
| --- | --- | --- |
| `a7932870` Revert "Try to prevent race conditions when hooking sl plugins" | Reverts upstream `f6db41df` (26 September 2026). `OptiScaler/hooks/LibraryLoad_Hooks.cpp` returns, byte for byte, to its content before that commit; `OptiScaler/hooks/Streamline_Hooks.h` loses only the six plugin mutex declarations. | **Yes, essential** (see below). |
| `e135c714` Save menu changes automatically | Once the user operates a menu control, the overlay menu saves `OptiScaler.ini` the way Save Settings does: at most every 500 ms and when the menu closes, and only when the serialized settings differ from the last saved ones. Values changed by runtime code while nobody touches the menu are not written. Save Settings still writes unconditionally; a failed write is logged, shown in the menu footer and retried after the next change. | No. A convenience: without it, menu changes last only until the game exits unless the user presses Save Settings. |
| `3c232628` Initialize optional FFX downscaled color resources before cleanup | `OptiScaler/upscalers/ffx/FFXFeature_Dx12.h`: `ID3D12Resource* smallerColor[2] = {};`. The cleanup releases both pointers, also when the optional resources were never created. | A bug fix, not specific to FreeFG. Upstream made the same change in `73deae91` (17 October 2026). |
| `e1efe7ab` Add private XeFG scaling controls and local Clang portability fixes | (a) A menu section, "XeFG scaling", in `OptiScaler/menu/bc250_fg_contract.h`, `bc250_fg_controls.h` and two lines of `menu_common.cpp`. It talks to a module named `BC250-MFG.asi`, the multi-frame add-on of earlier FreeFG test builds, and returns at once when that module is not loaded. (b) Five source changes so that clang-cl compiles the project, with no change in behaviour: `framegen/ffx/FSRFG_Dx12.cpp` (`_version = feature_version {}`), `hooks/Gdi32_Hooks.h` (the hook is declared before its signature check), `hooks/Kernel_Hooks.h` (`amdxc64Mark` is `static inline HMODULE const` instead of `constexpr`), `inputs/FfxApiExe_Dx12.cpp` (its five hook functions are renamed `ffx…_ExeDx12`), `with_dx12/dx11_with_dx12.h` (`UpscalerResourceCache` is defined after the class). | (a) No: the 2× build has no `BC250-MFG.asi`, so the section never draws. (b) Yes, for this build method. |

### Why the revert

`f6db41df` added a mutex per Streamline plugin (`sl.dlss`, `sl.dlss_g`, local `sl.dlss_g`, `sl.reflex`, `sl.pcl`,
`sl.common`). `LibraryLoadHooks::LoadLibraryCheckW` holds the plugin's mutex while it loads the plugin with
`NtdllProxy::LoadLibraryExW_Ldr`, which needs the Windows loader lock. `LibraryLoadHooks::CheckModulesInMemory` takes
the same mutexes, and `LoadLibraryCheckW` calls it for every DLL it does not handle itself. `LoadLibraryCheckW` runs
inside OptiScaler's `LdrLoadDll` and `NtLoadDll` hooks, so it also runs for a DLL that is loaded while its thread
already holds the loader lock, for example from another DLL's initialisation. Thread A then holds a plugin mutex and
waits for the loader lock, while thread B holds the loader lock and waits for the plugin mutex.

CONTROL Resonant (Streamline with DLSS frame generation as OptiScaler's input, under Proton on a BC-250) hung on a
black screen at start-up in about half of its starts with this fork before the revert (2 of 4, 3 of 6 and about 8 of
14 in three series). The process could not be attached by a debugger, which also needs the loader lock. Thread stacks
read from outside showed the loader lock held by a thread inside a DLL load, waiting on another lock, while the thread
loading a Streamline plugin and thread-pool threads waited for the loader lock. With the revert, 20 of 20 starts
booted (12 with the DLL swapped in, 8 after a fresh install). An OptiScaler build from 4 September 2026, before
`f6db41df`, booted 10 of 10. Without these mutexes the race that `f6db41df` addressed can come back; it was not seen
in these games.

After a CONTROL Resonant update, 32 of 32 starts booted with the shipped `244eca5c` on 18 October 2026. The earlier
series ran with the earlier build of the same source (next section).

## Earlier builds of the same source

FreeFG's private test builds from 29 September to 18 October 2026 carried `OptiScaler.dll` sha256
`777ed1e7745412c944a44ac284fa5e7ad95418d3faf6ed4d72c4ef339aeca98d` (27,790,848 bytes, version string
`OptiScaler v10.0.0-dev (2c103878e906-bc250-e3b0c442) (BC250 private)`), built on 29 September 2026 from commit
`2c103878e90656c3bb56cfdbd4926dd8beb269af`. On 18 October 2026 the four commits were recorded again under the author
address of this repository. Their trees did not change:

| Commit here | Earlier commit | Tree (both) |
| --- | --- | --- |
| `a7932870f9988b86692aabf9e8908e2adc61e1f0` | `2c103878e90656c3bb56cfdbd4926dd8beb269af` | `74d774430e56919ab2246476004ed43b731d259f` |
| `e135c714f9dd49f04b089111f893c91a04b487c4` | `5b4f2df837d853f4d8707050a729ad35385c3b47` | `ec5dcb50d74d348afd10a26bfcc8b38044486dbd` |
| `3c2326288657ad8a18c23a755ed2873fe8b2eead` | `1e3a7e15aa5c6a27a48f920204a65ab22fe293b0` | `7206ef17764365e9d9c8e62bcaeb4a41d682ea68` |
| `e1efe7ab85f1b65107f76aaed45094c03ee5d0f0` | `de4c0b35d50cde35263d5ca814bc8aa034cd7fb1` | `b91d95006770a90acf9c4410a3ce77e696904961` |

The DLL embeds the first 12 digits of its source commit in its version string, so a build of `a7932870` differs from
`777ed1e7…` there and nowhere else: both files are 27,790,848 bytes, and the 18 bytes that differ all lie inside those
12 digits, which the DLL holds twice (as text in `.rdata` and in the UTF-16 version resource in `.rsrc`). The earlier
commits are not part of this repository; their source is the tree above.

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
  build of this commit, rather than of `a7932870`, has a different version string and a different sha256.
- Build from a checkout with Unix line endings (git's default on Linux). A checkout with `core.autocrlf=true` changes
  the sources' bytes and can change the DLL.
- The reference build took about six minutes with four jobs.

## Reproducing the shipped DLL

```sh
git clone https://github.com/daniel-h-0/OptiScaler optiscaler-bc250
cd optiscaler-bc250
git checkout bc250-a793287                  # this file and tools/
cp tools/bc250-build.py ../bc250-build.py
git checkout --detach a7932870f9988b86692aabf9e8908e2adc61e1f0
git submodule update --init
git status --porcelain                      # must print nothing
MSVC_ROOT=/path/to/msvc python3 ../bc250-build.py --out ../build-244eca5c --jobs 4 \
  --expect-sha256 244eca5c0927dff802d7f2a506afe9e7776bcdc489bdc3acdf56e9c92f7b437d
```

The script exits with status 1 if the sha256 differs.

Checked on 18 October 2026:
- **Rebuilt.** On the reference toolchain and msvc-wine installation above, in a clone at a different location from
  the checkout of the 29 September build, these steps built `a7932870` to `244eca5c…` (twice, into two directories,
  with the same bytes). The same steps at the earlier commit `2c103878` (in a local clone that still has it) rebuilt
  the earlier `777ed1e7…` byte for byte, with the same 202 command lines as its 29 September build.
- Without compiling, for the 29 September build of `2c103878` (the same tree as `a7932870`):
  - its recorded local changes were empty (sha256 `e3b0c442…`, the `e3b0c442` in the version string);
  - every source file the compiler read (700 files across the 200 objects, from ninja's dependency log), plus
    `Source.def`, `resource.h`, the resource script and the 14 static libraries linked from the tree, is tracked (in
    this tree or at a submodule's recorded commit), with the same contents;
  - `tools/bc250-build.py --configure-only` writes the same 202 compile, resource and link command lines as that
    build, apart from the checkout and output directories, and the same version headers and resource script.
- The DLL holds no file system path of the machine it was built on (string scan), so the checkout's location does not
  matter.

## Submodules

Unchanged from upstream `92337ebf`. Each commit exists in its public repository (checked 18 October 2026, and again
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

## Upstream status (18 October 2026)

- The newest nightly is `nightly-20261018`, from master `babf1d6c`, 110 commits after this fork's base.
- Master still holds the plugin mutexes across the plugin loads in `OptiScaler/hooks/LibraryLoad_Hooks.cpp` (locks at
  lines 168, 188–189, 214, 234 and 254, loads at lines 170, 191, 216, 236 and 256). It takes the same mutexes in
  `CheckModulesInMemory()` (lines 1038, 1053–1054, 1082, 1106 and 1129), which `LoadLibraryCheckW` calls at line 627;
  `OptiScaler/hooks/Ntdll_Hooks.h` calls `LoadLibraryCheckW` from the loader hooks at lines 79 and 146. A rebase still
  needs the revert or another fix. This is read from the source; a current nightly was not tested.
- `3c232628` is in master as `73deae91`.
- The clang changes of `e1efe7ab` are not in master in this form (master has clang fixes of its own), so a rebase has
  to check them again.

A rebased build is a different binary. FreeFG pins this DLL by sha256, so a rebased build needs a new tag, a new pin
and its own testing.
