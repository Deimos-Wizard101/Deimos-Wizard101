import ctypes
import ctypes.wintypes
import math

from wizwalker.constants import user32


async def get_camera_state(client):
    """
    Read all camera state needed for projection in one batch.

    Returns a dict with camera axes, frustum, screenport, and client size,
    or None if camera data is unavailable.
    """
    camera = await client.game_client.selected_camera_controller()
    cam_pos = await camera.position()

    gcam = await camera.gamebryo_camera()

    if gcam is None:
        return None

    view = await gcam.cam_view()

    if view is None:
        return None

    yaw = await camera.yaw()
    pitch = await camera.pitch()

    sin_y = math.sin(yaw)
    cos_y = math.cos(yaw)
    sin_p = math.sin(pitch)
    cos_p = math.cos(pitch)

    # Client area size in pixels
    client_rect = ctypes.wintypes.RECT()
    user32.GetClientRect(client.window_handle, ctypes.byref(client_rect))

    return {
        "cam_x": cam_pos.x,
        "cam_y": cam_pos.y,
        "cam_z": cam_pos.z,
        # Camera axes in world space (base × yaw_matrix × pitch_matrix)
        "fwd_x": -sin_y * cos_p,
        "fwd_y": -cos_y * cos_p,
        "fwd_z": -sin_p,
        "right_x": -cos_y,
        "right_y": sin_y,
        "right_z": 0.0,
        "up_x": -sin_y * sin_p,
        "up_y": -cos_y * sin_p,
        "up_z": cos_p,
        # Viewport frustum
        "vp_left": await view.viewport_left(),
        "vp_right": await view.viewport_right(),
        "vp_top": await view.viewport_top(),
        "vp_bottom": await view.viewport_bottom(),
        # Screenport
        "sp_left": await view.screenport_left(),
        "sp_right": await view.screenport_right(),
        "sp_top": await view.screenport_top(),
        "sp_bottom": await view.screenport_bottom(),
        # Client size
        "client_w": client_rect.right,
        "client_h": client_rect.bottom,
    }


def project_point(cam, x, y, z):
    """
    Project a world-space point using pre-fetched camera state.

    Returns (sx, sy) pixel tuple relative to the client area, or None if
    the point is behind the camera.
    """
    dx = x - cam["cam_x"]
    dy = y - cam["cam_y"]
    dz = z - cam["cam_z"]

    cam_right = cam["right_x"] * dx + cam["right_y"] * dy + cam["right_z"] * dz
    cam_up = cam["up_x"] * dx + cam["up_y"] * dy + cam["up_z"] * dz
    cam_forward = cam["fwd_x"] * dx + cam["fwd_y"] * dy + cam["fwd_z"] * dz

    if cam_forward <= 0:
        return None

    proj_x = cam_right / cam_forward
    proj_y = cam_up / cam_forward

    vp_w = cam["vp_right"] - cam["vp_left"]
    vp_h = cam["vp_top"] - cam["vp_bottom"]
    u = (proj_x - cam["vp_left"]) / vp_w if vp_w != 0 else 0.5
    v = (proj_y - cam["vp_bottom"]) / vp_h if vp_h != 0 else 0.5

    norm_x = cam["sp_left"] + u * (cam["sp_right"] - cam["sp_left"])
    norm_y = cam["sp_top"] + (1.0 - v) * (cam["sp_bottom"] - cam["sp_top"])

    sx = norm_x * cam["client_w"]
    sy = (1.0 - norm_y) * cam["client_h"]

    return (int(sx), int(sy))


async def world_to_screen(client, x, y, z):
    """
    Project a world-space point to screen-space pixel coordinates.

    Convenience wrapper that reads camera state and projects in one call.
    For projecting multiple points per frame, use get_camera_state() +
    project_point() instead.

    Returns (sx, sy) pixel tuple relative to the client area, or None if the
    point is behind the camera.
    """
    cam = await get_camera_state(client)

    if cam is None:
        return None

    return project_point(cam, x, y, z)
