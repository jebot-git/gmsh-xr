#!/usr/bin/env python3
"""Check visible menu collapse, layout, shortcuts and fallback in real Gmsh."""
import asyncio
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from PIL import Image, ImageChops
from Xlib import X, XK, display
from Xlib.ext import xtest

if '--registrar' in sys.argv:
    from dbus_next.aio import MessageBus
    async def registrar():
        bus = await MessageBus().connect()
        await bus.request_name('com.canonical.AppMenu.Registrar')
        print('ready', flush=True)
        await asyncio.Future()
    asyncio.run(registrar())
    raise SystemExit()

signal.pthread_sigmask(signal.SIG_SETMASK, [])
if os.environ.get('GMSH_MENU_TEST_BUS') != '1':
    os.execvpe('dbus-run-session', ['dbus-run-session', '--', sys.executable, *sys.argv],
              {**os.environ, 'GMSH_MENU_TEST_BUS': '1'})
repo = Path(__file__).resolve().parents[1]
binary = Path(os.environ.get('GMSH_MENU_BINARY', repo / 'build-domed/gmsh'))
output = repo / 'artifacts/domemenu'
output.mkdir(parents=True, exist_ok=True)
checks, processes, logs = [], [], []

def wait(fn, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = fn()
        if value:
            return value
        time.sleep(.08)
    raise AssertionError('Timed out')

def check(value, label):
    assert value, label
    checks.append(label)
    print('PASS', label, flush=True)

with tempfile.TemporaryDirectory(prefix='gmsh-universal-menu-') as tmp:
    rd, wr = os.pipe()
    xvfb = subprocess.Popen(['Xvfb', '-displayfd', str(wr), '-screen', '0', '1500x1000x24',
                             '-nolisten', 'tcp'], pass_fds=(wr,), stderr=subprocess.DEVNULL)
    os.close(wr)
    with os.fdopen(rd) as pipe:
        ds = ':' + pipe.readline().strip()
    connection = display.Display(ds)
    env = {**os.environ, 'DISPLAY': ds, 'FLTK_BACKEND': 'x11', 'HOME': tmp,
           'XDG_CONFIG_HOME': tmp + '/config', 'XDG_CACHE_HOME': tmp + '/cache',
           'XDG_DATA_HOME': tmp + '/data', 'XDG_CURRENT_DESKTOP': 'Dome',
           'DE_XR_APPEARANCE_TRACE': '1', 'XMODIFIERS': '@im=none'}
    for key in ['WAYLAND_DISPLAY', 'WAYLAND_SOCKET']:
        env.pop(key, None)
    appearance = Path(tmp) / 'config/dome/appearance.json'
    appearance.parent.mkdir(parents=True)
    appearance.write_text(json.dumps({'light': False, 'font': 'Unifont / Sans-Serif',
                                     'font_size': 16, 'accent': '#6babff'}))
    def windows():
        return connection.screen().root.query_tree().children
    def window():
        return wait(lambda: next((w for w in windows() if 'Gmsh' in str(w.get_wm_name() or '')
                                  and w.get_attributes().map_state == X.IsViewable
                                  and w.get_geometry().height > 200), None))
    def start_app(name, desktop='Dome'):
        log = (output / (name + '.log')).open('w')
        logs.append(log)
        app = subprocess.Popen([str(binary), '-term'], env={**env, 'XDG_CURRENT_DESKTOP': desktop},
                               stdout=log, stderr=log)
        processes.append(app)
        return app, window(), output / (name + '.log')
    def capture(w, name):
        w.set_input_focus(X.RevertToParent, X.CurrentTime)
        w.configure(stack_mode=X.Above)
        connection.sync()
        time.sleep(.4)
        g = w.get_geometry()
        raw = w.get_image(0, 0, g.width, g.height, X.ZPixmap, 0xffffffff)
        image = Image.frombytes('RGB', (g.width, g.height), raw.data, 'raw', 'BGRX')
        image.save(output / (name + '.png'))
        return image
    def key(w, name, ctrl=False):
        w.set_input_focus(X.RevertToParent, X.CurrentTime)
        modifier = connection.keysym_to_keycode(XK.string_to_keysym('Control_L'))
        code = connection.keysym_to_keycode(XK.string_to_keysym(name))
        if ctrl:
            xtest.fake_input(connection, X.KeyPress, modifier)
        xtest.fake_input(connection, X.KeyPress, code)
        xtest.fake_input(connection, X.KeyRelease, code)
        if ctrl:
            xtest.fake_input(connection, X.KeyRelease, modifier)
        connection.sync()
    def layout(w):
        service = wait(lambda: w.get_full_property(connection.intern_atom('_KDE_NET_WM_APPMENU_SERVICE_NAME'), X.AnyPropertyType))
        path = w.get_full_property(connection.intern_atom('_KDE_NET_WM_APPMENU_OBJECT_PATH'), X.AnyPropertyType)
        return subprocess.check_output(['gdbus', 'call', '--session', '--dest', bytes(service.value).decode(),
            '--object-path', bytes(path.value).decode(), '--method', 'com.canonical.dbusmenu.GetLayout',
            '--', '0', '-1', '[]'], text=True)
    def start_host():
        host = subprocess.Popen([sys.executable, __file__, '--registrar'], env=env,
                                stdout=subprocess.PIPE, text=True)
        processes.append(host)
        assert host.stdout.readline().strip() == 'ready'
        return host
    try:
        app, w, trace = start_app('dome')
        before = capture(w, 'local-without-host')
        check(all(label in layout(w) for label in ['File', 'Tools', 'Window', 'Help']),
              'real Gmsh commands export while the fallback menu remains available')
        host = start_host()
        wait(lambda: 'DX_UNIVERSAL_MENU external=1 height=0' in trace.read_text())
        wait(lambda: 'DX_MENU_LAYOUT top=0' in trace.read_text())
        hidden = capture(w, 'universal-no-duplicate')
        band = (0, 0, 240, 20)
        check(ImageChops.difference(before.crop(band), hidden.crop(band)).getbbox(),
              'the local bar disappears and the content reclaims its top row')
        check('Open' in layout(w), 'collapsed menus continue exporting their native commands')
        key(w, 'o', True)
        chooser = wait(lambda: next((item for item in windows() if item.id != w.id
            and 'Open' in str(item.get_wm_name() or '')
            and item.get_attributes().map_state == X.IsViewable), None))
        check(app.poll() is None, 'Ctrl+O still opens the native chooser with the local bar collapsed')
        key(chooser, 'Escape')
        host.terminate()
        host.wait(timeout=5)
        wait(lambda: 'DX_UNIVERSAL_MENU external=0 height=' in trace.read_text())
        restored = capture(w, 'local-restored-on-host-loss')
        check(not ImageChops.difference(before.crop(band), restored.crop(band)).getbbox(),
              'losing the universal menu host restores the original local menu and layout')
        host = start_host()
        wait(lambda: trace.read_text().count('DX_UNIVERSAL_MENU external=1 height=0') >= 2)
        geometry = w.get_geometry()
        w.configure(width=geometry.width + 60, height=geometry.height + 50)
        connection.sync()
        resized = capture(w, 'universal-after-resize')
        check(ImageChops.difference(before.crop(band), resized.crop(band)).getbbox(),
              'resizing with the host active keeps the local menu collapsed')
        app.terminate()
        app.wait(timeout=5)
        wait(lambda: not any(item.id == w.id for item in windows()))
        other, other_window, other_trace = start_app('other-desktop', 'GNOME')
        capture(other_window, 'other-desktop-local')
        check('Open' in layout(other_window) and 'DX_UNIVERSAL_MENU external=1' not in other_trace.read_text(),
              'other desktops retain the local menu even when a registrar is present')
    finally:
        for child in reversed(processes):
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
        connection.close()
        xvfb.terminate()
        xvfb.wait(timeout=5)
        for log in logs:
            log.close()
(output / 'report.json').write_text(json.dumps({'checks': checks}, indent=2) + '\n')
