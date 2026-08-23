"""Client window resizing — freeform, crisp, undistorted game-window resizing.

Pieces (Deimos runs out-of-process, but uses WizWalker's in-process asm hooks for
the one thing cross-process can't do — forcing the render backbuffer):

1. Window (ctypes): add a sizing border (WS_THICKFRAME) so the game window can be
   drag-resized. (A fat WM_NCHITTEST grab zone would need a WndProc subclass, which
   is process-local; the native border still works — grab right at the edge.)

2. Backbuffer (WizWalker asm hook — wizsprinter ResolutionForcer): on resize, force
   the D3D backbuffer to the new client size so the render is crisp (not stretched)
   AND so mouse/UI hit-testing stays correct (the game maps clicks against the
   backbuffer; a backbuffer != client mismatch offsets every click). We therefore
   keep window-client == backbuffer at all times.

3. Camera aspect (WizWalker memory): the 3D projection aspect comes from the engine
   view frustum, not the backbuffer, so we widen the CamView frustum to match the
   window aspect (keeping vertical FOV) → world fills any aspect undistorted.

On a drag (debounced to the final size): force backbuffer = WxH, re-assert the
window client to WxH (the engine's apply snaps the window to its old size), then
correct the frustum aspect. If the asm hook is unavailable/fails, it degrades to
resize + aspect-correct (render scales) without crashing.
"""
from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes

from loguru import logger

try:
    from wizwalker.extensions.wizsprinter.resolution_hook import ResolutionForcer
except Exception:  # pragma: no cover - keep the feature usable without the hook
    ResolutionForcer = None

try:
    # Needs keystone-engine; makes the window grab-resizable in-process.
    from wizwalker.extensions.wizsprinter.resolution_hook import WindowResizeBorder
except Exception:  # pragma: no cover
    WindowResizeBorder = None

RESIZE_MARGIN = 14  # px grab zone at the window edges

# ---- Win32 (cross-process safe: GWL_STYLE, SetWindowPos, Get*Rect) ----
user32 = ctypes.WinDLL("user32", use_last_error=True)
LONG_PTR = ctypes.c_longlong

user32.GetWindowLongPtrW.restype = LONG_PTR
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = LONG_PTR
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.AdjustWindowRectEx.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.IsWindow.argtypes = [wintypes.HWND]

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_THICKFRAME = 0x00040000
WS_MAXIMIZEBOX = 0x00010000
WS_CAPTION = 0x00C00000
WS_BORDER = 0x00800000
WS_DLGFRAME = 0x00400000
WS_MINIMIZEBOX = 0x00020000
# Decorations stripped for borderless mode: the title bar / caption only.
# WS_THICKFRAME is deliberately KEPT: DefWindowProc only enables resizing (SC_SIZE)
# on a sizable window, so it is what lets the WndProc hit-test hook drag-resize the
# window. The thick sizing border it would normally draw is made INVISIBLE by the
# WndProc's WM_NCCALCSIZE handler (frameless flag) — so the window ends up both
# borderless (no title bar, no visible frame) and drag-resizable. If the WndProc
# hook is unavailable, the manager strips WS_THICKFRAME too so the window is still
# visually borderless (just not resizable) — see _SIZING_FRAME / ClientResizingManager.
_BORDERLESS_STRIP = WS_CAPTION | WS_BORDER | WS_DLGFRAME | WS_MINIMIZEBOX
# The sizing-frame bits the manager removes for the unresizable fallback above.
_SIZING_FRAME = WS_THICKFRAME | WS_MAXIMIZEBOX
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

# Stability ticks before acting on a new size (debounce drag -> final size).
_STABLE_TICKS = 2


def _client_size(hwnd: int):
    r = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(r)):
        return None
    return (r.right - r.left, r.bottom - r.top)


def _style(hwnd: int, idx: int) -> int:
    return int(user32.GetWindowLongPtrW(hwnd, idx)) & 0xFFFFFFFF


def _outer_size(hwnd: int, w: int, h: int, borderless: bool):
    """Window (outer) size that yields a w x h CLIENT area for this window's style.

    A frameless borderless window has its non-client area zeroed by the WndProc
    WM_NCCALCSIZE handler, so client == window: use w x h directly. AdjustWindowRectEx
    doesn't know about that override and would wrongly add the WS_THICKFRAME inset.
    """
    if borderless:
        return w, h
    style = _style(hwnd, GWL_STYLE)
    ex = _style(hwnd, GWL_EXSTYLE)
    r = wintypes.RECT(0, 0, w, h)
    user32.AdjustWindowRectEx(ctypes.byref(r), style, False, ex)
    return r.right - r.left, r.bottom - r.top


