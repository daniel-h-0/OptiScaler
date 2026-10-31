#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cross-build OptiScaler.dll on Linux with clang-cl, lld-link and llvm-rc against the MSVC and Windows SDK
headers and libraries, the way the BC-250 fork's shipped DLL was built (see FORK.md).

The compile and link lines come from OptiScaler/OptiScaler.vcxproj (Release|x64): its include and library
paths, preprocessor definitions, precompiled-header modes, excluded files, link dependencies, delay-loaded DLLs
and resource-compiler definitions. The script writes a ninja file and runs it; nothing in the source checkout is
written (ninja's own logs go to the output directory).

Inputs, all from the environment or the command line (no paths are built in):

  --source DIR / OPTISCALER_SOURCE   the fork checkout with its submodules (default: the checkout holding this
                                     script). Its HEAD and local changes name the build: the DLL's version string
                                     reads "<12-digit commit>-bc250" for a clean checkout and, with local changes,
                                     "<12-digit commit>-bc250-<first 8 hex of sha256(git diff --binary HEAD)>".
  --out DIR / BC250_BUILD_OUT        output directory, outside the source (default: <source>-build)
  MSVC_ROOT                          an msvc-wine installation (https://github.com/mstorsjo/msvc-wine): INCLUDE and
                                     LIB are read from $MSVC_ROOT/bin/x64/msvcenv.sh, as msvc-wine's
                                     msvcenv-native.sh does
  MSVC_INCLUDE, MSVC_LIB             instead of MSVC_ROOT: ';'-separated header and library directories, in the
                                     order msvcenv.sh gives them (MSVC atlmfc, MSVC, SDK shared/ucrt/um/winrt/km)
  CLANG_CL, LLD_LINK, LLVM_RC, NINJA tool names or paths (default clang-cl, lld-link, llvm-rc, ninja)

Options: --jobs N (default 2), --configure-only (write build.ninja and commands.json, compile nothing),
--expect-sha256 HEX (exit with status 1 unless the DLL has this sha256).

Outputs in the output directory: OptiScaler.dll, build.ninja, commands.json (every command line),
sdk-vfs.json (case-insensitive header overlay), generated/ (version headers, UTF-8 resource script) and
bc250-build-record.json (source commit, version label, whether the checkout had local changes, toolchain versions,
DLL sha256; no absolute paths).
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {'m': 'http://schemas.microsoft.com/developer/msbuild/2003'}
CONDITION = "'$(Configuration)|$(Platform)'=='Release|x64'"
STANDARD_LIBS = ['kernel32.lib', 'user32.lib', 'gdi32.lib', 'winspool.lib', 'comdlg32.lib', 'advapi32.lib',
                 'shell32.lib', 'ole32.lib', 'oleaut32.lib', 'uuid.lib', 'odbc32.lib', 'odbccp32.lib', 'delayimp.lib']


def fail(message):
    sys.exit('bc250-build: ' + message)


def git(source, *arguments, binary=False):
    out = subprocess.run(['git', '-C', str(source), *arguments], capture_output=True,
                         env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'))
    if out.returncode:
        fail(f'git {" ".join(arguments)} failed: {out.stderr.decode(errors="replace").strip()}')
    return out.stdout if binary else out.stdout.decode().strip()


def msvc_environment():
    """INCLUDE and LIB as ';'-separated Unix paths."""
    root = os.environ.get('MSVC_ROOT')
    if root:
        script = Path(root) / 'bin' / 'x64' / 'msvcenv.sh'
        if not script.is_file():
            fail(f'MSVC_ROOT has no bin/x64/msvcenv.sh: {root}')
        raw = subprocess.check_output(['bash', '-c', '. "$1" >/dev/null && printf "%s\\0%s" "$INCLUDE" "$LIB"', '_',
                                       str(script)])
        include, lib = raw.decode().split('\0')
        # msvcenv-native.sh: drop the Wine drive letter and turn backslashes into slashes
        unix = lambda value: value.replace('z:', '').replace('\\', '/')
        return unix(include), unix(lib)
    if os.environ.get('MSVC_INCLUDE') and os.environ.get('MSVC_LIB'):
        return os.environ['MSVC_INCLUDE'], os.environ['MSVC_LIB']
    fail('set MSVC_ROOT (an msvc-wine installation) or both MSVC_INCLUDE and MSVC_LIB')


def tool_version(command):
    try:
        out = subprocess.run([command, '--version'], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        return f'unavailable ({error.__class__.__name__})'
    lines = [line.strip() for line in (out.stdout or out.stderr).splitlines() if line.strip()]
    return lines[0] if lines else 'unknown'


def llvm_rc_version(command):
    """llvm-rc has no version option: it takes --version for an input file name. The same program started under
    the name llvm-windres (llvm-rc picks its mode from argv[0]) answers --version with its LLVM version."""
    path = shutil.which(command)
    if path is None:
        return 'unavailable (not found)'
    try:
        out = subprocess.run(['llvm-windres', '--version'], executable=path, capture_output=True, text=True,
                             timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        return f'unavailable ({error.__class__.__name__})'
    match = re.search(r'LLVM version (\S+)', out.stdout + out.stderr)
    return 'LLVM version ' + match[1] if match else 'unknown'


def source_label(source):
    """(commit, version label, local changes as `git diff --binary HEAD`, their sha256 or None when there are none).
    The label is the 12-digit commit plus "-bc250", and the changes' first 8 hex digits only when there are any:
    builds before this rule appended e3b0c442, the sha256 of no input, to a clean checkout's label too."""
    commit = git(source, 'rev-parse', 'HEAD')
    revision = git(source, 'rev-parse', '--short=12', 'HEAD')
    patch = git(source, 'diff', '--binary', 'HEAD', binary=True)
    patch_sha256 = hashlib.sha256(patch).hexdigest() if patch else None
    return commit, revision + '-bc250' + ('-' + patch_sha256[:8] if patch else ''), patch, patch_sha256


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--source', default=os.environ.get('OPTISCALER_SOURCE'))
    p.add_argument('--out', default=os.environ.get('BC250_BUILD_OUT'))
    p.add_argument('--jobs', type=int, default=2)
    p.add_argument('--configure-only', action='store_true')
    p.add_argument('--compile-only', action='store_true', help='compile the objects, do not link')
    p.add_argument('--expect-sha256')
    a = p.parse_args()
    if a.jobs < 1:
        fail('--jobs must be at least 1')

    source = Path(a.source or Path(__file__).resolve().parent.parent).resolve()
    project = source / 'OptiScaler'
    if not (project / 'OptiScaler.vcxproj').is_file():
        fail(f'not an OptiScaler checkout (no OptiScaler/OptiScaler.vcxproj): {source}')
    out = Path(a.out or str(source) + '-build').resolve()
    if out == source or source in out.parents:
        fail('the output directory must be outside the source checkout (the header overlay lists the whole source)')
    out.mkdir(parents=True, exist_ok=True)
    generated = out / 'generated'
    generated.mkdir(exist_ok=True)
    tools = {name: os.environ.get(env, default) for name, env, default in
             [('clang-cl', 'CLANG_CL', 'clang-cl'), ('lld-link', 'LLD_LINK', 'lld-link'),
              ('llvm-rc', 'LLVM_RC', 'llvm-rc'), ('ninja', 'NINJA', 'ninja')]}

    commit, label, patch, patch_sha256 = source_label(source)
    untracked = [line[3:] for line in git(source, 'status', '--porcelain', '--untracked-files=normal').splitlines()
                 if line.startswith('?? ')]
    generated_files = []
    for name, value in [('resource_build_date.h', '#define VER_BUILD_DATE "BC250 private"\n'),
                        ('resource_build_commit.h', '#define VER_BUILD_COMMIT "' + label + '"\n')]:
        file = generated / name
        if not file.exists() or file.read_bytes() != value.encode():
            file.write_bytes(value.encode())
        generated_files.append(file)
    (out / 'source.patch').write_bytes(patch)

    include_env, lib_env = msvc_environment()
    env = dict(os.environ, INCLUDE=include_env, LIB=lib_env)
    include_dirs = [v for v in include_env.split(';') if v]
    lib_dirs = [v for v in lib_env.split(';') if v]

    # Windows looks headers up case-insensitively: a clang VFS overlay of every header directory and the source
    # (without .git) maps any spelling to the real file, so neither the SDK nor the source needs editing.
    def directory(path):
        contents = []
        seen = {}
        for child in sorted(path.iterdir()):
            if child.name == '.git':
                continue
            folded = child.name.lower()
            if folded in seen:
                if child.resolve() != seen[folded].resolve():
                    fail(f'case collision in a header directory: {child}')
                continue
            seen[folded] = child
            if child.is_dir():
                contents.append(dict(type='directory', name=child.name, contents=directory(child)))
            elif child.is_file():
                contents.append(dict(type='file', name=child.name, **{'external-contents': str(child)}))
        return contents

    roots = [dict(type='directory', name=v, contents=directory(Path(v)))
             for v in [*include_dirs, str(source)] if Path(v).is_dir()]
    overlay = out / 'sdk-vfs.json'
    overlay_text = json.dumps(dict(version=0, **{'case-sensitive': False, 'roots': roots})) + '\n'
    if not overlay.exists() or overlay.read_bytes() != overlay_text.encode():
        overlay.write_bytes(overlay_text.encode())

    # Some sources ask the linker for "Version.lib"; msvc-wine installs it as Version.Lib with a lowercase link.
    # A link under the output directory, searched after every SDK directory, answers that spelling.
    lib_case = out / 'lib-case'
    lib_case.mkdir(exist_ok=True)
    if not any((Path(d) / 'Version.lib').exists() for d in lib_dirs):
        target = next((Path(d) / n for d in lib_dirs if Path(d).is_dir() for n in os.listdir(d)
                       if n.lower() == 'version.lib'), None)
        if target is None:
            fail('no version.lib in the library directories')
        link_name = lib_case / 'Version.lib'
        if link_name.is_symlink() or link_name.exists():
            link_name.unlink()
        link_name.symlink_to(target)
        env['LIB'] = lib_env + ';' + str(lib_case)

    tree = ET.parse(project / 'OptiScaler.vcxproj')
    props = next(g for g in tree.findall('m:PropertyGroup', NS)
                 if g.attrib.get('Condition') == CONDITION and g.find('m:IncludePath', NS) is not None)
    defs = next(g for g in tree.findall('m:ItemDefinitionGroup', NS) if g.attrib.get('Condition') == CONDITION)

    def paths(value):
        value = value.replace('$(ProjectDir)', str(project) + '/').replace('$(SolutionDir)', str(source) + '/')
        return [v for v in value.replace('\\', '/').split(';') if v and '$(' not in v]

    includes = [str(generated), *paths(props.find('m:IncludePath', NS).text)]
    libraries = paths(props.find('m:LibraryPath', NS).text)
    macros = [v for v in defs.find('m:ClCompile/m:PreprocessorDefinitions', NS).text.split(';') if v and '%(' not in v]
    base = [tools['clang-cl'], '/nologo', '/std:c++latest', '/EHsc', '/MD', '/O2', '/fp:fast', '/D_UNICODE',
            '/DUNICODE', *['/D' + v for v in macros], *['/I' + v for v in includes], '/clang:-ivfsoverlay',
            '/clang:' + str(overlay), '-Wno-microsoft-string-literal-from-predefined']
    pch = out / 'opti.pch'
    rules = ['builddir = ' + str(out).replace('$', '$$').replace(' ', '$ ').replace(':', '$:'),
             'rule cc', '  command = $compile_command > $out.log 2>&1', '  description = CC $in', '  deps = gcc',
             '  depfile = $out.d',
             'rule rc', '  command = $compile_command > $out.log 2>&1', '  description = RC $in',
             'rule link', '  command = $compile_command > $out.log 2>&1', '  description = LINK $out']
    objects = []
    commands = []

    def ninja_path(path):
        return str(path).replace('$', '$$').replace(' ', '$ ').replace(':', '$:')

    def emit(target, inputs, command, dependencies=(), rule='cc'):
        rules.append('build ' + ninja_path(target) + ': ' + rule + ' ' + ' '.join(ninja_path(v) for v in inputs) +
                     (' | ' + ' '.join(ninja_path(v) for v in dependencies) if dependencies else ''))
        rules.append('  compile_command = ' + shlex.join(command).replace('$', '$$'))
        commands.append(dict(output=str(target), argv=command))

    for item in tree.findall('.//m:ClCompile[@Include]', NS):
        if any(v.text == 'true' and v.attrib.get('Condition') in (None, CONDITION)
               for v in item.findall('m:ExcludedFromBuild', NS)):
            continue
        relative = item.attrib['Include'].replace('\\', '/')
        f = project / relative
        target = out / (relative.replace('/', '__') + '.obj')
        mode = next((v.text for v in item.findall('m:PrecompiledHeader', NS) if v.attrib.get('Condition') == CONDITION),
                    'Use')
        is_c = f.suffix.lower() == '.c'
        cmd = base + ['/c', str(f), '/Fo' + str(target), '/clang:-MD', '/clang:-MF', '/clang:' + str(target) + '.d']
        dependencies = []
        if mode == 'Create':
            cmd += ['/Ycpch.h', '/Fp' + str(pch)]
        elif mode != 'NotUsing' and not is_c:
            cmd += ['/Yupch.h', '/Fp' + str(pch)]
            dependencies = [out / 'pch.cpp.obj']
        if is_c:
            cmd = [v for v in cmd if not v.startswith(('/std:', '/EH'))]
        emit(target, [f], cmd, [overlay, *dependencies])
        objects.append(target)

    # Resource script: llvm-rc reads UTF-8, the project's script is UTF-16; same text, line endings kept
    resource = out / 'OptiScaler.res'
    resource_includes = includes + include_dirs
    resource_source = generated / 'OptiScaler.rc'
    original_resource = (project / 'OptiScaler.rc').read_bytes()
    resource_bytes = original_resource.decode(
        'utf-16' if original_resource.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8').encode('utf-8')
    if not resource_source.exists() or resource_source.read_bytes() != resource_bytes:
        resource_source.write_bytes(resource_bytes)
    rc_defines = [e for e in [defs.find('m:ResourceCompile/m:PreprocessorDefinitions', NS),
                              *tree.findall('m:ItemGroup/m:ResourceCompile/m:PreprocessorDefinitions', NS)]
                  if e is not None and e.text]
    rc_defines = list(dict.fromkeys(v for e in rc_defines for v in e.text.split(';') if v and '%(' not in v))
    emit(resource, [resource_source],
         [tools['llvm-rc'], '/c', '65001', *['/D' + v for v in rc_defines], '/fo', str(resource),
          *['/I' + v for v in resource_includes if v], str(resource_source)],
         generated_files + [project / 'OptiScaler.rc'], rule='rc')

    dependencies = [v.lower() for v in defs.find('m:Link/m:AdditionalDependencies', NS).text.split(';')
                    if v and '%(' not in v]
    delayed = defs.find('m:Link/m:DelayLoadDLLs', NS).text.split(';')
    dll = out / 'OptiScaler.dll'
    link = [tools['lld-link'], '/dll', '/machine:x64', '/subsystem:windows', '/opt:ref', '/opt:icf', '/timestamp:0',
            '/ignore:4099', '/out:' + str(dll), '/def:' + str(project / 'Source.def'),
            *['/libpath:' + v for v in libraries], *['/delayload:' + v for v in delayed], *[str(v) for v in objects],
            str(resource), *dependencies, *STANDARD_LIBS]
    emit(dll, [*objects, resource], link, rule='link')
    rules += ['build compile: phony ' + ' '.join(ninja_path(v) for v in [*objects, resource]),
              'default ' + ninja_path(dll)]
    (out / 'build.ninja').write_bytes(('\n'.join(rules) + '\n').encode())
    (out / 'commands.json').write_bytes((json.dumps(dict(source_commit=commit, commands=commands,
                                                         environment={k: env[k] for k in ['INCLUDE', 'LIB']}),
                                                    indent=2) + '\n').encode())
    print(f'source {commit} ({label}), {len(objects)} objects; build files in {out}')
    if untracked:
        print(f'note: {len(untracked)} untracked path(s) in the source (not part of the version label): '
              + ', '.join(untracked[:5]))
    if a.configure_only:
        return

    subprocess.run([tools['ninja'], '-f', str(out / 'build.ninja'), '-j', str(a.jobs),
                    *(['compile'] if a.compile_only else [])], cwd=project, env=env, check=True)
    if a.compile_only:
        return

    digest = hashlib.sha256(dll.read_bytes()).hexdigest()
    version_dirs = ';'.join(include_dirs)
    msvc_version = re.search(r'/msvc/(\d+\.\d+\.\d+)/', version_dirs, re.I)
    sdk_version = re.search(r'/include/(10\.\d+\.\d+\.\d+)/', version_dirs, re.I)
    record = dict(
        dll='OptiScaler.dll', dll_sha256=digest, dll_bytes=dll.stat().st_size,
        source_commit=commit, version_label=label, dirty=bool(patch), source_patch_sha256=patch_sha256,
        untracked_source_paths=untracked,
        toolchain={name: llvm_rc_version(command) if name == 'llvm-rc' else tool_version(command)
                   for name, command in tools.items()},
        msvc_version=msvc_version.group(1) if msvc_version else None,
        windows_sdk_version=sdk_version.group(1) if sdk_version else None,
        expected_sha256=a.expect_sha256, matches_expected=(digest == a.expect_sha256.lower()) if a.expect_sha256 else None)
    (out / 'bc250-build-record.json').write_bytes((json.dumps(record, indent=2) + '\n').encode())
    print(f'OptiScaler.dll sha256 {digest}')
    if a.expect_sha256 and digest != a.expect_sha256.lower():
        fail(f'sha256 differs from the expected {a.expect_sha256}')


if __name__ == '__main__':
    main()
