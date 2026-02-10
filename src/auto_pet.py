import asyncio
import time
import traceback
from asyncio import CancelledError

from loguru import logger
from pymem.exception import MemoryReadError
from wizwalker import HookAlreadyActivated, HookNotActive, HookNotReady, Client, Keycode, XYZ
from wizwalker.memory import MemoryReader
import struct
from typing import List, Optional
from src.paths import *
from src.teleport_math import navmap_tp
from src.utils import navigate_to_ravenwood, click_window_by_path, is_visible_by_path, navigate_to_commons_from_ravenwood, post_keys, get_window_from_path, safe_wait_for_zone_change, LoadingScreenNotFound, FriendBusyOrInstanceClosed, get_popup_title, wait_until_path_in_tree


#Full credit to Click for the Constants from Ghidra Analysis
PETGAMEDANCE_VTABLE_OFFSET = 0x2A425C8
OFFSET_SERVER_MOVES_START = 0x908      # Pointer to server's move array
OFFSET_SERVER_MOVES_END = 0x910        # Pointer to end of server's moves
OFFSET_PLAYER_MOVES_START = 0x928      # Pointer to player's input array
OFFSET_PLAYER_MOVES_END = 0x930        # Pointer to end of player's inputs


DIRECTION_KEYS = {
    0: Keycode.W,   # Up
    1: Keycode.D,   # Right
    2: Keycode.S,   # Down
    3: Keycode.A,   # Left
}

async def find_pet_game_dance(client: Client) -> Optional[int]:
    """
    Find the PetGameDance object in memory by scanning for its vtable pointer.
    """
    reader = MemoryReader(client._pymem)
    base_address = client._pymem.base_address
    vtable_addr = base_address + PETGAMEDANCE_VTABLE_OFFSET
    vtable_bytes = struct.pack("<Q", vtable_addr)
    try:
        addresses = await reader.pattern_scan(
            vtable_bytes,
            return_multiple=True,
            module=None
        )

        if addresses:
            return addresses[0]
    except Exception as e:
        #logger.debug(f"Failed to find PetGameDance: {e}")
        pass
    return None


async def read_moves_array(client: Client, pet_game_addr: int) -> List[int]:
    """
    Read the server's moves array from the PetGameDance object.
    """
    pymem = client._pymem
    try:
        start_ptr_bytes = pymem.read_bytes(pet_game_addr + OFFSET_SERVER_MOVES_START, 8)
        end_ptr_bytes = pymem.read_bytes(pet_game_addr + OFFSET_SERVER_MOVES_END, 8)

        start_ptr = struct.unpack("<Q", start_ptr_bytes)[0]
        end_ptr = struct.unpack("<Q", end_ptr_bytes)[0]
    except Exception as e:
        logger.debug(f"Failed to read pointers: {e}")
        return []

    if start_ptr == 0 or end_ptr == 0 or end_ptr <= start_ptr:
        return []
    num_moves = (end_ptr - start_ptr) // 4

    if num_moves > 100 or num_moves <= 0:
        return []
    try:
        moves_bytes = pymem.read_bytes(start_ptr, num_moves * 4)
        moves = list(struct.unpack(f"<{num_moves}i", moves_bytes))
    except Exception as e:
        logger.debug(f"Failed to read moves: {e}")
        return []

    return moves