def set_client_size(hwnd: int, w: int, h: int, borderless: bool = False):
    """Resize so the window's CLIENT area is exactly w x h (keeps position)."""
    ow, oh = _outer_size(hwnd, w, h, borderless)
    user32.SetWindowPos(hwnd, 0, 0, 0, ow, oh,
                        SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE)


def set_window_placement(hwnd: int, x: int, y: int, w: int, h: int, borderless: bool = False):
    """Move the window to (x, y) and make its CLIENT area exactly w x h."""
    ow, oh = _outer_size(hwnd, w, h, borderless)
    # SWP_FRAMECHANGED for borderless: re-trigger WM_NCCALCSIZE so the hook's frameless
    # return (client == window) takes effect — the frame isn't dropped until a reflow.
    flags = SWP_NOZORDER | SWP_NOACTIVATE | (SWP_FRAMECHANGED if borderless else 0)
    user32.SetWindowPos(hwnd, 0, int(x), int(y), ow, oh, flags)


# NOTE: applying a per-account window config at launch is a METHOD on
# ClientResizingManager (apply_account_window) rather than a free function, so it
# reuses the manager's single per-client ResolutionForcer. A second, independent
# forcer would pattern-scan setMode *after* the manager already hooked it (its
# entry is now a jump, not the original bytes) and fail with PatternFailed.


class _ArmState:
    __slots__ = ("orig_style", "last_size")

    def __init__(self, orig_style: int):
        self.orig_style = orig_style
        self.last_size = None


_armed: dict[int, _ArmState] = {}
# hwnd -> original style, for windows currently forced borderless.
_borderless: dict[int, int] = {}


def is_armed(hwnd: int) -> bool:
    return hwnd in _armed


def set_borderless(hwnd: int, on: bool) -> bool:
    """Strip (or restore) the window's title bar / caption.

    Self-healing and idempotent: safe to call every tick. When `on`, it re-strips
    the caption only if it has reappeared (e.g. the client restyles its window on a
    state transition / device init), so a borderless window stays caption-less
    without flickering on every call. The original style is remembered the first
    time so it can be restored when `on` is False.

    WS_THICKFRAME is left untouched here (kept for drag-resize); the manager arms it
    and the WndProc WM_NCCALCSIZE handler hides the frame — see _BORDERLESS_STRIP.
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    try:
        if on:
            style = _style(hwnd, GWL_STYLE)
            if hwnd not in _borderless:
                _borderless[hwnd] = style & 0xFFFFFFFF
            desired = style & ~_BORDERLESS_STRIP
            if desired == style:
                return True            # already frameless — no SetWindowPos (no flicker)
            user32.SetWindowLongPtrW(hwnd, GWL_STYLE, desired)
        else:
            orig = _borderless.pop(hwnd, None)
            if orig is None:
                return False
            user32.SetWindowLongPtrW(hwnd, GWL_STYLE, orig)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                            SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
        return True
    except Exception as e:
        logger.opt(exception=e).warning(f"[client_resizing] set_borderless failed {hwnd:#x}")
        return False


def arm_window(hwnd: int) -> bool:
    """Ensure the game window has a sizing border so it can be drag-resized.

    Self-healing: called every tick, it re-adds WS_THICKFRAME if it has gone missing
    (e.g. the game/another tool reset the style), remembering the original style the
    first time so it can be restored on disarm.
    """
    if not hwnd:
        return False
    try:
        style = _style(hwnd, GWL_STYLE)
        if style & WS_THICKFRAME:
            # Already has a sizing border; record the pre-arm style once.
            if hwnd not in _armed:
                _armed[hwnd] = _ArmState(style & ~WS_THICKFRAME)
            return True
        # Missing the sizing border — add it (and remember the original once).
        if hwnd not in _armed:
            _armed[hwnd] = _ArmState(style)
            logger.debug(f"[client_resizing] armed window {hwnd:#x}")
        user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style | WS_THICKFRAME | WS_MAXIMIZEBOX)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                            SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
        return True
    except Exception as e:
        logger.opt(exception=e).warning(f"[client_resizing] failed to arm {hwnd:#x}")
        return False


def disarm_window(hwnd: int):
    """Restore the original window style (removes the sizing border)."""
    state = _armed.pop(hwnd, None)
    if state is None:
        return
    try:
        if user32.IsWindow(hwnd):
            user32.SetWindowLongPtrW(hwnd, GWL_STYLE, state.orig_style)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
    except Exception as e:
        logger.opt(exception=e).debug(f"[client_resizing] disarm error {hwnd:#x}")


def strip_sizing_frame(hwnd: int):
    """Remove the WS_THICKFRAME sizing border (and its maximize box).

    Fallback for borderless windows when the WndProc WM_NCCALCSIZE hook (which would
    otherwise hide the frame while keeping it resizable) is unavailable — without the
    frame hidden, the only way to stay visually borderless is to drop the frame, at
    the cost of drag-resize. Idempotent; no SetWindowPos unless something changes.
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return
    style = _style(hwnd, GWL_STYLE)
    if not (style & _SIZING_FRAME):
        return
    try:
        user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style & ~_SIZING_FRAME)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                            SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
    except Exception as e:
        logger.opt(exception=e).debug(f"[client_resizing] strip_sizing_frame error {hwnd:#x}")


