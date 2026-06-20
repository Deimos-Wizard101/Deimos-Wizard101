import asyncio
import traceback
from asyncio import CancelledError

from loguru import logger
from pymem.exception import MemoryReadError
from wizwalker import HookAlreadyActivated, HookNotActive, HookNotReady, Client, Keycode, XYZ
from wizwalker.memory import HookHandler, SimpleHook

from src.dance_game_hook import attempt_activate_dance_hook, attempt_deactivate_dance_hook
from src.paths import *
from src.teleport_math import navmap_tp
from src.utils import navigate_to_ravenwood, click_window_by_path, is_visible_by_path, navigate_to_commons_from_ravenwood, post_keys, get_window_from_path, safe_wait_for_zone_change, LoadingScreenNotFound, FriendBusyOrInstanceClosed, get_popup_title

_dance_moves_transtable = str.maketrans("abcd", "WDSA")
_DANCE_SCREEN_TIMEOUT = 20.0
_DANCE_ROUND_TIMEOUT = 25.0
_PET_REWARD_TIMEOUT = 30.0


async def _collect_visible_ui_paths(window, path=None, results=None, depth=0):
    if path is None:
        path = []
    if results is None:
        results = []
    if depth >= 8 or len(results) >= 80:
        return results

    try:
        children = await window.children()
    except Exception:
        return results

    for child in children:
        if len(results) >= 80:
            break
        try:
            name = await child.name()
        except Exception:
            name = "<unreadable>"
        child_path = path + [name]
        try:
            if await child.is_visible():
                results.append("/".join(child_path))
        except Exception:
            pass
        await _collect_visible_ui_paths(child, child_path, results, depth + 1)
    return results


async def _control_state(client: Client, path):
    window = await get_window_from_path(client.root_window, path)
    if not window:
        return {
            "path": path,
            "exists": False,
            "visible": False,
            "grayed": None,
            "checked": None,
            "clickable": False,
        }

    async def read(method, default=None):
        try:
            return await method()
        except Exception:
            return default

    visible = await read(window.is_visible, False)
    grayed = await read(window.is_control_grayed)
    checked = await read(window.maybe_checked)
    return {
        "path": path,
        "exists": True,
        "visible": visible,
        "grayed": grayed,
        "checked": checked,
        "clickable": bool(visible and grayed is False),
        "text": await read(window.maybe_text),
        "tip": await read(window.tip),
        "rectangle": str(await read(window.window_rectangle)),
        "alpha": await read(window.alpha),
        "disabled_alpha": await read(window.disabled_alpha),
    }


async def _wait_for_dance_selection_stable(client: Client, cycle_number: int, timeout: float = 8.0):
    logger.debug(
        f"Auto Pet - Client {client.title}: Cycle {cycle_number} waiting for stable Dance Game selection UI."
    )
    deadline = asyncio.get_running_loop().time() + timeout
    stable_reads = 0
    while asyncio.get_running_loop().time() < deadline:
        track_visible = await is_visible_by_path(client, pet_feed_window_visible_path)
        play_state = await _control_state(client, play_dance_game_button_path)
        if track_visible and play_state["visible"]:
            stable_reads += 1
            if stable_reads >= 3:
                logger.debug(
                    f"Auto Pet - Client {client.title}: Cycle {cycle_number} selection UI is stable; "
                    f"play_state={play_state}."
                )
                return
        else:
            stable_reads = 0
        await asyncio.sleep(0.15)

    await _log_pet_ui_timeout(client, f"Cycle {cycle_number} Dance Game selection UI")
    raise TimeoutError(f"Cycle {cycle_number} Dance Game selection UI did not stabilize")


