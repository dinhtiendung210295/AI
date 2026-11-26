"""Chrome Native Messaging host. No HTTP server, audio capture or transcript logs."""
import ctypes as c
from ctypes import wintypes as w
import json
import struct
import sys
import threading
import time
import uiautomation as auto

u = c.WinDLL('user32', use_last_error=True)
k = c.WinDLL('kernel32', use_last_error=True)
u.GetForegroundWindow.restype = w.HWND
u.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
u.GetWindowThreadProcessId.restype = w.DWORD
u.GetAsyncKeyState.argtypes = [c.c_int]
u.GetAsyncKeyState.restype = c.c_short
k.GlobalAlloc.argtypes = [w.UINT, c.c_size_t]
k.GlobalAlloc.restype = w.HGLOBAL
k.GlobalLock.argtypes = [w.HGLOBAL]
k.GlobalLock.restype = c.c_void_p
k.GlobalUnlock.argtypes = [w.HGLOBAL]
k.GlobalFree.argtypes = [w.HGLOBAL]
u.SetClipboardData.argtypes = [w.UINT, w.HANDLE]
u.SetClipboardData.restype = w.HANDLE
u.OpenClipboard.argtypes = [w.HWND]
u.GetGUIThreadInfo.argtypes = [w.DWORD, c.c_void_p]
u.SendMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
u.SendMessageW.restype = w.LPARAM


class GUI(c.Structure):
    _fields_ = [('cbSize', w.DWORD), ('flags', w.DWORD),
                ('active', w.HWND), ('focus', w.HWND), ('capture', w.HWND),
                ('menu', w.HWND), ('move', w.HWND), ('caret', w.HWND), ('rect', w.RECT)]


class KEY(c.Structure):
    _fields_ = [('vk', w.WORD), ('scan', w.WORD), ('flags', w.DWORD),
                ('time', w.DWORD), ('extra', c.c_size_t)]


class MOUSE(c.Structure):
    _fields_ = [('dx', w.LONG), ('dy', w.LONG), ('data', w.DWORD),
                ('flags', w.DWORD), ('time', w.DWORD), ('extra', c.c_size_t)]


class PAYLOAD(c.Union):
    _fields_ = [('keyboard', KEY), ('mouse', MOUSE)]


class INPUT(c.Structure):
    _fields_ = [('type', w.DWORD), ('payload', PAYLOAD)]


u.SendInput.argtypes = [w.UINT, c.POINTER(INPUT), c.c_int]
u.SendInput.restype = w.UINT
lock = threading.Lock()
state_lock = threading.Lock()
pending = None
stopping = threading.Event()
clipboard_owner = None


def emit(value):
    data = json.dumps(value, ensure_ascii=True).encode('utf8')
    with lock:
        sys.stdout.buffer.write(struct.pack('<I', len(data)) + data)
        sys.stdout.buffer.flush()


def target():
    """UIA first for Electron/Chromium editors; never inspect entered text."""
    hwnd = u.GetForegroundWindow()
    try:
        control = auto.GetFocusedControl()
        if control and control.HasKeyboardFocus and not control.IsPassword and control.ControlType == 50004:
            pid = w.DWORD()
            u.GetWindowThreadProcessId(hwnd, c.byref(pid))
            if control.ProcessId == pid.value and not elevated(pid.value):
                pattern = control.GetValuePattern()
                if pattern and not pattern.IsReadOnly:
                    # Include selection range when the provider exposes it;
                    # otherwise element identity still detects focus changes.
                    position = ()
                    try:
                        text_pattern = control.GetTextPattern()
                        ranges = text_pattern.GetSelection() if text_pattern else []
                        position = tuple((r.left, r.top, r.right, r.bottom)
                                         for selection in ranges for r in selection.GetBoundingRectangles())
                    except Exception:
                        pass
                    return ('uia', hwnd, tuple(control.GetRuntimeId()), position)
    except Exception:
        pass
    return win32_target()