async def play_dance_game(client, timeout = 120):
    """
    PetDanceGame game loop
    """
    last_moves = []
    pet_game_addr = None
    start_time = time.monotonic()
    expected_vtable = client._pymem.base_address + PETGAMEDANCE_VTABLE_OFFSET
    logger.debug(f"Starting PetGameDance for {client.title}")
    while True:
        # Timeout guard
        if time.monotonic() - start_time > timeout:
            # Client is likely stuck in a loading screen
            logger.debug("Dance monitor timed out.")
            break

        try:
            if pet_game_addr is None:
                pet_game_addr = await find_pet_game_dance(client)
                if not pet_game_addr:
                    await asyncio.sleep(0.5)
                    continue
            # Validate object via vtable check
            try: vtable = struct.unpack( "<Q", client._pymem.read_bytes(pet_game_addr, 8))[0]

            except Exception as e:
                logger.debug(f"PetGameDance Vtable check failed: {e}")

            # Read moves
            moves = await read_moves_array(client, pet_game_addr)

            # Send moves
            if moves and moves != last_moves:
                await dancedance(client, moves)
                logger.debug(f"{client.title}: Dance:{len(moves) - 2}/5")
                last_moves = moves.copy()

            await asyncio.sleep(0.1)

            # Break the loop after 5 dances
            if len(moves) >= 7:
                break

        except Exception as e:
            logger.debug(f"Monitor error: {e}")
            break

async def navigate_to_pavilion_from_commons(cl: Client):
    # Teleport to pet pavilion door
    pavilion_XYZ = XYZ(8426.3779296875, -2165.6982421875, -27.913818359375)
    await navmap_tp(cl, pavilion_XYZ)
    await cl.wait_for_zone_change(name='WizardCity/WC_Hub')
    await asyncio.sleep(2.0)


async def navigate_to_dance_game(cl: Client):
    # Walk forward, to Milo Barker
    await cl.goto(x=-1738.7811279296875, y=-387.345458984375)
    # Walk in front of pet game
    await cl.goto(x=-4090.10888671875, y=-1186.3660888671875)
    # Walk onto sigil
    await cl.goto(x=-4449.36669921875, y=-992.9967651367188)


