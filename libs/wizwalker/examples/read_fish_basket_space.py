import asyncio

from wizwalker import ClientHandler, Keycode


async def read_fish_basket(client):
    # fish basket window must be open
    await client.send_key(Keycode.V)

    # to find this window you can use await client.root_window.debug_print_ui_tree()
    # window that contains the fish current space used and max space
    possiple_windows = await client.root_window.get_windows_with_name("inventorySpace")

    if not possiple_windows:
        print("Couldn't find the space used!")

    fish_space_window = possiple_windows[0]
    # get the actual text from the fish window
    # should be something like "<center>5/100"
    fish_space_text = await fish_space_window.maybe_text()

    # remove the <center> formatting and split on the /
    fish_space_used, fish_space_max = fish_space_text.replace("<center>", "").split("/")

    print(f"{fish_space_used=} {fish_space_max=}")


async def main():
    handler = ClientHandler()
    client = handler.get_new_clients()[0]

    try:
        print("Preparing")
        # we only need the root window hook
        await client.hook_handler.activate_root_window_hook()

        await read_fish_basket(client)
    finally:
        print("Closing")
        await handler.close()


if __name__ == "__main__":
    asyncio.run(main())
