import asyncio
import ctypes
import ctypes.wintypes
import io
import math
import struct
import subprocess

# noinspection PyCompatibility
import winreg
import zlib
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional

import appdirs

from wizwalker import ExceptionalTimeout
from wizwalker.constants import Keycode, kernel32, user32, gdi32


DEFAULT_INSTALL = "C:/ProgramData/KingsIsle Entertainment/Wizard101"


async def async_sorted(iterable, /, *, key=None, reverse=False):
    """
    sorted but key function is awaited
    """
    if key is None:
        return sorted(iterable, reverse=reverse)

    evaluated = {}

    for item in iterable:
        evaluated[item] = await key(item)

    return [
        i[0] for i in sorted(evaluated.items(), key=lambda it: it[1], reverse=reverse)
    ]


class Color:
    def __init__(self, r: int, g: int, b: int):
        self.r = r
        self.g = g
        self.b = b

    def __iter__(self):
        return iter((self.r, self.g, self.b))


class XYZ:
    def __init__(self, x: float, y: float, z: float):
        self.x = x
        self.y = y
        self.z = z

    def __sub__(self, other):
        return self.distance(other)

    def __str__(self):
        return f"<XYZ ({self.x}, {self.y}, {self.z})>"

    def __repr__(self):
        return str(self)

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def distance(self, other):
        """
        Calculate the distance between two points
        this does not account for z axis
        """
        if not isinstance(other, type(self)):
            raise ValueError(
                f"Can only calculate distance between instances of {type(self)} not {type(other)}"
            )

        return math.dist((self.x, self.y), (other.x, other.y))

    def yaw(self, other):
        """Calculate perfect yaw to reach another xyz"""
        if not isinstance(other, type(self)):
            raise ValueError(
                f"Can only calculate yaw between instances of {type(self)} not {type(other)}"
            )

        return calculate_perfect_yaw(self, other)

    def relative_yaw(self, *, x: float = None, y: float = None):
        """Calculate relative yaw to reach another x and/or y relative to current"""
        if x is None:
            x = self.x
        if y is None:
            y = self.y

        other = type(self)(x, y, self.z)
        return self.yaw(other)


class Orient:
    def __init__(self, pitch: float, roll: float, yaw: float):
        self.pitch = pitch
        self.roll = roll
        self.yaw = yaw

    def __str__(self):
        return f"<Orient (Pitch: {self.pitch}, roll: {self.roll}, yaw: {self.yaw})>"

    def __repr__(self):
        return str(self)

    def __iter__(self):
        return iter((self.pitch, self.roll, self.yaw))