async def nomnom(client: Client, ignore_pet_level_up: bool, only_play_dance_game: bool):
    finished_feeding = False

    while not finished_feeding:
        popup_title = await get_popup_title(client)
        while not popup_title == 'Dance Game':
            await asyncio.sleep(.125)
            popup_title = await get_popup_title(client)

        # wait for dance game popup, and click until the popup goes away and the pet window opens
        while not await is_visible_by_path(client, pet_feed_window_visible_path):
            while popup_title == 'Dance Game':
                await client.send_key(Keycode.X, 0.1)
                popup_title = await get_popup_title(client)
                await asyncio.sleep(.125)
            popup_title = await get_popup_title(client)
            await asyncio.sleep(.125)

        client.feeding_pet_status = True
        # click until feeder opens
        # while await client.is_in_npc_range():
        #     await client.send_key(Keycode.X, 0.1)
        #     await asyncio.sleep(.2)

        # wait for pet window to open
        # while not await is_visible_by_path(client, pet_feed_window_visible_path):
        #     await asyncio.sleep(.1)

        energy_cost_txt = await get_window_from_path(client.root_window, pet_feed_window_energy_cost_textbox_path)
        total_energy_txt = await get_window_from_path(client.root_window, pet_feed_window_your_energy_textbox_path)

        energy_cost = await energy_cost_txt.maybe_text()
        total_energy = await total_energy_txt.maybe_text()

        energy_cost = energy_cost[8:]
        total_energy = total_energy[8:]
        total_energy = total_energy.split('/', 1)[0]
        energy_cost = int(energy_cost)
        total_energy = int(total_energy)

        # if player has enough energy to play the game
        if total_energy >= energy_cost:
            # if the config forces us to play the dance game or we are unable to skip games yet - and the hook is not already active - activate the hook


            # skip game if it is an option and the user's config for always playing the game is off
            if await is_visible_by_path(client, skip_pet_game_button_path) and not only_play_dance_game:
                # click skip game button until window changes
                while await is_visible_by_path(client, pet_feed_window_visible_path):
                    if await is_visible_by_path(client, skip_pet_game_button_path):
                        async with client.mouse_handler:
                            await click_window_by_path(client, skip_pet_game_button_path)
                        await asyncio.sleep(.2)

                # wait for reward window to show up
                while not await is_visible_by_path(client, skipped_pet_game_rewards_window_path):
                    await asyncio.sleep(.1)

                # click 'Next' button
                if await is_visible_by_path(client, skipped_pet_game_continue_and_feed_button_path):
                    async with client.mouse_handler:
                        await click_window_by_path(client, skipped_pet_game_continue_and_feed_button_path)
                    await asyncio.sleep(1.5)

                # click first snack
                if await is_visible_by_path(client, skipped_first_pet_snack_path):
                    async with client.mouse_handler:
                        await click_window_by_path(client, skipped_first_pet_snack_path)
                    await asyncio.sleep(.6)

                    # Click 'Feed Pet'
                    if await is_visible_by_path(client, skipped_pet_game_continue_and_feed_button_path):
                        async with client.mouse_handler:
                            await click_window_by_path(client, skipped_pet_game_continue_and_feed_button_path)
                        await asyncio.sleep(1.0)

                        # Handle what happens when the pet levels up
                        # if user has ignore_pet_level_up = True, exit out of the level up screen and continue questing
                        # otherwise, leave it up and force user to close it themselves
                        if await is_visible_by_path(client, skipped_pet_leveled_up_window_path):
                            if not ignore_pet_level_up:
                                logger.info('Auto Pet - Client ' + client.title + '\'s pet leveled uclient.  Please close the window to continue, or exit Deimos if you wish to stop questing.')
                                logger.info('These pauses can be disabled in the config file by setting ignore_pet_level_up = True')

                                # wait for the user to realize their pet leveled up and wait for them to manually close the window
                                while await is_visible_by_path(client, skipped_pet_leveled_up_window_path):
                                    await asyncio.sleep(1.0)
                            else:
                                # while pet leveled up window is open, continually click exit button
                                while await is_visible_by_path(client, skipped_pet_leveled_up_window_path):
                                    if await is_visible_by_path(client, exit_skipped_pet_leveled_up_path):
                                        async with client.mouse_handler:
                                            await click_window_by_path(client, exit_skipped_pet_leveled_up_path)
                                        await asyncio.sleep(.2)

                        # wait for final screen
                        while not await is_visible_by_path(client, skipped_finish_pet_button):
                            await asyncio.sleep(.1)

                        # click 'Finish' button to exit all the way out
                        while await is_visible_by_path(client, skipped_finish_pet_button):
                            async with client.mouse_handler:
                                await click_window_by_path(client, skipped_finish_pet_button)
                            await asyncio.sleep(.2)

                        # wait for reward screen to close
                        while await is_visible_by_path(client, skipped_pet_game_rewards_window_path):
                            await asyncio.sleep(.1)
                else:
                    logger.info('Auto Pet - Client ' + client.title + ' is out of snacks.')
                    finished_feeding = True

                await asyncio.sleep(.5)
            # play dance game since the user has not unlocked skip game yet (or if config is set to always play)
            # thanks to Peechez for the actual dance game playing code
            else:
                # wait for pet game selection window to appear
                while await is_visible_by_path(client, pet_feed_window_visible_path):
                    # click wizard city game
                    await client.send_key(Keycode.X, 0.1)
                    if await is_visible_by_path(client, wizard_city_dance_game_path):
                        async with client.mouse_handler:
                            await click_window_by_path(client, wizard_city_dance_game_path)
                        await asyncio.sleep(.2)

                    # click play
                    if await is_visible_by_path(client, play_dance_game_button_path):
                        async with client.mouse_handler:
                            await click_window_by_path(client, play_dance_game_button_path)
                        await asyncio.sleep(.1)

                # Wait for PetGameDance to load and play it
                await safe_wait_for_zone_change(client,"ThePhantomZoneWorld/PetGameDance")
                await play_dance_game(client)

                # Click 'Next' to skip badge reward window 
                await wait_until_path_in_tree(client, won_pet_game_continue_and_feed_button_path)
                if await is_visible_by_path(client, won_pet_game_continue_and_feed_button_path):
                    async with client.mouse_handler:
                        await click_window_by_path(client, won_pet_game_continue_and_feed_button_path)
                    await asyncio.sleep(1.5)

                # if we leveled up from the small amount of XP the pet game gave us, account for it
                if await is_visible_by_path(client, won_pet_leveled_up_window_path):
                    await won_game_leveled_up(client, ignore_pet_level_up)

                # click first snack
                if await is_visible_by_path(client, won_first_pet_snack_path):
                    async with client.mouse_handler:
                        await click_window_by_path(client, won_first_pet_snack_path)
                    await asyncio.sleep(.6)

                    # Click 'Feed Pet'
                    if await is_visible_by_path(client, won_pet_game_continue_and_feed_button_path):
                        # Handle what happens when the pet levels up
                        # if user has ignore_pet_level_up = True, exit out of the level up screen and continue questing
                        # otherwise, leave it up and force user to close it themselves
                        await won_game_leveled_up(client, ignore_pet_level_up)

                        # wait for reward screen
                        while not await is_visible_by_path(client, won_finish_pet_button):
                            await asyncio.sleep(.1)

                        # click 'Finish'
                        while await is_visible_by_path(client, won_finish_pet_button):
                            async with client.mouse_handler:
                                await click_window_by_path(client, won_finish_pet_button)
                            await asyncio.sleep(.2)

                        # wait for reward screen to close
                        while await is_visible_by_path(client, won_pet_game_rewards_window_path):
                            await asyncio.sleep(.1)
                else:
                    logger.info('Auto Pet - Client ' + client.title + ' is out of snacks.')
                    finished_feeding = True

                await asyncio.sleep(.5)
        else:
            logger.info('Auto Pet - Client ' + client.title + ' is out of energy.')
            finished_feeding = True

    # feed window may still be open, close it
    while await is_visible_by_path(client, pet_feed_window_visible_path):
        if await is_visible_by_path(client, pet_feed_window_cancel_button_path):
            async with client.mouse_handler:
                await click_window_by_path(client, pet_feed_window_cancel_button_path)
            await asyncio.sleep(.2)

    # home button can in rare cases be greyed out after auto_buy - wait some time to make sure that clients don't get stuck if other code tries to send them home
    # await asyncio.sleep(6.5)

    client.feeding_pet_status = False

    # wait for client or code to walk off the sigil
    while await get_popup_title(client) == 'Dance Game':
        await asyncio.sleep(.125)


