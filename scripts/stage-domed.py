#!/usr/bin/env python3
"""Stage Gmsh and its DomeD integration on top of the installed FLTK runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, default=root/'artifacts/system-stage')
    args = parser.parse_args()
    stage = args.stage.resolve()
    if stage.exists():
        raise SystemExit(f'Use an empty staging directory: {stage}')
    stage.mkdir(parents=True)
    existing = json.loads(Path('/opt/fltk-vr/install-manifest.json').read_text())
    for item in existing:
        source = Path('/') / item['path']
        target = stage / item['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        if 'symlink' in item:
            target.symlink_to(os.readlink(source))
        else:
            shutil.copy2(source, target)

    def copy(source, target, mode=0o644):
        destination = stage / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        destination.chmod(mode)
        return destination

    def text(target, value, mode=0o644):
        destination = stage / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(value)
        destination.chmod(mode)

    for name in ['dome-compositor', 'dome-xr', 'dome-preview', 'dome-portal-picker', 'gmsh']:
        source = root / 'build-domed/gmsh' if name == 'gmsh' else root.parent / 'DomeD/target/release' / name
        target = copy(source, 'opt/fltk-vr/bin/' + name, 0o755)
        subprocess.run(['patchelf', '--set-rpath', '$ORIGIN/../toolkit/lib', str(target)], check=True)
    text('usr/local/bin/gmsh', '''#!/bin/sh
set -eu
prefix=/opt/fltk-vr
export LD_LIBRARY_PATH="$prefix/toolkit/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$prefix/bin/gmsh" "$@"
''', 0o755)
    text('usr/local/bin/gmsh-dome-xr', '''#!/bin/sh
set -eu
export FLTK_BACKEND=wayland
unset WAYLAND_SOCKET
exec /usr/local/bin/gmsh -dome-xr "$@"
''', 0o755)
    desktop = (root/'utils/freedesktop/info.gmsh.gmsh.desktop').read_text().replace('Exec=gmsh\n', 'Exec=gmsh %F\nActions=DomeXR;\n')
    desktop += '\n[Desktop Action DomeXR]\nName=Open in DomeD XR\nExec=gmsh-dome-xr %F\n'
    text('usr/local/share/applications/info.gmsh.gmsh.desktop', desktop)
    copy(root/'utils/icons/gmsh.svg', 'usr/local/share/icons/hicolor/scalable/apps/gmsh.svg')
    copy(root/'LICENSE.txt', 'usr/local/share/doc/gmsh/LICENSE.txt')
    copy(root/'doc/DomeD-XR.md', 'usr/local/share/doc/gmsh/DomeD-XR.md')
    copy(root.parent/'DomeD/README.md', 'usr/local/share/doc/domed/README.md')
    copy(root.parent/'DomeD/docs/man/dome-compositor.1', 'usr/local/share/man/man1/dome-compositor.1')
    record = {'upstream': 'https://github.com/gmsh-project/gmsh', 'tag': 'gmsh_4_15_2',
              'base_commit': subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
              'local_domexr_changes': True, 'FLTK': '/opt/fltk-vr/toolkit (1.4.5)',
              'optimization': '-O3 -march=native; LTO'}
    text('usr/local/share/doc/gmsh/upstream.json', json.dumps(record, indent=2)+'\n')
    manifest = []
    for path in sorted(stage.rglob('*')):
        if path.is_symlink():
            manifest.append({'path': str(path.relative_to(stage)), 'symlink': os.readlink(path)})
        elif path.is_file():
            manifest.append({'path': str(path.relative_to(stage)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                             'mode': path.stat().st_mode & 0o777, 'size': path.stat().st_size})
    (stage.parent/'install-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Staged {len(manifest)} files: {stage}')


if __name__ == '__main__':
    main()