async def ensure_dance_game_level_selected(client: Client, cycle_number: int, attempt: int):
    candidates = [await _control_state(client, path) for path in dance_game_level_paths]
    logger.info(
        f"Auto Pet - Client {client.title}: Cycle {cycle_number} level/map candidates "
        f"(attempt={attempt})={candidates}."
    )

    selectable = [state for state in candidates if state["visible"] and state["grayed"] is False]
    if not selectable:
        selectable = [state for state in candidates if state["visible"]]
    if not selectable:
        raise RuntimeError(f"Cycle {cycle_number} has no visible Dance Game level/map candidates")

    selected = selectable[0]
    logger.info(
        f"Auto Pet - Client {client.title}: Cycle {cycle_number} selecting level/map "
        f"path={selected['path']}, checked_before={selected['checked']}, "
        f"grayed_before={selected['grayed']}."
    )
    await click_window_by_path(client, selected["path"])
    await asyncio.sleep(0.45)

    selected_after = await _control_state(client, selected["path"])
    play_state = await _control_state(client, play_dance_game_button_path)
    logger.info(
        f"Auto Pet - Client {client.title}: Cycle {cycle_number} level/map selection applied; "
        f"selected_state={selected_after}, play_state={play_state}."
    )
    return selected_after, play_state


async def _start_dance_game_cycle(client: Client, cycle_number: int, max_attempts: int = 4):
    await _wait_for_dance_selection_stable(client, cycle_number)

    for attempt in range(1, max_attempts + 1):
        selected_state, play_state = await ensure_dance_game_level_selected(
            client, cycle_number, attempt
        )
        if play_state["grayed"] is True:
            logger.warning(
                f"Auto Pet - Client {client.title}: Cycle {cycle_number} Play is disabled after "
                f"selecting {selected_state['path']}; reselecting level/map before retry."
            )
            continue
        if not play_state["visible"]:
            logger.warning(
                f"Auto Pet - Client {client.title}: Cycle {cycle_number} Play is not visible after "
                "level/map selection; retrying."
            )
            continue
        if play_state["grayed"] is None:
            logger.warning(
                f"Auto Pet - Client {client.title}: Cycle {cycle_number} Play grayed state was unreadable; "
                "clicking once only after explicit level/map selection."
            )

        logger.info(
            f"Auto Pet - Client {client.title}: Cycle {cycle_number} clicking Play after level/map "
            f"selection; play_state={play_state}."
        )
        await click_window_by_path(client, play_dance_game_button_path)

        transition_deadline = asyncio.get_running_loop().time() + 5.0
        while asyncio.get_running_loop().time() < transition_deadline:
            if not await is_visible_by_path(client, pet_feed_window_visible_path):
                logger.info(
                    f"Auto Pet - Client {client.title}: Cycle {cycle_number} Play transition started."
                )
                return True
            await asyncio.sleep(0.1)

        play_after = await _control_state(client, play_dance_game_button_path)
        logger.warning(
            f"Auto Pet - Client {client.title}: Cycle {cycle_number} Play click did not transition "
            f"(attempt={attempt}, play_state_after={play_after}); reselecting level/map."
        )

    await _log_pet_ui_timeout(client, f"Cycle {cycle_number} enabled Play transition")
    logger.error(
        f"Auto Pet - Client {client.title}: Cycle {cycle_number} stopped gracefully because Play "
        f"never became usable after {max_attempts} level/map selections."
    )
    return False


async def _pet_ui_debug_state(client: Client):
    known_paths = {
        "track_selection": pet_feed_window_visible_path,
        "play_button": play_dance_game_button_path,
        "skip_button": skip_pet_game_button_path,
        "dance_action": dance_game_action_textbox_path,
        "reward_screen": won_pet_game_rewards_window_path,
        "reward_next": won_pet_game_continue_and_feed_button_path,
        "snack_zero": won_first_pet_snack_path,
        "finish_button": won_finish_pet_button,
    }
    visible = {}
    for name, path in known_paths.items():
        try:
            visible[name] = await is_visible_by_path(client, path)
        except Exception as error:
            visible[name] = f"error:{type(error).__name__}"

    try:
        popup_title = await get_popup_title(client)
    except Exception as error:
        popup_title = f"error:{type(error).__name__}"
    try:
        zone_name = await client.zone_name()
    except Exception as error:
        zone_name = f"error:{type(error).__name__}"

    return {
        "zone": zone_name,
        "popup_title": popup_title,
        "known_paths": visible,
        "play_control": await _control_state(client, play_dance_game_button_path),
        "level_controls": [
            await _control_state(client, path) for path in dance_game_level_paths
        ],
        "visible_ui_paths": await _collect_visible_ui_paths(client.root_window),
    }