# Thanks to Peechez for this code from wizdancer
async def dancedance(client, moves):
    while not await is_visible_by_path(client, dance_game_action_textbox_path):
        await asyncio.sleep(.1)
    action_window = await get_window_from_path(client.root_window, dance_game_action_textbox_path)
    while await action_window.maybe_text() != "<center>Go!":
        await asyncio.sleep(0.125)
    await asyncio.sleep(1.5)
    for step in moves:
        keycode = DIRECTION_KEYS[step] 
        await client.send_key(keycode, 0.1)


async def won_game_leveled_up(client: Client, auto_pet_ignore_pet_level_up):
    async with client.mouse_handler:
        await click_window_by_path(client, won_pet_game_continue_and_feed_button_path)
    await asyncio.sleep(1.0)
    if await is_visible_by_path(client, won_pet_leveled_up_window_path):
        if not auto_pet_ignore_pet_level_up:
            logger.info('Auto Pet - Client ' + client.title + '\'s pet leveled up.  Please close the window to continue, or exit Deimos if you wish to stop questing.')
            logger.info('These pauses can be disabled in the config file by setting auto_pet_ignore_pet_level_up = True')

            # wait for the user to realize their pet leveled up and wait for them to manually close the window
            while await is_visible_by_path(client, won_pet_leveled_up_window_path):
                await asyncio.sleep(1.0)
        else:
            # while pet leveled up window is open, continually click exit button
            while await is_visible_by_path(client, won_pet_leveled_up_window_path):
                if await is_visible_by_path(client, exit_won_pet_leveled_up_path):
                    async with client.mouse_handler:
                        await click_window_by_path(client, exit_won_pet_leveled_up_path)
                    await asyncio.sleep(.2)