def reflow_frame_if_framed(hwnd: int):
    """If a borderless window still shows a frame (client != window), trigger one
    SWP_FRAMECHANGED so the WndProc WM_NCCALCSIZE hook drops it.

    Needed because the frame isn't recomputed until a frame-changed reflow, and the
    hook's frameless flag may go live (hook install / client restyle) after the last
    one. Fires only while a frame is present, so it stops once frameless (no flicker).
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return
    cs = _client_size(hwnd)
    r = wintypes.RECT()
    if not cs or not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return
    if cs != (r.right - r.left, r.bottom - r.top):     # frame still present
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                            SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)


def _sane_frustum(l: float, r: float, t: float, b: float) -> bool:
    """Reject garbage so we never write extents to a mis-identified pointer."""
    import math
    if not all(math.isfinite(v) and abs(v) < 1e4 for v in (l, r, t, b)):
        return False
    return (r - l) > 1e-5 and (t - b) > 1e-5


async def _add_ctrl_view(views: dict, client, ctrl):
    """Resolve a controller's frustum, validate it, and add it to `views`."""
    if ctrl is None:
        return
    try:
        gcam = await ctrl.gamebryo_camera()
        if gcam is None:
            return
        view = await gcam.cam_view()
        if view is None or view.base_address in views:
            return
        l = await view.viewport_left(); r = await view.viewport_right()
        t = await view.viewport_top(); b = await view.viewport_bottom()
        if _sane_frustum(l, r, t, b):
            views[view.base_address] = view
    except Exception:
        return


async def _all_cam_views(client):
    """Every distinct camera-controller frustum (selected, free, elastic, combat).

    The game keeps a separate camera controller per mode and only the *active*
    one's frustum drives the render, so on a camera switch the new controller's
    (uncorrected, native 16:9) frustum takes over and the 3D view distorts again.
    The combat camera has no wizwalker getter — it sits one pointer-slot below
    `selected` in the same contiguous block of controllers — so we read it directly
    (anchored on the pattern-scanned `selected` offset, not a hardcoded address).
    Deduped by frustum (CamView) address; each frustum is sanity-checked.
    """
    from wizwalker.memory.memory_object import Primitive
    from wizwalker.memory.memory_objects.camera_controller import DynamicCameraController

    gc = client.game_client
    views = {}
    # Named controllers (these calls also populate the offset cache used below).
    for getter in (gc.selected_camera_controller, gc.free_camera_controller,
                   gc.elastic_camera_controller):
        try:
            await _add_ctrl_view(views, client, await getter())
        except Exception:
            continue
    # Unnamed controllers in the same block (combat/cinematic). Scan the slots just
    # below `selected`; validation filters out non-controller (garbage) slots.
    try:
        sel_off = gc._offset_lookup_cache.get("selected_camera_controller")
        if sel_off:
            for off in range(sel_off - 0x30, sel_off, 8):
                try:
                    addr = await gc.read_value_from_offset(off, Primitive.int64)
                except Exception:
                    continue
                if addr and addr > 0x10000:
                    await _add_ctrl_view(views, client, DynamicCameraController(client.hook_handler, addr))
    except Exception:
        pass
    return views


