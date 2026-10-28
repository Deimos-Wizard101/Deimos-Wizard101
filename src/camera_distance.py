"""Apply elastic-camera distance settings without changing follow behavior."""

import math


async def camera_distance_bounds(camera):
    from src.camera_wheel import wheel_bounds

    saved = await wheel_bounds(camera)
    if saved is not None:
        return saved
    return await camera.min_distance(), await camera.max_distance_target()


async def set_camera_distance(camera, *, distance=None, minimum=None, maximum=None, wheel=False):
    """Apply bounds before distance; optionally use them as scroll-wheel limits."""
    for value in (distance, minimum, maximum):
        if value is not None and (
            not math.isfinite(value) or not 1.401298464324817e-45 <= value <= 3.4028234663852886e38
        ):
            raise ValueError("Camera distances must be positive, finite float32 values.")

    if wheel:
        saved_low, saved_high = await camera_distance_bounds(camera)
    else:
        saved_low, saved_high = await camera.min_distance(), await camera.max_distance_target()
    low = saved_low if minimum is None else minimum
    high = saved_high if maximum is None else maximum
    if distance is not None:
        if minimum is None:
            low = min(low, distance)
        if maximum is None:
            high = max(high, distance)
    if not (math.isfinite(low) and math.isfinite(high) and 0 < low <= high <= 3.4028234663852886e38):
        raise ValueError("Dist Min must be positive and no greater than Dist Max.")
    if distance is not None and not low <= distance <= high:
        raise ValueError("Distance must be within Dist Min and Dist Max.")

    target = await camera.distance_target() if distance is None else distance
    if not math.isfinite(target):
        raise ValueError("The camera's requested distance must be finite.")
    bounded_target = max(low, min(target, high))

    if wheel:
        from src.camera_wheel import configure_wheel

        # A failed hook installation must not change the camera settings.
        await configure_wheel(camera, low, high)

    # The game eases max_distance toward max_distance_target each frame.
    await camera.write_max_distance_target(high)
    await camera.write_max_distance(high)
    await camera.write_min_distance(low)
    if distance is not None or bounded_target != target:
        await camera.write_distance_target(bounded_target)
        await camera.write_distance(bounded_target)