class Rectangle:
    def __init__(self, x1: int, y1: int, x2: int, y2: int):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    def __str__(self):
        return f"<Rectangle ({self.x1}, {self.y1}, {self.x2}, {self.y2})>"

    def __repr__(self):
        return str(self)

    def __iter__(self):
        return iter((self.x1, self.x2, self.y1, self.y2))

    def scale_to_client(self, parents: List["Rectangle"], factor: float) -> "Rectangle":
        """
        Scale this rectangle base on parents and a scale factor

        Args:
            parents: List of other rectangles
            factor: Factor to scale by

        Returns:
            The scaled rectangle
        """
        x1_sum = self.x1
        y1_sum = self.y1

        for rect in parents:
            x1_sum += rect.x1
            y1_sum += rect.y1

        converted = Rectangle(
            int(x1_sum * factor),
            int(y1_sum * factor),
            int(((self.x2 - self.x1) * factor) + (x1_sum * factor)),
            int(((self.y2 - self.y1) * factor) + (y1_sum * factor)),
        )

        return converted

    def center(self):
        """
        Get the center point of this rectangle

        Returns:
            The center point
        """
        center_x = ((self.x2 - self.x1) // 2) + self.x1
        center_y = ((self.y2 - self.y1) // 2) + self.y1

        return center_x, center_y

    def paint_on_screen(self, window_handle: int, *, rgb: tuple = (255, 0, 0)):
        """
        Paint this rectangle to the screen for debugging

        Args:
            rgb: Red, green, blue tuple to define the color of the rectangle
            window_handle: Handle to the window to paint the rectangle on
        """
        paint_struct = PAINTSTRUCT()
        # https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdc
        device_context = user32.GetDC(window_handle)
        brush = gdi32.CreateSolidBrush(ctypes.wintypes.RGB(*rgb))

        user32.BeginPaint(window_handle, ctypes.byref(paint_struct))

        # left, top = top left corner; right, bottom = bottom right corner
        draw_rect = ctypes.wintypes.RECT()
        draw_rect.left = self.x1
        draw_rect.top = self.y1
        draw_rect.right = self.x2
        draw_rect.bottom = self.y2

        # https://docs.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-createrectrgnindirect
        region = gdi32.CreateRectRgnIndirect(ctypes.byref(draw_rect))
        # https://docs.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-fillrgn
        gdi32.FillRgn(device_context, region, brush)

        user32.EndPaint(window_handle, ctypes.byref(paint_struct))
        user32.ReleaseDC(window_handle, device_context)
        gdi32.DeleteObject(brush)
        gdi32.DeleteObject(region)


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", ctypes.wintypes.HDC),
        ("fErase", ctypes.wintypes.BOOL),
        ("rcPaint", ctypes.wintypes.RECT),
        ("fRestore", ctypes.wintypes.BOOL),
        ("fIncUpdate", ctypes.wintypes.BOOL),
        ("rgbReserved", ctypes.c_char * 32),
    ]


def order_clients(clients):
    def sort_clients(client):
        rect = client.window_rectangle
        return rect.y1, rect.x1

    return sorted(clients, key=sort_clients)


_OVERRIDE_PATH = None


def override_wiz_install_location(path: str):
    """
    Override the path returned by get_wiz_install

    Args:
        path: The path to override with
    """
    # hacking old behavior so I dont have to actually fix the issue
    global _OVERRIDE_PATH
    _OVERRIDE_PATH = path


def get_wiz_install() -> Path:
    """
    Get the game install root dir
    """
    if _OVERRIDE_PATH:
        return Path(_OVERRIDE_PATH).absolute()

    default_install_path = Path(DEFAULT_INSTALL)

    if default_install_path.exists():
        return default_install_path

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{A9E27FF5-6294-46A8-B8FD-77B1DECA3021}",
            0,
            winreg.KEY_READ,
        ) as key:
            install_location = Path(
                winreg.QueryValueEx(key, "InstallLocation")[0]
            ).absolute()
            return install_location
    except OSError:
        raise Exception("Wizard101 install not found.")


def start_instance():
    """
    Starts a wizard101 instance
    """
    location = get_wiz_install()
    subprocess.Popen(
        rf"{location}\Bin\WizardGraphicalClient.exe -L login.us.wizard101.com 12000",
        cwd=rf"{location}\Bin",
    )


def instance_login(window_handle: int, username: str, password: str):
    """
    Login to an instance on the login screen

    Args:
        window_handle: Handle to window
        username: Username to login with
        password: Password to login with
    """

    def send_chars(chars: str):
        for char in chars:
            user32.SendMessageW(window_handle, 0x102, ord(char), 0)

    send_chars(username)
    # tab
    user32.SendMessageW(window_handle, 0x102, 9, 0)
    send_chars(password)
    # enter
    user32.SendMessageW(window_handle, 0x102, 13, 0)