async def _log_pet_ui_timeout(client: Client, stage: str):
    try:
        state = await _pet_ui_debug_state(client)
    except Exception:
        logger.exception(f"Auto Pet - Client {client.title}: Failed to collect UI state for {stage} timeout.")
        return
    logger.error(f"Auto Pet - Client {client.title}: {stage} timed out; ui_state={state}")


async def _wait_for_visible_path(client: Client, path, timeout: float, stage: str):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if await is_visible_by_path(client, path):
            return True
        await asyncio.sleep(0.1)
    await _log_pet_ui_timeout(client, stage)
    raise TimeoutError(f"Auto Pet timed out waiting for {stage}")


async def _find_dance_action_window(client: Client):
    action_window = await get_window_from_path(client.root_window, dance_game_action_textbox_path)
    if action_window and await action_window.is_visible():
        return action_window

    for candidate in await client.root_window.get_windows_with_name("txtAction"):
        if await candidate.is_visible():
            return candidate
    return None


async def _wait_for_dance_action_window(client: Client, timeout: float):
    logger.debug(f"Auto Pet - Client {client.title}: Waiting for Dance Game screen.")
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        action_window = await _find_dance_action_window(client)
        if action_window is not None:
            logger.info(f"Auto Pet - Client {client.title}: Dance Game screen detected.")
            return action_window
        await asyncio.sleep(0.1)
    await _log_pet_ui_timeout(client, "Dance Game screen")
    raise TimeoutError("Auto Pet timed out waiting for the Dance Game screen")


async def _wait_for_action_text(action_window, predicate, timeout: float, stage: str):
    deadline = asyncio.get_running_loop().time() + timeout
    last_text = None
    while asyncio.get_running_loop().time() < deadline:
        last_text = await action_window.maybe_text()
        if predicate(last_text):
            return last_text
        await asyncio.sleep(0.125)
    raise TimeoutError(f"Auto Pet timed out during {stage}; last_action_text={last_text!r}")


async def _read_dance_moves(client: Client, round_number: int, timeout: float = 6.0):
    deadline = asyncio.get_running_loop().time() + timeout
    last_error = None
    while asyncio.get_running_loop().time() < deadline:
        try:
            moves = await client.hook_handler.read_current_dance_game_moves()
            if moves:
                return moves
        except (HookNotActive, HookNotReady, MemoryReadError) as error:
            last_error = error
        await asyncio.sleep(0.1)
    raise RuntimeError(
        f"Dance move hook was not ready for round {round_number}; last_error={last_error}"
    )

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
    mode = "normal-play" if only_play_dance_game else "skip"
    completed = False
    logger.info(f"Auto Pet - Client {client.title}: Task started (mode={mode}).")
    try:
        await _nomnom(client, ignore_pet_level_up, only_play_dance_game)
        completed = True
    except CancelledError:
        logger.warning(
            f"Auto Pet - Client {client.title}: Task cancelled; the Auto Pet hotkey, "
            "client lifecycle, or task restart stopped the run."
        )
        raise
    except Exception:
        logger.exception(f"Auto Pet - Client {client.title}: Task failed before snack feeding completed.")
        raise
    finally:
        if client.dance_hook_status:
            await attempt_deactivate_dance_hook(client)
        client.feeding_pet_status = False
        result = "success" if completed else "failed-or-cancelled"
        logger.info(f"Auto Pet - Client {client.title}: Task finished ({result}).")