def win32_target():
    hwnd = u.GetForegroundWindow()
    thread = u.GetWindowThreadProcessId(hwnd, None)
    info = GUI(cbSize=c.sizeof(GUI))
    if not u.GetGUIThreadInfo(thread, c.byref(info)):
        return None
    # Without a detectable caret we cannot establish safe insertion identity.
    if not info.focus or not info.caret:
        return None
    name = c.create_unicode_buffer(256)
    u.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, c.c_int]
    u.GetClassNameW(info.focus, name, 256)
    if 'edit' in name.value.lower() and u.SendMessageW(info.focus, 0x00D2, 0, 0):
        return None  # EM_GETPASSWORDCHAR
    # Exclude elevated processes; never request elevation to inject keystrokes.
    pid = w.DWORD()
    u.GetWindowThreadProcessId(hwnd, c.byref(pid))
    if elevated(pid.value):
        return None
    return (hwnd, info.focus, info.caret, info.rect.left, info.rect.top, info.rect.right, info.rect.bottom)


def elevated(pid):
    adv = c.WinDLL('advapi32', use_last_error=True)
    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k.OpenProcess.restype = w.HANDLE
    k.CloseHandle.argtypes = [w.HANDLE]
    adv.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
    adv.GetTokenInformation.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
    process = k.OpenProcess(0x1000, False, pid)
    if not process:
        return True
    token = w.HANDLE()
    try:
        if not adv.OpenProcessToken(process, 8, c.byref(token)):
            return True
        value, size = w.DWORD(), w.DWORD()
        if not adv.GetTokenInformation(token, 20, c.byref(value), c.sizeof(value), c.byref(size)):
            return True
        return bool(value.value)
    finally:
        if token:
            k.CloseHandle(token)
        k.CloseHandle(process)


def clipboard(text):
    global clipboard_owner
    data = (text + '\0').encode('utf-16-le')
    handle = k.GlobalAlloc(0x42, len(data))
    if not handle:
        raise RuntimeError('Không cấp được bộ nhớ clipboard.')
    address = k.GlobalLock(handle)
    if not address:
        k.GlobalFree(handle)
        raise RuntimeError('Không khóa được bộ nhớ clipboard.')
    c.memmove(address, data, len(data))
    k.GlobalUnlock(handle)
    u.CreateWindowExW.argtypes = [w.DWORD,w.LPCWSTR,w.LPCWSTR,w.DWORD,c.c_int,c.c_int,c.c_int,c.c_int,w.HWND,w.HMENU,w.HINSTANCE,c.c_void_p]
    u.CreateWindowExW.restype = w.HWND
    u.DestroyWindow.argtypes = [w.HWND]
    if not clipboard_owner:
        clipboard_owner = u.CreateWindowExW(0, 'STATIC', 'Local dictation clipboard', 0, 0, 0, 0, 0, w.HWND(-3), None, None, None)
    owner = clipboard_owner
    if not owner:
        k.GlobalFree(handle)
        raise RuntimeError('Không tạo được clipboard owner.')
    for _ in range(10):
        if u.OpenClipboard(owner):
            break
        time.sleep(.03)
    else:
        k.GlobalFree(handle)
        raise RuntimeError('Clipboard đang bị ứng dụng khác giữ.')
    try:
        if not u.EmptyClipboard() or not u.SetClipboardData(13, handle):
            raise RuntimeError('Không ghi được clipboard.')
        handle = None  # ownership transferred to Windows
    finally:
        u.CloseClipboard()
        if handle:
            k.GlobalFree(handle)
    # Closing the clipboard can advance the sequence as Windows materializes
    # compatible formats. Capture AFTER closing; retain the message-only owner.
    return u.GetClipboardSequenceNumber()


def paste():
    keys = [(0x11, 0), (0x56, 0), (0x56, 2), (0x11, 2)]
    inputs = (INPUT * 4)(*[INPUT(type=1, payload=PAYLOAD(keyboard=KEY(vk=vk, flags=flags))) for vk, flags in keys])
    count = u.SendInput(4, inputs, c.sizeof(INPUT))
    if count != 4:
        # Always try releasing modifiers on partial injection.
        releases = (INPUT * 2)(*[INPUT(type=1, payload=PAYLOAD(keyboard=KEY(vk=vk, flags=2))) for vk in (0x56, 0x11)])
        u.SendInput(2, releases, c.sizeof(INPUT))
        raise RuntimeError('Windows không nhận đủ thao tác paste; chữ vẫn ở clipboard.')