# TODO: use login window for this
# -- [LoginWindow] GameLoginWindow
# --- [title1 shadow] ControlText
# --- [loginPassword] ControlEdit
# --- [passwordText] ControlText
# --- [accountText] ControlText
# --- [okButton] ControlButton
# --- [cancelButton] ControlButton
# --- [title1] ControlText
# --- [loginName] ControlEdit
async def start_instances_with_login(instance_number: int, logins: Iterable, wait_for_ready=True):
    """
    Start a number of instances and login to them with logins

    Args:
        instance_number: number of instances to start
        logins: logins to use
    """
    start_handles = set(get_all_wizard_handles())

    for _ in range(instance_number):
        start_instance()

    # TODO: have way to properly check if instances are on login screen
    # waiting for instances to start
    if wait_for_ready:
      await asyncio.sleep(7)

    new_handles = set(get_all_wizard_handles()).difference(start_handles)

    for handle, username_password in zip(new_handles, logins):
        username, password = username_password.split(":")
        instance_login(handle, username, password)


def patch_open_browser():
    """
    Patches EmbeddedBrowserConfig so that the game doesn't
    open a web browser when closed
    """
    install_location = get_wiz_install()
    data = '<Objects><Class Name="class EmbeddedBrowserConfig"></Class></Objects>'
    browser_config = install_location / "bin" / "EmbeddedBrowserConfig.xml"
    browser_config.write_text(data)


def calculate_perfect_yaw(current_xyz: XYZ, target_xyz: XYZ) -> float:
    """
    Calculates the perfect yaw to reach an xyz in a stright line

    Args:
        current_xyz: Starting position xyz
        target_xyz: Ending position xyz
    """
    target_line = math.dist(
        (current_xyz.x, current_xyz.y), (target_xyz.x, target_xyz.y)
    )
    origin_line = math.dist(
        (current_xyz.x, current_xyz.y), (current_xyz.x, current_xyz.y - 1)
    )
    target_to_origin_line = math.dist(
        (target_xyz.x, target_xyz.y), (current_xyz.x, current_xyz.y - 1)
    )

    if 1.0 - abs(origin_line) > 0.0 or 1.0 - abs(target_line) > 0.0:
        # will lead to division by 0 if left alone
        return 0

    # target_angle = math.cos(origin_line / target_line)
    target_angle = math.acos(
        (pow(target_line, 2) + pow(origin_line, 2) - pow(target_to_origin_line, 2))
        / (2 * origin_line * target_line)
    )

    if target_xyz.x > current_xyz.x:
        # outside
        target_angle_degres = math.degrees(target_angle)
        perfect_yaw = math.radians(360 - target_angle_degres)
    else:
        # inside
        perfect_yaw = target_angle

    return perfect_yaw


# TODO: 2.0 rename coro to awaitable (do for other wait_for methods also)
async def wait_for_value(
    coro, want, sleep_time: float = 0.5, *, ignore_errors: bool = True
):
    """
    Wait for a awaitable to return a value

    Args:
        coro: awaitable to wait for
        want: Value wanted
        sleep_time: Time between calls
        ignore_errors: If errors should be ignored
    """
    while True:
        try:
            now = await coro()
            if now == want:
                return now

        except Exception as e:
            if ignore_errors:
                await asyncio.sleep(sleep_time)

            else:
                raise e


async def wait_for_non_error(coro, sleep_time: float = 0.5):
    """
    Wait for a coro to not error

    Args:
        coro: Coro to wait for
        sleep_time: Time between calls
    """
    while True:
        # noinspection PyBroadException
        try:
            return await coro()

        except Exception:
            await asyncio.sleep(sleep_time)


async def maybe_wait_for_value_with_timeout(
    coro,
    sleep_time: float = 0.5,
    *,
    value: Any = None,
    timeout: Optional[float] = None,
    ignore_exceptions: bool = True,
    inverse_value: bool = False,
):
    possible_exception = None

    async def _inner():
        nonlocal possible_exception

        while True:
            try:
                res = await coro()
                if value is not None and inverse_value and res != value:
                    return res

                elif value is not None and not inverse_value and res == value:
                    return res

                elif value is None and inverse_value and res is not None:
                    return res

            except Exception as e:
                if ignore_exceptions:
                    possible_exception = e
                    await asyncio.sleep(sleep_time)

                else:
                    raise e

            await asyncio.sleep(sleep_time)

    try:
        return await asyncio.wait_for(_inner(), timeout)
    except asyncio.TimeoutError:
        raise ExceptionalTimeout(
            f"Timed out waiting for coro {coro.__name__}", possible_exception
        )