NATIVE_ASPECT = 16.0 / 9.0   # the engine's design aspect (its native frustum is 16:9)
# Per frustum: ``(v_ref, left, right, top, bottom)`` as first seen — the native vertical
# half-extent (the frustum's vertical FOV, which is constant — zoom is camera distance,
# not FOV) plus the untouched extents, so a teardown can put the frustum back exactly as
# the game had it. Nested: hwnd -> {cam_view_address: tuple}. Keyed per frustum because
# each camera controller has its own (and possibly its own FOV).
#
# Restoring on teardown is not cosmetic. The capture below assumes first-seen == native,
# so leaving a corrected frustum behind makes the NEXT capture read our own corrected
# value as "native". For a window narrower than 16:9 the correction grows the vertical
# extent, so each hook/unhook cycle multiplies it by (16/9)/aspect again and the POV
# creeps further back every time.
_native_views: dict[int, dict[int, tuple]] = {}


async def _correct_view(view, aspect: float, refs: dict) -> bool:
    """Apply the window aspect to a single frustum, anchored on its native FOV."""
    try:
        ref = refs.get(view.base_address)
        if ref is None:
            # First time we see this frustum: capture its native extents. The engine
            # leaves inactive controllers at native 16:9, so first-seen is native (that
            # is exactly why an unfixed controller looks distorted).
            top = await view.viewport_top()
            bottom = await view.viewport_bottom()
            left = await view.viewport_left()
            right = await view.viewport_right()
            v_ref = (top - bottom) / 2.0
            if v_ref <= 0:
                return False
            ref = (v_ref, left, right, top, bottom)
            refs[view.base_address] = ref
        v_ref = ref[0]

        if aspect >= NATIVE_ASPECT:          # wider than native -> grow horizontal
            v = v_ref
            h = v_ref * aspect
        else:                                # taller/narrower -> grow vertical
            h = v_ref * NATIVE_ASPECT
            v = h / aspect
        await view.write_viewport_top(v)
        await view.write_viewport_bottom(-v)
        await view.write_viewport_left(-h)
        await view.write_viewport_right(h)
        return True
    except Exception:
        return False


async def correct_aspect(client, hwnd: int) -> bool:
    """Match EVERY camera controller's frustum to the window aspect (both extents).

    The frustum aspect = horizontal_extent / vertical_extent must equal the window
    W/H or the 3D view distorts. Anchored on each frustum's native vertical FOV, we
    expand the dimension that exceeds the native 16:9 aspect: wider windows widen the
    horizontal extent, taller/narrower windows grow the vertical extent. Applied to
    the selected, free, and combat/elastic controllers so switching cameras keeps the
    correction (run every tick, so a switch is reflected within a tick).
    """
    size = _client_size(hwnd)
    if not size or size[1] <= 0:
        return False
    aspect = size[0] / size[1]
    views = await _all_cam_views(client)
    if not views:
        return False
    refs = _native_views.setdefault(hwnd, {})
    ok = False
    for view in views.values():
        ok = await _correct_view(view, aspect, refs) or ok
    return ok


async def restore_aspect(client, hwnd: int) -> bool:
    """Put every frustum we corrected back to the extents captured when we first saw it.

    Must run before the captured extents are dropped, and while the client is still
    alive — otherwise the corrected frustum is what the next hook reads as native and
    the POV compounds (see ``_native_views``). Best-effort: a controller that isn't
    reachable right now keeps its corrected frustum, so we only restore what we can
    still see. Returns True if anything was written back.
    """
    refs = _native_views.get(hwnd)
    if not refs or client is None:
        return False
    try:
        views = await _all_cam_views(client)
    except Exception:
        return False
    ok = False
    for addr, view in views.items():
        ref = refs.get(addr)
        if ref is None:
            continue
        _v_ref, left, right, top, bottom = ref
        try:
            await view.write_viewport_top(top)
            await view.write_viewport_bottom(bottom)
            await view.write_viewport_left(left)
            await view.write_viewport_right(right)
            ok = True
        except Exception:
            continue
    if ok:
        logger.debug(f"[client_resizing] camera frustum restored {hwnd:#x}")
    return ok


