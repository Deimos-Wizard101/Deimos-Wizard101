import asyncio
import regex
from contextlib import suppress

from wizwalker.memory.memory_objects.enums import WindowFlags
from wizwalker.utils import maybe_wait_for_value_with_timeout


_friend_list_entry = regex.compile(
    r"<Y;\d+><X;\d+><indent;0><Color;[\w\d]+><left>"
    r"<icon;FriendsList/Friend_Icon_List_0(?P<icon_list>[12])\."
    r"dds;\d+;\d+;(?P<icon_index>\d+)></left><Y;(?P<name_y>[-\d]+)><X;(?P<name_x>[-\d]+)>"
    r"<indent;\d+><Color;[\d\w]+>(<left>)?<COLOR;[\w\d]+>(?P<name>[\w ]+)"
)


async def paint_window_for(window, time: float = 2):
    """
    Paint a window for a number of seconds

    Args:
        window: The window to paint
        time: How long to paint the window
    """

    async def _paint_task():
        with suppress(asyncio.CancelledError):
            while True:
                await window.debug_paint()

    paint_task = asyncio.create_task(_paint_task())
    await asyncio.sleep(time)
    paint_task.cancel()


async def _maybe_get_named_window(parent, name: str, retries: int = 4):
    async def _try_do(callback, *args, **kwargs):
        while True:
            res = await callback(*args, **kwargs)

            if not res:
                nonlocal retries
                if retries <= 0:
                    return res

                retries -= 1
                await asyncio.sleep(0.4)

            else:
                return res

    possible = await _try_do(parent.get_windows_with_name, name)

    if not possible:
        raise ValueError(f"No child window named {name}")

    if len(possible) > 1:
        raise ValueError(f"Multiple results for {name}")

    return possible[0]


async def _cycle_to_online_friends(client, friends_list):
    list_label = await _maybe_get_named_window(friends_list, "lblFriendsList")

    async def _get_text():
        current_text = await list_label.maybe_text()

        if current_text is None:
            raise Exception("Friend's list has no label")

        return current_text.replace("<center>", "").replace("</center>", "")

    right_button = await _maybe_get_named_window(friends_list, "btnListTypeRight")

    while (current_page := await _get_text()) != "Online Friends":
        await client.mouse_handler.click_window(right_button)
        await maybe_wait_for_value_with_timeout(
            _get_text, value=current_page, inverse_value=True, timeout=5
        )


async def _cycle_friends_list(
    client, right_button, friends_list, icon, icon_list, name, current_page
):
    list_text = await friends_list.maybe_text()

    match = None
    idx = 0

    for idx, friend_entry in enumerate(list(_friend_list_entry.finditer(list_text))):
        friend_icon = int(friend_entry.group("icon_index"))
        friend_icon_list = int(friend_entry.group("icon_list"))
        friend_name = friend_entry.group("name")

        if icon is not None and icon_list is not None and name:
            if (
                friend_icon == icon
                and friend_icon_list == icon_list
                and friend_name == name
            ):
                match = friend_entry
                break

        elif icon is not None and icon_list is not None:
            if friend_icon == icon and friend_icon_list == icon_list:
                match = friend_entry
                break

        elif name:
            if friend_name == name:
                match = friend_entry
                break

        else:
            raise RuntimeError("Invalid args")

    if match:
        target_page = (idx // 10) + 1

        if target_page != current_page:
            for _ in range(target_page - current_page):
                await client.mouse_handler.click_window(right_button)

    return match, idx


async def _click_on_friend(client, friends_list, friend_index):
    scaled_rect = await friends_list.scale_to_client()
    ui_scale = await client.render_context.ui_scale()

    # 12 % 10 = 2 * 30 = 60 * ui_scale
    scaled_friend_name_y = ((friend_index % 10) * 30) * ui_scale

    scaled_rect_center = scaled_rect.center()
    click_x = scaled_rect_center[0]
    # 15 is half the size of each entry's click area
    click_y = int(scaled_rect.y1 + scaled_friend_name_y + (15 * ui_scale))

    await client.mouse_handler.click(click_x, click_y)
    await asyncio.sleep(1)


async def _teleport_to_friend(client, character_window):
    teleport_button = await _maybe_get_named_window(character_window, "btnGoToFriend")
    await client.mouse_handler.click_window(teleport_button)
    # wait for confirmation window
    await asyncio.sleep(1)

    confirmation_window = await _maybe_get_named_window(
        client.root_window, "MessageBoxModalWindow"
    )
    yes_button = await _maybe_get_named_window(confirmation_window, "centerButton")

    close_button = await _maybe_get_named_window(character_window, "btnCharacterClose")

    await client.mouse_handler.click_window(yes_button)
    # we need to click the close button within the 1 second of the teleport animation
    await client.mouse_handler.click_window(close_button)


# TODO: add error if friend is busy message pops up
async def teleport_to_friend_from_list(
    client, *, icon_list: int = None, icon_index: int = None, name: str = None
):
    """
    Teleport to a friend from the client's friend list

    Args:
        client: Client to teleport
        icon_list: Icon list the icon is from (1 or 2) or None
        icon_index: Index of the icon or None
        name: Name of the player or None
    """
    if (
        icon_list is None
        and icon_index is not None
        or icon_list is not None
        and icon_index is None
    ):
        raise ValueError("Icon list and icon index must both be defined or not defined")

    if all(i is None for i in (icon_list, icon_index, name)):
        raise ValueError("Must specify icon_list and icon_index or name or all")

    try:
        friends_window = await _maybe_get_named_window(
            client.root_window, "NewFriendsListWindow"
        )
    except ValueError:
        # friend's list isn't open so open it
        friend_button = await _maybe_get_named_window(client.root_window, "btnFriends")
        await client.mouse_handler.click_window(friend_button)

        friends_window = await _maybe_get_named_window(
            client.root_window, "NewFriendsListWindow"
        )
    else:
        if not await friends_window.is_visible():
            # friend's list isn't open so open it
            friend_button = await _maybe_get_named_window(client.root_window, "btnFriends")
            await client.mouse_handler.click_window(friend_button)

    await _cycle_to_online_friends(client, friends_window)

    friends_list_window = await _maybe_get_named_window(friends_window, "listFriends")
    friends_list_text = await friends_list_window.maybe_text()

    # no friends online
    if not friends_list_text:
        raise ValueError("No friends online")

    right_button = await _maybe_get_named_window(friends_window, "btnArrowDown")
    page_number = await _maybe_get_named_window(friends_window, "PageNumber")

    page_number_text = await page_number.maybe_text()

    current_page, _ = map(
        int,
        page_number_text.replace("<center>", "")
        .replace("</center>", "")
        .replace(" ", "")
        .split("/"),
    )

    friend, friend_index = await _cycle_friends_list(
        client,
        right_button,
        friends_list_window,
        icon_index,
        icon_list,
        name,
        current_page,
    )

    if friend is None:
        raise ValueError(
            f"Could not find friend with icon {icon_index} icon list {icon_list} and/or name {name}"
        )

    await _click_on_friend(client, friends_list_window, friend_index)

    character_window = await _maybe_get_named_window(client.root_window, "wndCharacter")
    await _teleport_to_friend(client, character_window)

    # close friends window
    await friends_window.write_flags(WindowFlags.disabled)