async def maybe_wait_for_any_value_with_timeout(
    coro,
    sleep_time: float = 0.5,
    *,
    timeout: Optional[float] = None,
    ignore_exceptions: bool = True,
):
    possible_exception = None

    async def _inner():
        nonlocal possible_exception

        while True:
            try:
                res = await coro()
                if res is not None:
                    return res

            except Exception as e:
                if ignore_exceptions:
                    possible_exception = e


                else:
                    raise e

            await asyncio.sleep(sleep_time)

    try:
        return await asyncio.wait_for(_inner(), timeout)
    except asyncio.TimeoutError:
        raise ExceptionalTimeout(
            f"Timed out waiting for coro", possible_exception
        )


def get_cache_folder() -> Path:
    """
    Get the wizwalker cache folder
    """
    app_name = "WizWalker"
    app_author = "StarrFox"
    cache_dir = Path(appdirs.user_cache_dir(app_name, app_author))

    cache_dir.mkdir(parents=True, exist_ok=True)

    return cache_dir


def get_logs_folder() -> Path:
    """
    Get the wizwalker log folder
    """
    app_name = "WizWalker"
    app_author = "StarrFox"
    log_dir = Path(appdirs.user_log_dir(app_name, app_author))

    log_dir.mkdir(parents=True, exist_ok=True)

    return log_dir


def get_system_directory(max_size: int = 100) -> Path:
    """
    Get the windows system directory

    Args:
        max_size: Max size of the string
    """
    # https://docs.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getsystemdirectoryw
    buffer = ctypes.create_unicode_buffer(max_size)
    kernel32.GetSystemDirectoryW(buffer, max_size)

    return Path(buffer.value)


def get_foreground_window() -> Optional[int]:
    """
    Get the window currently in the forground

    Returns:
        Handle to the window currently in the forground
    """
    return user32.GetForegroundWindow()


def set_foreground_window(window_handle: int) -> bool:
    """
    Bring a window to the foreground

    Args:
        window_handle: Handle to the window to bring to the foreground

    Returns:
        False if the operation failed True otherwise
    """
    return user32.SetForegroundWindow(window_handle) != 0


def get_window_title(handle: int, max_size: int = 100) -> str:
    """
    Get a window's title bar text

    Args:
        handle: Handle to the window
        max_size: Max size to read

    Returns:
        The window title
    """
    # https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowtextw
    window_title = ctypes.create_unicode_buffer(max_size)
    user32.GetWindowTextW(handle, ctypes.byref(window_title), max_size)
    return window_title.value


def set_window_title(handle: int, window_title: str):
    """
    Set a window's title bar text

    Args:
        handle: Handle to the window
        window_title: Title to write
    """
    # https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowtextw
    user32.SetWindowTextW(handle, window_title)


def get_window_rectangle(handle: int) -> Rectangle:
    """
    Get a window's Rectangle

    Args:
        handle: Handle to the window

    Returns:
        The window's Rectangle
    """
    # https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowrect
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(handle, ctypes.byref(rect))

    # noinspection PyTypeChecker
    return Rectangle(rect.right, rect.top, rect.left, rect.bottom)


def check_if_process_running(handle: int) -> bool:
    """
    Checks if a process is still running
    True = Running
    False = Not
    """
    # https://docs.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getexitcodeprocess
    exit_code = ctypes.wintypes.DWORD()
    kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
    # 259 is the value of IS_ALIVE
    return exit_code.value == 259


def get_pid_from_handle(handle: int) -> int:
    # https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowthreadprocessid
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
    return pid.value


def get_all_wizard_handles() -> list:
    """
    Get handles to all currently open wizard clients
    """
    target_class = "Wizard Graphical Client"

    def callback(handle):
        class_name = ctypes.create_unicode_buffer(len(target_class))
        user32.GetClassNameW(handle, class_name, len(target_class) + 1)
        if target_class == class_name.value:
            return True

    return get_windows_from_predicate(callback)