class ClientResizingManager:
    """Per-client freeform resizing: a sizing border, crisp backbuffer forcing
    (in-process asm hook) keeping window==backbuffer, and camera-aspect correction.

    Call tick(clients, enabled) periodically.
    """

    def __init__(self):
        self._enabled = False
        self._forcers: dict[int, object] = {}     # hwnd -> ResolutionForcer
        self._borders: dict[int, object] = {}      # hwnd -> WindowResizeBorder
        self._pending: dict[int, tuple] = {}       # hwnd -> (size, stable_count)
        # hwnd -> the client we last serviced, kept only so _teardown can write the
        # camera frustum back (that needs memory access, and teardown is keyed by hwnd).
        # Dropped in _teardown, so it never outlives the hooks it belongs to.
        self._clients: dict[int, object] = {}
        # Handles whose window/resolution/border config was applied at launch
        # (before activate_hooks). The tick loop must NOT tear these down just
        # because they aren't hooked yet (not in walker.clients); they're kept
        # alive until the window closes (drop_keep_alive on stale cleanup / kill).
        self._keep_alive: set[int] = set()
        # PER-CLIENT install locks (keyed by hwnd). A lock only needs to stop the
        # tick loop and a launch-time apply from BOTH installing a hook for the SAME
        # client (a double setMode hook -> the second one's pattern scan fails). A
        # single global lock would also serialize installs across DIFFERENT clients —
        # and each install pattern-scans + waits up to ~3s for the video manager — so
        # N clients would hook back-to-back. Per-hwnd locks let distinct clients hook
        # concurrently while still guarding each client against a double install.
        self._install_locks: dict[int, asyncio.Lock] = {}
        # Latched on app close / pre-update relaunch so a tick that is still in
        # flight (or fires during cancellation) can't re-arm hooks after we've torn
        # them down — the shutdown teardown must be the last word.
        self._shutdown = False

    def drop_keep_alive(self, hwnd: int):
        """Stop protecting a launch-managed handle (window closed / client killed)."""
        self._keep_alive.discard(hwnd)

    def _install_lock(self, hwnd: int) -> asyncio.Lock:
        """The per-client install lock for `hwnd` (created on first use). Creating
        the entry is a single synchronous dict op, so concurrent callers for the same
        hwnd resolve to the same lock without a race."""
        lock = self._install_locks.get(hwnd)
        if lock is None:
            lock = asyncio.Lock()
            self._install_locks[hwnd] = lock
        return lock

    async def tick(self, clients, enabled: bool):
        if self._shutdown:
            return
        if not enabled:
            if self._enabled:
                self._enabled = False
                await self._teardown_all()
            return
        self._enabled = True

        # Collect the live windows first, then service them all CONCURRENTLY so a
        # slow install on one client (hook pattern scan + up to ~3s waiting for the
        # video manager to be captured) doesn't hold up the others — every client's
        # hooks come up in parallel instead of back-to-back. Per-client state is keyed
        # by hwnd, so concurrent servicing never touches another client's entries.
        live_pairs = []
        for client in clients:
            hwnd = getattr(client, "window_handle", 0)
            if not hwnd or not user32.IsWindow(hwnd):
                continue
            live_pairs.append((client, hwnd))
        live = {hwnd for _, hwnd in live_pairs}

        if live_pairs:
            await asyncio.gather(
                *(self._service_client(client, hwnd) for client, hwnd in live_pairs)
            )

        # A kept-alive window that has since closed must stop being protected.
        for hwnd in list(self._keep_alive):
            if not user32.IsWindow(hwnd):
                self._keep_alive.discard(hwnd)

        # _native_views is in the union so a client whose only change was the camera
        # correction (no forcer/border installed) still gets its frustum restored.
        for hwnd in set(self._forcers) | set(self._borders) | set(_armed) | set(_native_views):
            if hwnd not in live and hwnd not in self._keep_alive:
                await self._teardown(hwnd)

    async def _service_client(self, client, hwnd: int):
        """Install/heal one client's resize hooks and correct its aspect for a single
        tick. Every touched piece of state is keyed by this hwnd, so it is safe to run
        concurrently for several clients; a failure is logged and isolated so it never
        aborts the other clients' servicing."""
        try:
            self._clients[hwnd] = client   # for the frustum restore in _teardown
            await self._ensure_forcer(client, hwnd)
            await self._ensure_border(client, hwnd)
            if hwnd in _borderless:
                set_borderless(hwnd, True)     # self-heal: re-strip caption if the client restyled
                if self._borders.get(hwnd) is not None:
                    arm_window(hwnd)           # WS_THICKFRAME; the NCCALCSIZE hook hides the frame
                    await self._update_border(hwnd)   # push the frameless flag before the reflow
                    reflow_frame_if_framed(hwnd)      # drop the (now-hidden) frame if still shown
                else:
                    strip_sizing_frame(hwnd)   # no hook to hide a frame -> stay frameless (unresizable)
                    await self._update_border(hwnd)
            else:
                arm_window(hwnd)
                await self._update_border(hwnd)
            await self._handle_resize(client, hwnd)
            # Re-assert the aspect fix on every controller each tick so switching
            # cameras (free / combat) reflects it within a tick, even with no resize.
            await correct_aspect(client, hwnd)
        except Exception as e:
            logger.opt(exception=e).debug(f"[client_resizing] service tick error {hwnd:#x}")

    async def _ensure_forcer(self, client, hwnd: int):
        if ResolutionForcer is None or hwnd in self._forcers:
            return
        async with self._install_lock(hwnd):
            if hwnd in self._forcers:          # re-check after acquiring the lock
                return
            try:
                forcer = ResolutionForcer(client)
                await forcer.install()
                self._forcers[hwnd] = forcer
                logger.debug(f"[client_resizing] resolution hook installed {hwnd:#x}")
            except Exception as e:
                logger.opt(exception=e).warning(f"[client_resizing] resolution hook unavailable {hwnd:#x}")

    async def apply_account_window(self, client, hwnd: int, x: int, y: int, w: int, h: int,
                                   res_w: int, res_h: int, locked: bool,
                                   borderless: bool = False) -> bool:
        """Apply the WINDOW half of a saved per-account config — everything that
        needs no in-game camera, so it can run at launch (before hooks / player
        select): borderless frame, sizing border, crisp resolution forcing, resize
        hit-test hook, and placement. The camera frustum is applied separately by
        the per-tick correct_aspect once the in-game camera exists (after hooks).

        Reuses the manager's single per-client forcer/border (see note above) and
        keeps the handle alive so the tick loop won't tear those hooks down while
        the client is launched-but-not-yet-hooked."""
        if not hwnd or not user32.IsWindow(hwnd):
            return False
        borderless = bool(borderless)
        self._clients[hwnd] = client   # so a teardown before the first tick can restore
        # Strip the caption first so the client-area sizing below accounts for it.
        set_borderless(hwnd, borderless)
        await self._ensure_forcer(client, hwnd)
        forcer = self._forcers.get(hwnd)
        if forcer is not None:
            try:
                for _ in range(15):            # wait for the video-manager capture
                    if await forcer._manager_address():
                        break
                    await asyncio.sleep(0.2)
                await forcer.force(res_w, res_h)
                await asyncio.sleep(0.4)        # let the engine run its apply
            except Exception as e:
                logger.opt(exception=e).debug(f"[client_resizing] launch force failed {hwnd:#x}")
        await self._ensure_border(client, hwnd)    # in-process WndProc hook (resize + frameless)
        # Sizing border so the window is drag-resizable. A borderless window keeps it
        # only when the WndProc hook is present to hide the frame (WM_NCCALCSIZE);
        # otherwise drop it so the window is at least visually borderless.
        if not borderless or self._borders.get(hwnd) is not None:
            arm_window(hwnd)
        elif borderless:
            strip_sizing_frame(hwnd)
        await self._update_border(hwnd)            # push rect + frameless flag before placing
        try:
            set_window_placement(hwnd, x, y, w, h, borderless=borderless)
        except Exception:
            pass
        self._keep_alive.add(hwnd)             # protect these hooks until the window closes
        return True

    async def _ensure_border(self, client, hwnd: int):
        # The in-process WndProc hit-test hook that makes the window grab-resizable.
        # Lock-serialized (like _ensure_forcer) so a launch-time apply and the tick
        # loop can't both install the hook for the same client.
        if WindowResizeBorder is None or hwnd in self._borders:
            return
        async with self._install_lock(hwnd):
            if hwnd in self._borders:          # re-check after acquiring the lock
                return
            try:
                border = WindowResizeBorder(client)
                await border.install()
                self._borders[hwnd] = border
                logger.debug(f"[client_resizing] resize-border hook installed {hwnd:#x}")
            except Exception as e:
                logger.opt(exception=e).warning(f"[client_resizing] resize-border hook unavailable {hwnd:#x}")

    async def _update_border(self, hwnd: int):
        # Keep the hit-test hook's window rect current (cursor is hit-tested against it).
        border = self._borders.get(hwnd)
        if border is None:
            return
        r = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(r)):
            try:
                await border.update_rect(r.left, r.top, r.right, r.bottom, RESIZE_MARGIN,
                                         frameless=hwnd in _borderless)
            except Exception:
                pass

    async def _handle_resize(self, client, hwnd: int):
        state = _armed.get(hwnd)
        if state is None:
            return
        cur = _client_size(hwnd)
        if not cur or cur[1] <= 0:
            return
        if cur == state.last_size:
            self._pending.pop(hwnd, None)
            return

        # Debounce: only act once the size has settled (drag finished).
        psize, count = self._pending.get(hwnd, (None, 0))
        count = count + 1 if cur == psize else 0
        self._pending[hwnd] = (cur, count)
        if count < _STABLE_TICKS:
            return

        w, h = cur
        forcer = self._forcers.get(hwnd)
        forced = False
        if forcer is not None:
            try:
                forced = await forcer.force(w, h)
            except Exception as e:
                logger.opt(exception=e).debug(f"[client_resizing] force failed {hwnd:#x}")
                forced = False

        if forced:
            # The engine's apply snaps the window to its descriptor size — re-assert
            # the dragged size so window-client == backbuffer (crisp + clicks correct).
            await asyncio.sleep(0.25)
            try:
                set_client_size(hwnd, w, h, borderless=hwnd in _borderless)
            except Exception:
                pass
            await correct_aspect(client, hwnd)
            state.last_size = _client_size(hwnd)
            self._pending.pop(hwnd, None)
        else:
            # No backbuffer force (hook unavailable / not ready): still correct the
            # aspect so the (stretched) render isn't distorted. Retry forcing later.
            await correct_aspect(client, hwnd)
            if forcer is None or ResolutionForcer is None:
                state.last_size = cur
                self._pending.pop(hwnd, None)

    async def _teardown(self, hwnd: int):
        # Undo the camera correction FIRST, while the window and client are still in the
        # state we corrected them from. Leaving it applied would make the next hook read
        # our corrected frustum as the native one and push the POV back again.
        client = self._clients.pop(hwnd, None)
        if client is not None and user32.IsWindow(hwnd):
            try:
                await restore_aspect(client, hwnd)
            except Exception as e:
                logger.opt(exception=e).debug(
                    f"[client_resizing] frustum restore failed {hwnd:#x}"
                )
        for store in (self._forcers, self._borders):
            hook = store.pop(hwnd, None)
            if hook is not None:
                try:
                    await hook.uninstall()
                except Exception:
                    pass
        disarm_window(hwnd)
        if hwnd in _borderless:
            set_borderless(hwnd, False)     # restore decorations
        _borderless.pop(hwnd, None)         # guard against a leak if window is gone
        self._pending.pop(hwnd, None)
        _native_views.pop(hwnd, None)
        # Drop the per-client install lock unless an install is mid-flight holding it.
        lk = self._install_locks.get(hwnd)
        if lk is not None and not lk.locked():
            self._install_locks.pop(hwnd, None)

    async def _teardown_all(self):
        for hwnd in (set(self._forcers) | set(self._borders) | set(_armed)
                     | set(_borderless) | set(_native_views)):
            await self._teardown(hwnd)

    async def teardown_client(self, hwnd: int):
        """Restore every hook for a SINGLE client (e.g. the GUI 'Unhook' button).

        MUST run while that client is still alive: ``client.close()`` rewrites the
        shared hook codecave, so any resolution/resize jump still patched into the
        game's code would dangle and crash the game the next time it is hit. Also
        stops protecting a launch-managed handle so the tick loop won't re-arm it.
        """
        self.drop_keep_alive(hwnd)
        await self._teardown(hwnd)

    async def shutdown(self):
        """Tear down every hook for good (app close / pre-update relaunch).

        MUST run while the game clients are still alive: the resolution-forcer and
        resize-border asm hooks patch the game's own code and are NOT tracked by the
        client's hook_handler, so ``client.close()`` won't restore them — only their
        ``uninstall()`` rewrites the original bytes. Latches ``_shutdown`` first so a
        concurrently-cancelling tick loop can't re-arm anything after this runs.
        """
        self._shutdown = True
        self._enabled = False
        await self._teardown_all()