def hotkeys():
    with auto.UIAutomationInitializerInThread():
        hotkeys_loop()


def hotkeys_loop():
    global pending
    u.RegisterHotKey.argtypes = [w.HWND, c.c_int, w.UINT, w.UINT]
    if not u.RegisterHotKey(None, 91, 0x4002, 0xC0):
        emit({'event':'status', 'status':'Ctrl + ` đang bị ứng dụng khác giữ. Hãy tắt bản thử cũ.'})
        return
    emit({'event':'status', 'status':'Windows sẵn sàng: giữ Ctrl + ` để nói, thả để lấy chữ và dán. Đích không xác minh được thì chỉ copy.'})
    msg = w.MSG()
    u.PeekMessageW.argtypes = [c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT]
    held = False
    checked = 0
    try:
        while not stopping.is_set():
            while u.PeekMessageW(c.byref(msg), None, 0, 0, 1):
                if msg.message == 0x0312:
                    with state_lock:
                        if not held and pending is None:
                            pending = {'target':target(), 'changed':False, 'since':time.monotonic()}
                            held = True
                            emit({'event':'start'})
            with state_lock:
                if pending and time.monotonic() - checked > .15:
                    checked = time.monotonic()
                    if pending['target'] != target():
                        pending['changed'] = True
                    if time.monotonic() - pending['since'] > 100:
                        pending = None
                        emit({'event':'status','status':'Lượt đọc quá hạn; không tự paste.'})
            if held and not (u.GetAsyncKeyState(0x11) & 0x8000 and u.GetAsyncKeyState(0xC0) & 0x8000):
                held = False
                emit({'event':'stop'})
            time.sleep(.015)
    finally:
        u.UnregisterHotKey(None, 91)


def read_exact(size):
    data = b''
    while len(data) < size:
        chunk = sys.stdin.buffer.read(size-len(data))
        if not chunk:
            return None
        data += chunk
    return data


def main():
    with auto.UIAutomationInitializerInThread():
        run_host()


def run_host():
    global pending
    threading.Thread(target=hotkeys, daemon=True).start()
    try:
        while True:
            header = read_exact(4)
            if not header:
                break
            length = struct.unpack('<I', header)[0]
            if length > 1024*1024:
                break
            raw = read_exact(length)
            if raw is None:
                break
            message = json.loads(raw)
            if message.get('type') == 'abort':
                with state_lock:
                    pending = None
                continue
            if message.get('type') != 'result':
                continue
            text = message.get('text')
            if not isinstance(text, str) or not text.strip() or len(text) > 100000:
                continue
            with state_lock:
                job, pending = pending, None
            if not job:
                emit({'event':'status', 'status':'Đã nhận bản chữ nhưng không còn lượt hotkey tương ứng; không copy/paste. Hãy bật lại cầu nối Windows.'})
                continue
            try:
                emit({'event':'status','status':'Windows đã nhận bản chữ; đang ghi clipboard…'})
                sequence = clipboard(text)
                safe = (job['target'] is not None and not job['changed'] and target() == job['target']
                        and not any(u.GetAsyncKeyState(vk) & 0x8000 for vk in (0x11, 0x10, 0x12, 0x5B, 0x5C)))
                if safe and sequence == u.GetClipboardSequenceNumber() and target() == job['target']:
                    paste()
                    status = 'Đã copy và gửi Ctrl+V tới ô nhập ban đầu. Không nhấn Enter.'
                else:
                    reason = ('không xác minh được ô nhập ban đầu' if job['target'] is None
                              else 'focus/ô nhập đã thay đổi trong lúc thu' if job['changed']
                              else 'đích hiện tại hoặc phím bổ trợ chưa phù hợp')
                    status = f'Đã copy nhưng KHÔNG tự paste: {reason}. Dùng Ctrl+V.'
                emit({'event':'copied','text':text,'status':status})
            except Exception as exc:
                emit({'event':'failed','status':str(exc)})
    finally:
        stopping.set()


if __name__ == '__main__':
    main()