def get_windows_from_predicate(predicate: Callable) -> list:
    """
    Get all windows that match a predicate

    Args:
        predicate: the predicate windows should pass

    Examples:
        .. code-block:: py

            def predicate(window_handle):
                if window_handle == 0:
                    # handle will be returned
                    return True
                else:
                    # handle will not be returned
                    return False
    """
    handles = []

    def callback(handle, _):
        if predicate(handle):
            handles.append(handle)

        # iterate all windows, (True)
        return 1

    enumwindows_func_type = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
    )

    callback = enumwindows_func_type(callback)
    user32.EnumWindows(callback, 0)

    return handles


# TODO: 2.0 move all these pharse functions to cache_handler, and rename them to parse instead of pharse
def pharse_template_id_file(file_data: bytes) -> dict:
    """
    Pharse a template id file's data
    """
    if not file_data.startswith(b"BINd"):
        raise RuntimeError("No BINd id string")

    data = zlib.decompress(file_data[0xD:])

    total_size = len(data)
    data = io.BytesIO(data)

    data.seek(0x24)

    out = {}
    while data.tell() < total_size:
        size = ord(data.read(1)) // 2

        string = data.read(size).decode()
        data.read(8)  # unknown bytes

        # Little endian int
        entry_id = struct.unpack("<i", data.read(4))[0]

        data.read(0x10)  # next entry

        out[entry_id] = string

    return out


def pharse_node_data(file_data: bytes) -> dict:
    """
    Converts data into a dict of node nums to points
    """
    entry_start = b"\xFE\xDB\xAE\x04"

    node_data = {}
    # no nodes
    if len(file_data) == 20:
        return node_data

    # header
    file_data = file_data[20:]

    last_start = 0
    while file_data:
        start = file_data.find(entry_start, last_start)
        if start == -1:
            break

        # fmt: off
        entry = file_data[start: start + 48 + 2]

        cords_data = entry[16: 16 + (4 * 3)]
        x = struct.unpack("<f", cords_data[0:4])[0]
        y = struct.unpack("<f", cords_data[4:8])[0]
        z = struct.unpack("<f", cords_data[8:12])[0]

        node_num = entry[48: 48 + 2]
        unpacked_num = struct.unpack("<H", node_num)[0]
        # fmt: on

        node_data[unpacked_num] = (x, y, z)

    return node_data


# implemented from https://github.com/PeechezNCreem/navwiz/
# this licence covers the below function
# Boost Software License - Version 1.0 - August 17th, 2003
#
# Permission is hereby granted, free of charge, to any person or organization
# obtaining a copy of the software and accompanying documentation covered by
# this license (the "Software") to use, reproduce, display, distribute,
# execute, and transmit the Software, and to prepare derivative works of the
# Software, and to permit third-parties to whom the Software is furnished to
# do so, all subject to the following:
#
# The copyright notices in the Software and this entire statement, including
# the above license grant, this restriction and the following disclaimer,
# must be included in all copies of the Software, in whole or in part, and
# all derivative works of the Software, unless such copies or derivative
# works are solely in the form of machine-executable object code generated by
# a source language processor.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE, TITLE AND NON-INFRINGEMENT. IN NO EVENT
# SHALL THE COPYRIGHT HOLDERS OR ANYONE DISTRIBUTING THE SOFTWARE BE LIABLE
# FOR ANY DAMAGES OR OTHER LIABILITY, WHETHER IN CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
def pharse_nav_data(file_data: bytes):
    file_data = file_data[2:]

    vertex_count_bytes = file_data[:4]
    file_data = file_data[4:]

    vertex_count = struct.unpack("<i", vertex_count_bytes)[0]

    vertices = []
    for idx in range(vertex_count):
        position_bytes = file_data[:12]
        file_data = file_data[12:]

        x, y, z = struct.unpack("<fff", position_bytes)
        vertices.append(XYZ(x, y, z))

        vertex_index_bytes = file_data[:2]
        file_data = file_data[2:]

        vertex_index = struct.unpack("<h", vertex_index_bytes)[0]

        if vertex_index != idx:
            raise RuntimeError(
                f"vertex index doesnt match expected: {idx} got: {vertex_index}"
            )

    edge_count_bytes = file_data[:4]
    file_data = file_data[4:]

    edge_count = struct.unpack("<i", edge_count_bytes)[0]

    edges = []
    for idx in range(edge_count):
        start_stop_bytes = file_data[:4]
        file_data = file_data[4:]

        start, stop = struct.unpack("<hh", start_stop_bytes)

        edges.append((start, stop))

    return vertices, edges