async def _nomnom(client: Client, ignore_pet_level_up: bool, only_play_dance_game: bool):
    finished_feeding = False
    dance_hook_activated = False
    cycle_number = 0

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
            # Activate the dance hook whenever normal play is selected or skipping is unavailable.
            if (only_play_dance_game or not await is_visible_by_path(client, skip_pet_game_button_path)) and not dance_hook_activated:
                logger.debug('Auto Pet - Client ' + client.title + ': Normal play selected; activating dance game hook.')
                # dance hook seems to need time to activate fully - without a sleep, it will miss turns in the game
                dance_hook_activated = await attempt_activate_dance_hook(client, sleep_time=5.0)
                if not dance_hook_activated:
                    raise RuntimeError("Dance game hook activation failed; refusing to start an unsolved pet game")


            # skip game if it is an option and the user's config for always playing the game is off
            if await is_visible_by_path(client, skip_pet_game_button_path) and not only_play_dance_game:
                logger.warning(
                    'Auto Pet - Client ' + client.title +
                    ': Skip Pet Games is enabled; using SkipGameButton instead of Play.'
                )
                # click skip game button until window changes
                while await is_visible_by_path(client, pet_feed_window_visible_path):
                    if await is_visible_by_path(client, skip_pet_game_button_path):
                        logger.debug(
                            'Auto Pet - Client ' + client.title +
                            ': Clicking Skip Game via UI path ' + str(skip_pet_game_button_path)
                        )
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
            # Play the Dance Game normally unless skipping was explicitly enabled.
            # thanks to Peechez for the actual dance game playing code
            else:
                cycle_number += 1
                logger.info(
                    f"Auto Pet - Client {client.title}: Starting normal Dance Game cycle "
                    f"{cycle_number}; Skip Game will not be clicked."
                )
                if not await _start_dance_game_cycle(client, cycle_number):
                    finished_feeding = True
                    continue

                logger.info(f"Auto Pet - Client {client.title}: Cycle {cycle_number} waiting for Dance Game screen.")

                # automatic success method
                # play the dance game and win it
                await dancedance(client)

                # if we leveled up from the small amount of XP the pet game gave us, account for it
                if await is_visible_by_path(client, won_pet_leveled_up_window_path):
                    logger.info(f"Auto Pet - Client {client.title}: Handling pet level-up before snack selection.")
                    await won_game_leveled_up(client, ignore_pet_level_up)

                logger.debug(f"Auto Pet - Client {client.title}: Waiting for reward and snack UI.")
                await _wait_for_visible_path(
                    client,
                    won_pet_game_rewards_window_path,
                    _PET_REWARD_TIMEOUT,
                    "pet reward screen",
                )
                await _wait_for_visible_path(
                    client,
                    won_pet_game_continue_and_feed_button_path,
                    10.0,
                    "reward Continue button",
                )
                logger.debug(f"Auto Pet - Client {client.title}: Clicking Continue to open snack list.")
                async with client.mouse_handler:
                    await click_window_by_path(client, won_pet_game_continue_and_feed_button_path)
                await asyncio.sleep(1.0)

                try:
                    await _wait_for_visible_path(
                        client,
                        won_first_pet_snack_path,
                        12.0,
                        "snack list",
                    )
                except TimeoutError:
                    logger.error(
                        f"Auto Pet - Client {client.title}: Snack feeding was not reached because "
                        "snack index 0 never appeared; treating this as out of snacks."
                    )
                    finished_feeding = True
                    continue

                snack_window = await get_window_from_path(client.root_window, won_first_pet_snack_path)
                try:
                    snack_name = await snack_window.maybe_text()
                except Exception:
                    snack_name = None
                logger.info(
                    f"Auto Pet - Client {client.title}: Snack list detected; selecting "
                    f"snack index=0, name={snack_name!r}."
                )
                async with client.mouse_handler:
                    await click_window_by_path(client, won_first_pet_snack_path)
                await asyncio.sleep(.6)

                await _wait_for_visible_path(
                    client,
                    won_pet_game_continue_and_feed_button_path,
                    10.0,
                    "Feed Pet button",
                )
                logger.info(f"Auto Pet - Client {client.title}: Clicking Feed Pet for snack index 0.")
                await won_game_leveled_up(client, ignore_pet_level_up)
                logger.info(f"Auto Pet - Client {client.title}: Snack fed successfully.")

                await _wait_for_visible_path(
                    client,
                    won_finish_pet_button,
                    _PET_REWARD_TIMEOUT,
                    "pet reward Finish button",
                )
                while await is_visible_by_path(client, won_finish_pet_button):
                    logger.debug(f"Auto Pet - Client {client.title}: Clicking Finish.")
                    async with client.mouse_handler:
                        await click_window_by_path(client, won_finish_pet_button)
                    await asyncio.sleep(.2)

                while await is_visible_by_path(client, won_pet_game_rewards_window_path):
                    await asyncio.sleep(.1)
                logger.info(
                    f"Auto Pet - Client {client.title}: Pet game cycle complete; "
                    "continuing while energy and snacks remain."
                )

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

    if dance_hook_activated:
        logger.debug('Client ' + client.title + ': Deactivating dance game hook.')
        await attempt_deactivate_dance_hook(client)

    # home button can in rare cases be greyed out after auto_buy - wait some time to make sure that clients don't get stuck if other code tries to send them home
    # await asyncio.sleep(6.5)

    client.feeding_pet_status = False

    # wait for client or code to walk off the sigil
    while await get_popup_title(client) == 'Dance Game':
        await asyncio.sleep(.125)


