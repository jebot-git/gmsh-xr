#!/usr/bin/env python3
"""Real Gmsh/FLTK rendering and DomeD routing on private displays and a simulated XR heartbeat.

Requires Xvfb, Pillow, python-xlib and dbus-next. Does not create an OpenXR/headset session.
"""
import argparse
import asyncio
import array
import json
import os
from pathlib import Path
import re
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from PIL import Image, ImageChops, ImageStat
from dbus_next.aio import MessageBus
from dbus_next import Message, MessageType, Variant
from Xlib import X, XK, display
from Xlib.ext import xtest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument('--gmsh', type=Path, default=root / 'build-domed/gmsh')
    parser.add_argument('--compositor', type=Path, default=root.parent / 'DomeD/target/release/dome-compositor')
    args = parser.parse_args()
    if os.environ.get('GMSH_DOME_TEST_BUS') != '1':
        os.execvpe('dbus-run-session', ['dbus-run-session', '--', sys.executable, *sys.argv],
                  {**os.environ, 'GMSH_DOME_TEST_BUS': '1'})
    signal.pthread_sigmask(signal.SIG_SETMASK, [])
    out = root / 'artifacts/domexr'
    out.mkdir(parents=True, exist_ok=True)
    children, logs, checks = [], [], []
    stopped = threading.Event()
    http = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def start(argv, name, env, **kw):
        log = (out / (name + '.log')).open('w')
        logs.append(log)
        child = subprocess.Popen(list(map(str, argv)), env=env, stdout=log, stderr=subprocess.STDOUT, **kw)
        children.append(child)
        return child

    def check(value, name):
        if not value:
            raise AssertionError(name)
        checks.append(name)
        print('PASS:', name, flush=True)

    def wait(fn, timeout=25):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                result = fn()
                if result:
                    return result
            except (OSError, ValueError, KeyError, StopIteration) as error:
                last = error
            time.sleep(.08)
        raise AssertionError(f'Timed out: {last}')

    try:
        with tempfile.TemporaryDirectory(prefix='gmsh-dome-xr-') as tmp:
            runtime = Path(tmp)
            runtime.chmod(0o700)
            read, write = os.pipe()
            xvfb = start(['Xvfb', '-displayfd', write, '-screen', '0', '1600x1000x24', '-nolisten', 'tcp', '-noreset'],
                         'xvfb', os.environ.copy(), pass_fds=(write,))
            os.close(write)
            with os.fdopen(read) as pipe:
                ds = ':' + pipe.readline().strip()
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            env = {**os.environ, 'DISPLAY': ds, 'XDG_RUNTIME_DIR': tmp, 'HOME': tmp,
                   'XDG_CONFIG_HOME': tmp + '/config', 'XDG_STATE_HOME': tmp + '/state',
                   'XDG_DATA_HOME': tmp + '/data', 'DOME_PREVIEW_PORT': str(port),
                   'DOME_LOGIN_SESSION': '0', 'DOME_START_XR': '0', 'DOME_START_IME': '0',
                   'DOME_SESSION_RESTORE': '0', 'DOME_APPEARANCE_SERVICE': '1', 'LD_LIBRARY_PATH': '/opt/fltk-vr/toolkit/lib',
                   'FLTK_BACKEND': 'x11'}
            for key in ['WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'DOME_BACKEND', 'DOME_RENDERER']:
                env.pop(key, None)
            appearance = runtime / 'config/dome/appearance.json'
            appearance.parent.mkdir(parents=True)
            appearance.write_text(json.dumps({'light': False, 'accent': '#6babff',
                                             'font': 'Unifont / Sans-Serif', 'font_size': 16}))
            geo = runtime / 'box.geo' 
            geo.write_text('SetFactory("OpenCASCADE");\nBox(1)={-.5,-.3,-.2,1,.6,.4};\nMesh.MeshSizeMin=.15;\nMesh.MeshSizeMax=.15;\n')
            mesh = runtime / 'box.msh'
            mesher = start([args.gmsh, geo, '-3', '-nt', '2', '-format', 'msh2', '-o', mesh], 'meshing', env)
            check(mesher.wait(timeout=45) == 0 and mesh.is_file(), 'OpenCASCADE model generates a real tetrahedral mesh')
            view = ['-setnumber', 'General.Trackball', '0', '-setnumber', 'General.RotationX', '20',
                    '-setnumber', 'General.RotationY', '30', '-setnumber', 'Mesh.SurfaceFaces', '1',
                    '-setnumber', 'Mesh.SurfaceEdges', '1']
            capture = out / 'stereo.ppm'
            capture.unlink(missing_ok=True)
            qa = start([args.gmsh, mesh, '-dome-xr-capture', capture, *view], 'capture', env)
            check(qa.wait(timeout=30) == 0 and capture.is_file(), 'Native FLTK stereo framebuffer capture completes')
            picture = Image.open(capture).convert('RGB')
            picture.save(out / 'stereo.png')
            def eyes(image):
                width = image.width // 2
                return image.crop((0, 0, width, image.height)), image.crop((image.width-width, 0, image.width, image.height))
            left, right = eyes(picture)
            check(max(ImageStat.Stat(left).var) > 10 and ImageChops.difference(left, right).getbbox(),
                  'Actual mesh renders with distinct left/right geometry')
            compositor = start([args.compositor, '--backend', 'nested'], 'compositor', env)
            base = f'http://127.0.0.1:{port}'
            def get(path):
                return json.load(http.open(base + path, timeout=3))
            def post(path, value):
                request = urllib.request.Request(base + path, data=json.dumps(value).encode(),
                                                headers={'Content-Type': 'application/json'})
                with http.open(request, timeout=3):
                    pass
            def scene():
                return get('/api/state')['scene']
            wait(lambda: scene()['source'] == 'wayland')
            match = wait(lambda: re.search(r'Dome Wayland socket: (\S+)', (out/'compositor.log').read_text()))
            fonts = wait(lambda: next(runtime.glob('dome-appearance-*/fonts.conf'), None))
            client = {**env, 'FONTCONFIG_FILE': str(fonts), 'WAYLAND_DISPLAY': match[1], 'DISPLAY': '', 'FLTK_BACKEND': 'wayland',
                      'XDG_CURRENT_DESKTOP': 'Dome', 'DE_XR_APPEARANCE_TRACE': '1'}
            refused = start([args.gmsh, mesh, '-term', '-dome-xr'], 'inactive', client)
            wait(lambda: 'Start XR in DomeD' in (out/'inactive.log').read_text())
            check(not any(w['app_id'] == 'org.gmsh.Sbs' for w in scene()['windows']),
                  'Inactive XR reports an error and retains the ordinary GUI')
            refused.terminate()
            refused.wait(timeout=5)
            wait(lambda: not scene()['windows'])
            def heartbeat():
                while not stopped.wait(.2):
                    try:
                        post('/api/xr-session', {'id': 481, 'visible': True, 'focused': True,
                             'head': {'position_m': [0, 1.4, 0], 'orientation_xyzw': [0, 0, 0, 1]},
                             'horizontal_fov_deg': 90, 'mouse_viewport': None})
                    except OSError:
                        pass
            thread = threading.Thread(target=heartbeat, daemon=True)
            thread.start()
            wait(lambda: get('/api/integrations/gmsh')['xr_active'])
            gui = start([args.gmsh, mesh, '-term', '-dome-xr', *view], 'wayland-gmsh', client)
            def stereo_window():
                return next((w for w in scene()['windows'] if w['app_id'] == 'org.gmsh.Sbs'), None)
            stereo = wait(stereo_window)
            desktop = wait(lambda: next((w for w in scene()['windows'] if w['app_id'] != 'org.gmsh.Sbs'), None))
            check(stereo['stereo'] == 'side_by_side' and stereo['xr_visible'] and not stereo['desktop_visible'],
                  'DomeD recognizes the dedicated stereo surface and routes it only to XR')
            check(desktop['stereo'] == 'mono' and desktop['desktop_visible'], 'The original Gmsh GUI remains a normal desktop window')

            async def dbus_call(service, path, interface, method, signature='', body=None):
                bus = await MessageBus().connect()
                try:
                    reply = await asyncio.wait_for(bus.call(Message(destination=service, path=path,
                        interface=interface, member=method, signature=signature, body=body or [])), timeout=3)
                    assert reply.message_type != MessageType.ERROR, reply.body
                    return reply.body
                finally:
                    bus.disconnect()
            def buscall(service, path, interface, method, signature='', body=None):
                return asyncio.run(dbus_call(service, path, interface, method, signature, body))
            def menu(service, number, method='GetLayout', signature='iias', body=None):
                return buscall(service, f'/org/de_xr/FLTK/Menu{number}', 'com.canonical.dbusmenu',
                               method, signature, [0, -1, []] if body is None else body)
            def find(node, text):
                if node[1].get('label', Variant('s','')).value.replace('_','') == text: return node
                return next((v for child in node[2] if (v := find(child.value, text))), None)
            service = wait(lambda: (re.search(r'DX_MENU (:\S+) /org/de_xr/FLTK/Menu1', (out/'wayland-gmsh.log').read_text()) or [None,None])[1])
            model = menu(service, 1)[1]
            xrmodel = wait(lambda: menu(service, 2)[1])
            check([child.value[1]['label'].value.replace('_','') for child in model[2]] == ['File','Tools','Window','Help']
                  and find(xrmodel, 'DomeD XR Mesh') is not None,
                  'Desktop and XR surfaces export the real Gmsh menu tree')
            check([[key.lower() for key in chord] for chord in find(model, 'DomeD XR Mesh')[1]['shortcut'].value] == [['control','shift','x']],
                  'Universal menu exports the native shortcut metadata')
            check(find(model, 'Open Recent') is not None and 'box.msh' in str(model),
                  'Dynamic recent-file entries are exported')
            wait(lambda: 'font=16 size=16' in (out/'wayland-gmsh.log').read_text())
            check(True, 'Startup UI inherits DomeD bitmap font and native strike size')
            def frame(id):
                with http.open(base + '/api/xr-frame/' + str(id), timeout=3) as response:
                    return Image.frombytes('RGBA', (int(response.headers['X-Dome-Width']),
                                                    int(response.headers['X-Dome-Height'])), response.read())
            before = wait(lambda: frame(stereo['id']))
            before.save(out/'native-wayland-stereo.png')
            check(ImageChops.difference(*eyes(before.convert('RGB'))).getbbox(), 'DomeD receives the distinct eye images through native Wayland')
            def gpu_lease():
                path = get('/api/xr-control')['gpu_socket']
                if not path:
                    return None
                descriptors = array.array('i')
                try:
                    with socket.socket(socket.AF_UNIX) as channel:
                        channel.settimeout(3)
                        channel.connect(path)
                        channel.sendall(struct.pack('<Q', stereo['id']))
                        status, ancillary, flags, _ = channel.recvmsg(1, socket.CMSG_SPACE(16))
                        for level, kind, data in ancillary:
                            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                                descriptors.frombytes(data)
                        if status != b'\1':
                            return None
                        assert len(descriptors) == 1 and not flags & socket.MSG_CTRUNC
                        def exact(length):
                            data = b''
                            while len(data) < length:
                                chunk = channel.recv(length-len(data))
                                if not chunk:
                                    raise OSError('Incomplete GPU lease')
                                data += chunk
                            return data
                        return json.loads(exact(struct.unpack('<I', exact(4))[0]))
                finally:
                    for fd in descriptors:
                        os.close(fd)
            lease = wait(gpu_lease)
            check(lease['device'] > 0 and lease['width'] > 0,
                  'The stereo mesh surface is exported as a native DMA-BUF GPU lease')
            wait(lambda: get('/api/xr-control')['input_realm'] == 'xr')
            # Let the compositor's XR presentation transition finish before
            # sending seat events, and deliver a real multi-frame drag.
            time.sleep(.5)
            # The initial FLTK buffer can precede DomeD's final size configure.
            # Compare input against the configured surface, not that first buffer.
            before = wait(lambda: frame(stereo['id']))
            def packet(events=(), actions=()):
                post('/api/xr-input', {'events': list(events), 'actions': list(actions)})
            packet([{'kind': 'motion', 'id': stereo['id'], 'uv': [.5, .5]}],
                   [{'op': 'focus', 'id': stereo['id']}])
            time.sleep(.1)
            packet([{'kind': 'button', 'button': 272, 'pressed': True}])
            time.sleep(.1)
            packet([{'kind': 'motion', 'id': stereo['id'], 'uv': [.65, .60]}])
            time.sleep(.1)
            packet([{'kind': 'button', 'button': 272, 'pressed': False}])
            def rotated():
                image = frame(stereo['id'])
                if image.size != before.size:
                    return None
                box = (40, 40, image.width-40, image.height-40)
                diff = ImageChops.difference(image.crop(box).convert('RGB'), before.crop(box).convert('RGB'))
                return image if max(ImageStat.Stat(diff).mean) > .2 else None
            after = wait(rotated)
            after.save(out/'native-wayland-rotated.png')
            check(True, 'XR pointer drag rotates the live mesh')
            connection = display.Display(ds)
            host = wait(lambda: next((w for w in connection.screen().root.query_tree().children
                        if str(w.get_wm_name() or '').startswith('Dome')), None))
            host.set_input_focus(X.RevertToParent, X.CurrentTime)
            connection.sync()

            def key(name, modifiers=()):
                codes = [connection.keysym_to_keycode(XK.string_to_keysym(k)) for k in [*modifiers, name]]
                for code in codes:
                    xtest.fake_input(connection, X.KeyPress, code)
                    connection.sync(); time.sleep(.04)
                for code in reversed(codes):
                    xtest.fake_input(connection, X.KeyRelease, code)
                    connection.sync(); time.sleep(.04)
            key('0')
            time.sleep(.5)
            check(max(ImageStat.Stat(ImageChops.difference(*eyes(frame(stereo['id']).convert('RGB')))).mean) > .05,
                  'Gmsh 0 shortcut is no longer intercepted as zero stereo separation')
            # Verify both palette and font change live in the actual native GUI.
            def ui_pixel():
                image = frame(desktop['id']).convert('RGB')
                return image.getpixel((image.width-10, 10))
            dark = wait(ui_pixel)
            appearance.write_text(json.dumps({'light': True, 'accent': '#bb3377',
                'font': 'Cozette / Medium', 'font_size': 13}))
            wait(lambda: 'size=13' in (out/'wayland-gmsh.log').read_text())
            wait(lambda: sum(ui_pixel()) > sum(dark)+150)
            check(True, 'Live appearance changes update native UI palette and bitmap font')
            frame(desktop['id']).save(out/'desktop-light.png')
            # Menus attach through the Wayland appmenu protocol. Open the real
            # Window menu through the XR shell, then navigate its native subtree.
            def xr_click(x, y):
                layout = get('/api/xr-shell')
                packet([{'kind':'motion', 'id':0, 'uv':[x/layout['width'], y/layout['top']]}])
                time.sleep(.15)
                packet([{'kind':'button','button':272,'pressed':True},
                        {'kind':'button','button':272,'pressed':False}])
                time.sleep(.25)
            # Universal order is File, Edit (shell fallback), Tools, Window, Help.
            xr_click(430, 18)
            wait(lambda: get('/api/xr-shell')['top'] > 36)
            key('Home'); key('Down'); key('Right'); key('Home'); key('Down'); key('Down'); key('Return')

            def zero_disparity():
                image = frame(stereo['id']).convert('RGB')
                difference = ImageChops.difference(*eyes(image))
                return image if max(ImageStat.Stat(difference).mean) < .05 else None
            wait(zero_disparity).save(out/'zero-baseline.png')
            check(True, 'Zero separation produces identical eye geometry in the live renderer')

            check(True, 'XR universal menu keyboard navigation invokes the native separation callback')
            config = get('/api/state')['scene']['config']
            binding = next(b for b in config['keybindings'] if b['command'] == 'Close')
            binding.update(key=0xffc5, mods={'ctrl':True,'shift':True,'logo':True,'alt':False}, enabled=True)
            post('/api/action', {'op':'configure','config':config})
            time.sleep(.3)
            packet([{'kind':'motion','id':stereo['id'],'uv':[.5,.5]}], [{'op':'focus','id':stereo['id']}])
            time.sleep(.2)
            key('F8', ['Super_L','Control_L','Shift_L'])
            wait(lambda: stereo_window() is None)
            check(gui.poll() is None, 'Remapped DomeD close shortcut takes precedence and closes only the XR surface')
            post('/api/action', {'op':'focus','id':desktop['id']})
            time.sleep(.2)
            key('x', ['Control_L','Shift_L'])
            stereo = wait(stereo_window)
            check(True, 'Native Ctrl+Shift+X shortcut reopens the XR mesh view')
            packet([{'kind':'motion','id':stereo['id'],'uv':[.5,.5]}], [{'op':'focus','id':stereo['id']}])
            time.sleep(.2)
            code = connection.keysym_to_keycode(XK.string_to_keysym('Escape'))
            xtest.fake_input(connection, X.KeyPress, code)
            xtest.fake_input(connection, X.KeyRelease, code)
            connection.sync()
            wait(lambda: stereo_window() is None)
            check(gui.poll() is None and bool(scene()['windows']), 'Escape closes only the XR view and keeps Gmsh alive')
            connection.close()
            stopped.set()
            thread.join(timeout=2)
    finally:
        stopped.set()
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        for log in logs:
            log.close()
        (out/'report.json').write_text(json.dumps({'checks': checks, 'physical_headset_tested': False}, indent=2)+'\n')


if __name__ == '__main__':
    main()