async def send_hotkey(window_handle: int, modifers: List[Keycode], key: Keycode):
    """
    Send a hotkey

    Args:
        window_handle: Handle to the window to send the hotkey to
        modifers: Keys to hold down
        key: The key to press
    """
    for modifier in modifers:
        user32.SendMessageW(window_handle, 0x100, modifier.value, 0)

    user32.SendMessageW(window_handle, 0x100, key.value, 0)
    user32.SendMessageW(window_handle, 0x101, key.value, 0)

    for modifier in modifers:
        user32.SendMessageW(window_handle, 0x101, modifier.value, 0)


async def timed_send_key(window_handle: int, key: Keycode, seconds: float):
    """
    Send a key for a number of seconds

    Args:
        window_handle: Handle to window to send key to
        key: The key to send
        seconds: Number of seconds to send the key
    """
    keydown_task = asyncio.create_task(_send_keydown_forever(window_handle, key))
    await asyncio.sleep(seconds)
    keydown_task.cancel()
    user32.SendMessageW(window_handle, 0x101, key.value, 0)


async def _send_keydown_forever(window_handle: int, key: Keycode):
    while True:
        user32.SendMessageW(window_handle, 0x100, key.value, 0)
        await asyncio.sleep(0.05)

# TODO: Can replace this with more generic one if needed, but only here for camera maths
def multiply3x3matrices(a: list[float], b: list[float]):
    result = [0.0] * 9

    for i in range(3):
        for j in range(3):
            for k in range(3):
                result[i * 3 + j] += a[i * 3 + k] * b[k * 3 + j]

    return result

def pitch_matrix(pitch: float):
    result = [0.0] * 9

    s = math.sin(pitch)
    c = math.cos(pitch)

    result[0] = c
    result[1] = s
    result[3] = -s
    result[4] = c
    result[8] = 1.0

    return result

def roll_matrix(roll: float):
    result = [0.0] * 9

    s = math.sin(roll)
    c = math.cos(roll)

    result[0] = 1.0
    result[4] = c
    result[5] = s
    result[7] = -s
    result[8] = c

    return result

def yaw_matrix(yaw: float):
    result = [0.0] * 9

    s = math.sin(yaw)
    c = math.cos(yaw)

    result[0] = c
    result[2] = -s
    result[4] = 1.0
    result[6] = s
    result[8] = c

    return result

def make_ypr_matrix(base, orientation: Orient):
    base = multiply3x3matrices(base, yaw_matrix(orientation.yaw))
    base = multiply3x3matrices(base, pitch_matrix(orientation.pitch))
    base = multiply3x3matrices(base, roll_matrix(orientation.roll))
    return base


def sign_extend(val: int) -> int:
    return (val & 0x7FFFFFFF) - (val & 0x80000000)

def make_string_id(x: str) -> int:
    # https://kronos-project.github.io/grimoire/internals/string-id.html
    hash = 0
    for idx, c in enumerate(x):
        val = ord(c) - 32
        shift = 5 * idx % 32

        hash ^= sign_extend(val << shift)
        if shift > 24:
            hash ^= sign_extend(val >> (32 - shift))
    return abs(hash) & 0xFFFF_FFFF
