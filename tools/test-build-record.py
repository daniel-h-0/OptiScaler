#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check bc250-build.py's build record: the version label of a clean and a changed checkout, and llvm-rc's version
probe (llvm-rc reads --version as an input file name; started as llvm-windres it reports its LLVM version).

Uses a temporary git repository and a compiled stand-in for llvm-rc that, like the real one, decides by argv[0];
the installed llvm-rc is probed too when present. Builds nothing.
"""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

FAKE_RC = r'''
#include <stdio.h>
#include <string.h>
int main(int argc, char** argv) {
    const char* name = strrchr(argv[0], '/') ? strrchr(argv[0], '/') + 1 : argv[0];
    size_t n = strlen(name);
    if (WINDRES && n >= 7 && strcmp(name + n - 7, "windres") == 0 && argc > 1 && strcmp(argv[1], "--version") == 0) {
        puts("llvm-windres, compatible with GNU windres\nLLVM (http://llvm.org/):\n  LLVM version 99.1.2");
        return 0;
    }
    puts("Exactly one input file should be provided.");
    return 0;
}
'''


def main():
    spec = importlib.util.spec_from_file_location('bc250_build', Path(__file__).resolve().parent / 'bc250-build.py')
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    failures = []
    checks = 0

    def check(condition, what):
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(what)
            print('FAIL ' + what)

    with tempfile.TemporaryDirectory(prefix='opti-build-record-') as directory:
        root = Path(directory)
        repo = root / 'repo'
        repo.mkdir()
        env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid', GIT_COMMITTER_NAME='t',
                   GIT_COMMITTER_EMAIL='t@example.invalid', GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        git = lambda *arguments: subprocess.run(['git', '-C', str(repo), *arguments], env=env, check=True,
                                                capture_output=True, text=True).stdout.strip()
        git('init', '-q')
        (repo / 'a.cpp').write_text('int a;\n')
        git('add', 'a.cpp')
        git('commit', '-q', '-m', 'a')
        commit = git('rev-parse', 'HEAD')

        clean = build.source_label(repo)
        check(clean == (commit, commit[:12] + '-bc250', b'', None), 'clean checkout: commit label, no digest')
        (repo / 'notes.txt').write_text('untracked\n')
        check(build.source_label(repo)[1:] == clean[1:], 'an untracked file leaves the label alone')
        (repo / 'a.cpp').write_text('int a = 1;\n')
        _, label, patch, digest = build.source_label(repo)
        check(patch and digest == hashlib.sha256(patch).hexdigest(), 'changed checkout: digest of its diff')
        check(label == commit[:12] + '-bc250-' + digest[:8], 'changed checkout: label carries the digest')

        compiler = shutil.which(os.environ.get('CC', 'cc')) or shutil.which('clang')
        for windres, expected in [(1, 'LLVM version 99.1.2'), (0, 'unknown')]:
            program = root / f'llvm-rc-{windres}'
            (root / 'fake.c').write_text(FAKE_RC)
            subprocess.run([compiler, f'-DWINDRES={windres}', str(root / 'fake.c'), '-o', str(program)], check=True)
            check(build.llvm_rc_version(str(program)) == expected,
                  f'llvm-rc stand-in {"with" if windres else "without"} a windres mode: {expected}')
            check(build.tool_version(str(program)) == 'Exactly one input file should be provided.',
                  'the plain --version probe gets the usage error (why llvm-rc needs its own probe)')
        check(build.llvm_rc_version(str(root / 'missing-llvm-rc')) == 'unavailable (not found)', 'missing tool')
        if shutil.which('llvm-rc'):
            check(build.llvm_rc_version('llvm-rc').startswith('LLVM version '), 'installed llvm-rc reports a version')

    print(f'{checks} build-record checks: {"FAIL" if failures else "PASS"}')
    raise SystemExit(1 if failures else 0)


if __name__ == '__main__':
    main()