# Thanks to Peechez for this code from wizdancer
async def dancedance(client: Client):
    action_window = await _wait_for_dance_action_window(client, _DANCE_SCREEN_TIMEOUT)

    for round_number in range(1, 6):
        logger.info(f"Auto Pet - Client {client.title}: Dance round {round_number}/5 started.")
        try:
            sequence_text = await _wait_for_action_text(
                action_window,
                lambda text: text != "<center>Go!",
                _DANCE_ROUND_TIMEOUT,
                f"round {round_number} sequence display",
            )
            logger.debug(
                f"Auto Pet - Client {client.title}: Round {round_number} sequence display detected; "
                f"action_text={sequence_text!r}."
            )
            await _wait_for_action_text(
                action_window,
                lambda text: text == "<center>Go!",
                _DANCE_ROUND_TIMEOUT,
                f"round {round_number} Go prompt",
            )
        except TimeoutError:
            await _log_pet_ui_timeout(client, f"Dance round {round_number}")
            logger.error(f"Auto Pet - Client {client.title}: Dance round {round_number} failed to advance.")
            raise

        await asyncio.sleep(1.5)
        moves = await _read_dance_moves(client, round_number)
        logger.info(
            f"Auto Pet - Client {client.title}: Round {round_number} detected arrow sequence={moves!r}."
        )
        logger.debug(
            f"Auto Pet - Client {client.title}: Round {round_number} sending arrow key presses={list(moves)}."
        )
        await post_keys(client, moves)
        logger.info(f"Auto Pet - Client {client.title}: Round {round_number} arrow presses sent.")

        await asyncio.sleep(0.5)
        try:
            result_text = await action_window.maybe_text()
        except Exception:
            result_text = "<action window transitioned>"
        lowered_result = (result_text or "").lower()
        if any(word in lowered_result for word in ("fail", "wrong", "miss")):
            outcome = "failure"
        elif any(word in lowered_result for word in ("great", "good", "perfect", "success")):
            outcome = "success"
        else:
            outcome = "submitted"
        logger.info(
            f"Auto Pet - Client {client.title}: Round {round_number} outcome={outcome}; "
            f"action_text={result_text!r}."
        )

    logger.info(f"Auto Pet - Client {client.title}: All dance rounds submitted; waiting for results.")
    deadline = asyncio.get_running_loop().time() + _PET_REWARD_TIMEOUT
    while asyncio.get_running_loop().time() < deadline:
        if await is_visible_by_path(client, won_pet_game_rewards_window_path):
            logger.info(f"Auto Pet - Client {client.title}: Dance game complete; reward screen detected.")
            return
        if await is_visible_by_path(client, won_pet_leveled_up_window_path):
            logger.info(f"Auto Pet - Client {client.title}: Dance game complete; pet level-up screen detected.")
            return
        await asyncio.sleep(0.1)

    await _log_pet_ui_timeout(client, "Dance Game results")
    raise TimeoutError("Auto Pet timed out waiting for Dance Game results")


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