async def auto_pet(client: Client, ignore_pet_level_up: bool, only_play_dance_game: bool, questing: bool = False):
    # we know we are on the pet sigil or going to it, activate and let nomnom deactivate when it is finished
    client.feeding_pet_status = True

    started_at_pavilion = False
    if await client.zone_name() != 'WizardCity/WC_Streets/Interiors/WC_PET_Park':
        original_mana = await client.stats.current_mana()
        while await client.stats.current_mana() >= original_mana:
            logger.debug(f'Client {client.title} - Marking Location')
            await client.send_key(Keycode.PAGE_DOWN, 0.1)
            await asyncio.sleep(.75)

        await asyncio.sleep(.5)
        # Navigate to ravenwood
        await navigate_to_ravenwood(client)
        # Navigate to commons from ravenwood
        await navigate_to_commons_from_ravenwood(client)
        # Navigate to pet pavilion from commons
        await navigate_to_pavilion_from_commons(client)
        # Navigate to sigil
        await navigate_to_dance_game(client)
    else:
        started_at_pavilion = True
        try:
            await client.teleport(XYZ(x=-4450.57958984375, y=-994.8973388671875, z=-8.041412353515625))
        except ValueError:
            await asyncio.sleep(3.0)
            await client.teleport(XYZ(x=-4450.57958984375, y=-994.8973388671875, z=-8.041412353515625))


        # for i in range(3):
        #     await client.send_key(Keycode.END, 0.1)
        #
        # try:
        #     await safe_wait_for_zone_change(client, name='WizardCity/WC_Streets/Interiors/WC_PET_Park')
        # # commons button was probably on cooldown.  wait and try again
        # except LoadingScreenNotFound:
        #     logger.debug('Failed to return to commons - sleeping and trying again.')
        #     await asyncio.sleep(30.0)
        #     for i in range(3):
        #         await client.send_key(Keycode.END, 0.1)
        #
        #     await client.wait_for_zone_change(name='WizardCity/WC_Streets/Interiors/WC_PET_Park')
        #
        # await asyncio.sleep(2.0)
        # # Navigate to pet pavilion from commons
        # await navigate_to_pavilion_from_commons(client)
        # # Navigate to sigil
        # await navigate_to_dance_game(client)

    # lets outer functions know when the client has leveled up and has more energy to use
    if questing:
        client.character_level = await client.stats.reference_level()

    # feed the pet
    # await nomnom(client, ignore_pet_level_up, only_play_dance_game)

    while client.feeding_pet_status:
        await asyncio.sleep(.1)

    await asyncio.sleep(1.0)

    # walk off of the sigil to stop auto pet from triggering
    # await client.goto(-3830.433837890625, -1301.0308837890625)

    if not started_at_pavilion:
        # return to last location
        await client.send_key(Keycode.PAGE_UP, 0.1)

        # account for teleporting to mark
        # if any error occurs, just let auto quest take care of it
        while True:
            try:
                await safe_wait_for_zone_change(client, name='WizardCity/WC_Streets/Interiors/WC_PET_Park', handle_hooks_if_needed=True)
                break
            # something may have gone wrong initially with the teleport mark - we never entered a loading screen
            except LoadingScreenNotFound:
                logger.debug('Client ' + client.title + 'failed to recall from pet pavilion.')
                pass
            # we attempted to teleport to a closed dungeon
            except FriendBusyOrInstanceClosed:
                logger.debug('Client ' + client.title + 'failed to recall from pet pavilion - instance was closed.')
                break

