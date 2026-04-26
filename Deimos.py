import asyncio
import traceback
import requests
import queue
import threading
import wizwalker
from wizwalker import Keycode, HotkeyListener, ModifierKeys, utils, XYZ, Orient
from wizwalker.utils import get_all_wizard_handles, get_foreground_window
from wizwalker.client_handler import ClientHandler, Client
from wizwalker.extensions.scripting import teleport_to_friend_from_list
from wizwalker.memory.memory_objects.camera_controller import DynamicCameraController, ElasticCameraController
from wizwalker.memory.memory_objects.window import Window
import os
import time
import sys
import ctypes
import winreg
import subprocess
from loguru import logger
import datetime
import statistics
import re
# import pypresence
from pypresence import AioPresence
from src.command_parser import execute_flythrough, parse_command
from src.auto_pet import nomnom
from src.drop_logger import logging_loop
# from src.combat_new import Fighter
from src.stat_viewer import total_stats
from src.world_to_screen import world_to_screen, get_camera_state, project_point
from src.teleport_math import navmap_tp, calc_Distance
from src.questing import Quester
from src.sigil import Sigil
from src.utils import index_with_str, is_visible_by_path, is_free, auto_potions, auto_potions_force_buy, to_world, collect_wisps_with_limit, try_task_coro, read_webpage, override_wiz_install_using_handle, get_window_from_path#, assign_pet_level
from src.paths import advance_dialog_path, decline_quest_path, play_button_path
import pyperclip
from src.sprinty_client import SprintyClient
from src.gui_inputs import param_input, trunc
from src import discsdk
from wizwalker.extensions.wizsprinter.wiz_navigator import toZoneDisplayName, toZone
from wizwalker.extensions.wizsprinter.sprinty_combat import SprintyCombat
from src.config_combat import StrCombatConfigProvider, delegate_combat_configs, default_config
from typing import List

from src import gui as deimosgui
from src.gui import GUIKeys
import wizlaunch
from src.settings_manager import DeimosSettings
from src.tokenizer import tokenize
from src.deimoslang import vm


cMessageBox = ctypes.windll.user32.MessageBoxW

tool_version: str = '3.13.0 (BETA 2)'
tool_name: str = 'Deimos'
tool_author: str = 'Deimos-Wizard101'
repo_name: str = tool_name + '-Wizard101'
branch: str = 'main'
repo_path_raw: str = f'https://raw.githubusercontent.com/{tool_author}/{repo_name}/refs/heads/{branch}'

type_format_dict = {
"char": "<c",
"signed char": "<b",
"unsigned char": "<B",
"bool": "?",
"short": "<h",
"unsigned short": "<H",
"int": "<i",
"unsigned int": "<I",
"long": "<l",
"unsigned long": "<L",
"long long": "<q",
"unsigned long long": "<Q",
"float": "<f",
"double": "<d",
}


def remove_if_exists(file_name : str, sleep_after : float = 0.1):
	if os.path.exists(file_name):
		os.remove(file_name)
		time.sleep(sleep_after)


def download_file(url: str, file_name : str, delete_previous: bool = False, debug : str = True):
	if delete_previous:
		remove_if_exists(file_name)
	if debug:
		print(f'Downloading {file_name}...')
	with requests.get(url, stream=True) as r:
		with open(file_name, 'wb') as f:
			for chunk in r.iter_content(chunk_size=128000):
				f.write(chunk)


# Default settings — JSON in AppData is authoritative
speed_multiplier = 5.0
use_potions = True
rpc_status = True
drop_status = True
anti_afk_status = True
gui_on_top = True
gui_langcode = 'en'
gui_font = 'Segoe UI'
gui_font_size = 9
use_team_up = False
buy_potions = True
client_to_follow = None
client_to_boost = None
questing_friend_tp = False
gear_switching_in_solo_zones = False
hitter_client = None
kill_minions_first = False
automatic_team_based_combat = False
discard_duplicate_cards = True
ignore_pet_level_up = False
only_play_dance_game = False

settings = DeimosSettings()
settings.migrate_theme_from_settings()

# Load theme from dedicated theme file
theme_dict = settings.get_theme()

# Override globals from settings.json (authoritative after migration)
_json_settings = settings.get_settings()
speed_multiplier = _json_settings.get('speed_multiplier', speed_multiplier)
use_potions = _json_settings.get('use_potions', use_potions)
rpc_status = _json_settings.get('rich_presence', rpc_status)
drop_status = _json_settings.get('drop_logging', drop_status)
anti_afk_status = _json_settings.get('use_anti_afk', anti_afk_status)
buy_potions = _json_settings.get('buy_potions', buy_potions)
gui_on_top = _json_settings.get('on_top', gui_on_top)
gui_langcode = _json_settings.get('locale', gui_langcode)
gui_font = _json_settings.get('font', gui_font)
gui_font_size = _json_settings.get('font_size', gui_font_size)
use_team_up = _json_settings.get('use_team_up', use_team_up)
client_to_follow = _json_settings.get('client_to_follow', client_to_follow)
client_to_boost = _json_settings.get('client_to_boost', client_to_boost)
questing_friend_tp = _json_settings.get('friend_teleport', questing_friend_tp)
gear_switching_in_solo_zones = _json_settings.get('gear_switching_in_solo_zones', gear_switching_in_solo_zones)
hitter_client = _json_settings.get('hitter_client', hitter_client)
ignore_pet_level_up = _json_settings.get('ignore_pet_level_up', ignore_pet_level_up)
only_play_dance_game = _json_settings.get('only_play_dance_game', only_play_dance_game)
kill_minions_first = _json_settings.get('kill_minions_first', kill_minions_first)
automatic_team_based_combat = _json_settings.get('automatic_team_based_combat', automatic_team_based_combat)
discard_duplicate_cards = _json_settings.get('discard_duplicate_cards', discard_duplicate_cards)

while True:
	if hasattr(sys, '_MEIPASS'):
		folder_path = os.path.join(sys._MEIPASS, 'wizwalker/extensions/wizsprinter/traversalData')
		if not os.path.exists(folder_path):
			os.makedirs(folder_path)
		download_file('https://raw.githubusercontent.com/notfaj/wizsprinter/main/wizwalker/extensions/wizsprinter/traversalData/displayZones.txt', os.path.join(folder_path, 'displayZones.txt'))
		download_file('https://raw.githubusercontent.com/notfaj/wizsprinter/main/wizwalker/extensions/wizsprinter/traversalData/gates_list.txt', os.path.join(folder_path, 'gates_list.txt'))
		download_file('https://raw.githubusercontent.com/notfaj/wizsprinter/main/wizwalker/extensions/wizsprinter/traversalData/interactiveTeleporters.txt', os.path.join(folder_path, 'interactiveTeleporters.txt'))
		download_file('https://raw.githubusercontent.com/notfaj/wizsprinter/main/wizwalker/extensions/wizsprinter/traversalData/objectLocations.txt', os.path.join(folder_path, 'objectLocations.txt'))
		download_file('https://raw.githubusercontent.com/notfaj/wizsprinter/main/wizwalker/extensions/wizsprinter/traversalData/uniqueObjectLocations.txt', os.path.join(folder_path, 'uniqueObjectLocations.txt'))
		download_file('https://raw.githubusercontent.com/notfaj/wizsprinter/main/wizwalker/extensions/wizsprinter/traversalData/zoneMap.txt', os.path.join(folder_path, 'zoneMap.txt'))
	break

speed_status = False
combat_status = False
dialogue_status = False
sigil_status = False
freecam_status = False
hotkey_status = False
questing_status = False
auto_pet_status = False
auto_potion_status = False
side_quest_status = False
tool_status = True
original_client_locations = dict()

hotkeys_blocked = False

sigil_leader_pid: int = None
questing_leader_pid: int = None

questing_task: asyncio.Task = None
auto_pet_task: asyncio.Task = None
sigil_task: asyncio.Task = None
dialogue_task: asyncio.Task = None
combat_task: asyncio.Task = None
tp_task: asyncio.Task = None
speed_task: asyncio.Task = None
pet_task: asyncio.Task = None

bot_task: asyncio.Task = None
flythrough_task: asyncio.Task = None
highlight_task: asyncio.Task = None
entity_stream_task: asyncio.Task = None

def file_len(filepath) -> List[str]:
	# return the number of lines in a file
	f = open(filepath, "r")
	return len(f.readlines())


def generate_timestamp() -> str:
	# generates a timestamp and makes the symbols filename-friendly
	time = str(datetime.datetime.now())
	time_list = time.split('.')
	time_stamp = str(time_list[0])
	time_stamp = time_stamp.replace('/', '-').replace(':', '-')
	return time_stamp



def run_updater():
	download_file(url=f"{repo_path_raw}/{tool_name}Updater.exe", file_name=f'{tool_name}Updater.exe', delete_previous=True)
	time.sleep(0.1)
	subprocess.Popen(f'{tool_name}Updater.exe')
	sys.exit()


def get_latest_version() -> str:
	update_server = None

	try:
		update_server = read_webpage(f"{repo_path_raw}/LatestVersion.txt")
	except:
		time.sleep(0.1)

	if len(update_server) >= 1:
		return update_server[0]
	else:
		return None


def is_version_greater(version: str, comparison_version: str) -> bool:
	# Compares the semantic version of two inputted versions and returns True if the first is greater
	version_list = version.split('.')
	comparison_version_list = comparison_version.split('.')

	for i, v in enumerate(version_list):
		current_v = int(v)
		current_comparison_v = int(comparison_version_list[i])
		if current_v > current_comparison_v:
			return True
		elif current_v < current_comparison_v:
			return False

	return False


# def auto_update(latest_version: str = get_latest_version()):
# 	remove_if_exists(f'{tool_name}-copy.exe')
# 	remove_if_exists(f'{tool_name}Updater.exe')
# 	time.sleep(0.1)
# 	if auto_updating:
# 		if is_version_greater(latest_version, tool_version):
# 			run_updater()




async def mass_key_press(foreground_client : Client, background_clients : list[Client], pressed_key_name: str, key, duration : float = 0.1, debug : bool = False):
	# sends a given keystroke to all clients, handles foreground client seperately
	if debug and foreground_client:
		key_name = str(key)
		key_name = key_name.replace('Keycode.', '')
		logger.debug(f'{pressed_key_name} key pressed, sending {key_name} key press to all clients.')
	await asyncio.gather(*[p.send_key(key=key, seconds=duration) for p in background_clients])
	# only send foreground key press if there is a client in foreground
	if foreground_client:
		await foreground_client.send_key(key=key, seconds=duration)


async def sync_camera(client: Client, xyz: XYZ = None, yaw: float = None):
	# Teleports the freecam to a specified position, yaw, etc.
	if not xyz:
		xyz = await client.body.position()

	if not yaw:
		yaw = await client.body.yaw()

	xyz.z += 200

	camera = await client.game_client.free_camera_controller()
	await camera.write_position(xyz)
	await camera.write_yaw(yaw)


async def xyz_sync(foreground_client : Client, background_clients : list[Client], turn_after : bool = True, debug : bool = False):
	# syncs client XYZ up with the one in foreground, doesn't work across zones or realms
	if background_clients:
		if debug:
			logger.debug('XYZ Sync hotkey pressed, syncing client locations.')
		if foreground_client:
			xyz = await foreground_client.body.position()
			yaw = await foreground_client.body.yaw()
		else:
			first_background_client = background_clients[0]
			xyz = await first_background_client.body.position()
			yaw = await first_background_client.body.yaw()

		await asyncio.gather(*[p.teleport(xyz, yaw=yaw) for p in background_clients])
		if turn_after:
			await asyncio.gather(*[p.send_key(key=Keycode.A, seconds=0.1) for p in background_clients])
			await asyncio.gather(*[p.send_key(key=Keycode.D, seconds=0.1) for p in background_clients])
		await asyncio.sleep(0.3)


async def navmap_teleport(foreground_client : wizwalker.Client, background_clients : list[Client], mass_teleport: bool = False, debug : bool = False, xyz: XYZ = None):
	# teleports foreground client or all clients using the navmap.
	# nested function that allows for the gathering of the teleports for each client
	async def client_navmap_teleport(client: Client, xyz: XYZ = None):
		if not xyz:
			xyz = await client.quest_position.position()
		await navmap_tp(client, xyz)
		# except:
		# 	# skips teleport if there's no navmap, this should just switch to auto adjusting teleport
		# 	logger.error(f'{client.title} encountered an error during navmap tp, most likely the navmap for the zone did not exist. Skipping teleport.')

	if debug:
		if mass_teleport:
			logger.debug('Mass TP hotkey pressed, teleporting all clients to quests.')
		else:
			logger.debug(f'Quest TP hotkey pressed, teleporting client {foreground_client.title} to quest.')
	clients_to_port = []
	if foreground_client:
		clients_to_port.append(foreground_client)
	if mass_teleport:
		for b in background_clients:
			clients_to_port.append(b)
		# decide which client's quest XYZ to obey. Chooses the most common Quest XYZ across all clients, if there is none and all clients are in the same zone then it obeys the foreground client. If the zone differs, each client obeys their own quest XYZ.
		list_modes = statistics.multimode([await c.quest_position.position() for c in clients_to_port])
		zone_names = [await p.zone_name() for p in clients_to_port]
		if len(list_modes) == 1:
			xyz = list_modes[0]
		else:
			if zone_names.count(zone_names[0]) == len(zone_names):
				if foreground_client:
					xyz = await foreground_client.quest_position.position()

	# if mass teleport is off and no client is selected, this will default to p1
	if len(clients_to_port) == 0:
		if background_clients:
			clients_to_port.append(background_clients[0])

	# all clients teleport at the same time
	await asyncio.gather(*[client_navmap_teleport(p, xyz) for p in clients_to_port])


async def friend_teleport_sync(clients : list[wizwalker.Client], debug: bool):
	# uses the util for porting to friend via the friends list. Sends every client to p1. I really don't like this function, or this code, but it works and people want it so I have to have it in here sadly. Might rewrite it someday.
	if debug:
		logger.debug('Friend TP hotkey pressed, friend teleporting all clients to p1.')
	child_clients = clients[1:]
	for p in child_clients:
		async with p.mouse_handler:
			try:
				await teleport_to_friend_from_list(client=p, icon_list=1, icon_index=50)
			except Exception as e:
				logger.error(e)
				await asyncio.sleep(0)



async def kill_tool(debug: bool):
	# raises KeyboardInterrupt, forcing the tool to exit.
	if debug:
		logger.debug(f'Kill tool hotkey pressed, killing {tool_name}.')
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	raise deimosgui.ToolClosedException


async def tool_finish():
	if not walker or len(walker.clients) == 0:
		return

	alive_clients = [p for p in walker.clients if p.is_running()]
	for p in alive_clients:
		try:
			original_speed = client_speeds.get(p.process_id)
			if original_speed is not None:
				await p.client_object.write_speed_multiplier(original_speed)
			p.title = 'Wizard101'
			# Uncomment when freecam is fixed
			if await p.game_client.is_freecam():
				await p.camera_elastic()
			else:
				camera: ElasticCameraController = await p.game_client.elastic_camera_controller()
				client_object = await p.body.parent_client_object()
				await camera.write_attached_client_object(client_object)
				await camera.write_check_collisions(True)
				await camera.write_distance_target(300.0)
				await camera.write_distance(300.0)
				await camera.write_min_distance(150.0)
				await camera.write_max_distance(450.0)
				await camera.write_zoom_resolution(150.0)
			await p.body.write_scale(1.0)
		except Exception:
			pass
	await listener.clear()
	for p in walker.clients:
		try:
			await asyncio.wait_for(p.close(), timeout=10.0)
		except asyncio.TimeoutError:
			logger.warning(f"Timed out closing client '{p.title}', skipping.")
		except:
			pass
	# await walker.close()
	await asyncio.sleep(0)
	global tool_status
	tool_status = False


@logger.catch()
async def main():
	global tool_status
	global original_client_locations
	global listener
	listener = HotkeyListener()
	foreground_client: Client = None
	background_clients = []
	await asyncio.sleep(0)
	listener.start()


	async def x_press_hotkey():
		await mass_key_press(foreground_client, background_clients, 'X Press', Keycode.X, duration=0.1, debug=True)


	async def xyz_sync_hotkey():
		await xyz_sync(foreground_client, background_clients, turn_after=True, debug=True)


	async def navmap_teleport_hotkey():
		if not freecam_status:
			await navmap_teleport(foreground_client, background_clients, mass_teleport=False, debug=True)


	async def mass_navmap_teleport_hotkey():
		if not freecam_status:
			await navmap_teleport(foreground_client, background_clients, mass_teleport=True, debug=True)


	async def toggle_speed_hotkey():
		global speed_task
		global gui_send_queue

		if not freecam_status:
			if speed_task is not None and not speed_task.cancelled():
				speed_task.cancel()
				speed_task = None
				logger.debug('Speed hotkey pressed, disabling speed multiplier.')
				gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('SpeedhackStatus', 'Disabled')))
				for client in walker.clients:
					await client.client_object.write_speed_multiplier(client_speeds[client.process_id])

			else:
				logger.debug('Speed hotkey pressed, enabling speed multiplier.')
				gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('SpeedhackStatus', 'Enabled')))
				speed_task = asyncio.create_task(try_task_coro(speed_switching, walker.clients))


	async def friend_teleport_sync_hotkey():
		if not freecam_status:
			await friend_teleport_sync(walker.clients, debug=True)


	async def kill_tool_hotkey():
		# await tool_finish()
		# try:
		# 	await kill_tool(debug=True)
		# except deimosgui.ToolClosedException:
		# 	pass
		# finally:
		# 	gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.Close))
		# global tool_status
		# tool_status = False;
		logger.debug(f"Kill tool hotkey pressed, closing {tool_name}.")
		if walker.clients != 0:
			gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.CloseFromBackend))
		# raise deimosgui.ToolClosedException



	async def toggle_combat_hotkey(debug: bool = True):
		global combat_task
		global gui_send_queue

		for client in walker.clients:
			client.combat_status ^= True

		if not freecam_status:
			if combat_task is not None and not combat_task.cancelled():
				combat_task.cancel()
				combat_task = None
				if debug:
					logger.debug('Combat hotkey pressed, disabling auto combat.')
				gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('CombatStatus', 'Disabled')))

			else:
				if debug:
					logger.debug('Combat hotkey pressed, enabling auto combat.')
				gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('CombatStatus', 'Enabled')))
				combat_task = asyncio.create_task(try_task_coro(combat_loop, walker.clients, True))


	async def toggle_dialogue_hotkey():
		global dialogue_task
		global gui_send_queue
		# global side_quest_status

		if not freecam_status:
			if dialogue_task is not None and not dialogue_task.cancelled():
				# side_quest_status = False
				dialogue_task.cancel()
				dialogue_task = None
				logger.debug('Dialogue hotkey pressed, disabling auto dialogue.')
				gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('DialogueStatus', 'Disabled')))

			else:
				# side_quest_log_str = ""
				# side_quest_status = side_quests
				# if side_quest_status:
				# 	side_quest_log_str += " and auto side quests functionality"
				logger.debug('Dialogue hotkey pressed, enabling auto dialogue.')
				gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('DialogueStatus', 'Enabled')))
				dialogue_task = asyncio.create_task(try_task_coro(dialogue_loop, walker.clients, True))


	# async def toggle_dialogue_side_quests_hotkey():
	# 	await toggle_dialogue_hotkey(True)



	async def toggle_sigil_hotkey():
		global sigil_task
		global questing_status
		global questing_task
		global gui_send_queue

		if not freecam_status:
			for p in walker.clients:
				p.sigil_status ^= True
				if p.sigil_status:
					p.questing_status = False
					p.auto_pet_status = False

			if sigil_task is not None and not sigil_task.cancelled():
				sigil_task.cancel()
				sigil_task = None
				logger.debug('Sigil hotkey pressed, disabling auto sigil.')
				gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('SigilStatus', 'Disabled')))

			else:
				logger.debug('Sigil hotkey pressed, enabling auto sigil.')
				if questing_task is not None and not questing_task.cancelled():
					logger.debug('Questing hotkey pressed, disabling auto questing.')
					gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('QuestingStatus', 'Disabled')))
					questing_task.cancel()
					for p in walker.clients:
						p.questing_status = False
					questing_status = False
					questing_task = None

				gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('SigilStatus', 'Enabled')))
				sigil_task = asyncio.create_task(try_task_coro(sigil_loop, walker.clients, True))



	async def toggle_freecam_hotkey(debug: bool = True):
		global freecam_status
		if foreground_client:
			if await is_free(foreground_client):
				if await foreground_client.game_client.is_freecam():
					if debug:
						logger.debug('Freecam hotkey pressed, disabling freecam.')
					await foreground_client.camera_elastic()
					freecam_status = False
					gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('FreecamStatus', 'Disabled')))

				else:
					if debug:
						logger.debug('Freecam hotkey pressed, enabling freecam.')

					freecam_status = True
					await sync_camera(foreground_client)
					await foreground_client.camera_freecam()
					gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('FreecamStatus', 'Enabled')))


	async def tp_to_freecam_hotkey():
		if foreground_client:
			logger.debug('Freecam TP hotkey pressed, teleporting foreground client to freecam position.')
			if await foreground_client.game_client.is_freecam():
				camera = await foreground_client.game_client.free_camera_controller()
				camera_pos = await camera.position()
				await toggle_freecam_hotkey(False)
				await foreground_client.teleport(camera_pos, wait_on_inuse=True, purge_on_after_unuser_fixer=True)


	async def toggle_questing_hotkey():
		global sigil_task
		global questing_task
		global questing_status
		global sigil_status
		global gui_send_queue

		if not freecam_status:
			questing_status ^= True
			for p in walker.clients:
				p.questing_status ^= True

			if questing_task is not None and not questing_task.cancelled():
				logger.debug('Questing hotkey pressed, disabling auto questing.')
				gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('QuestingStatus', 'Disabled')))
				questing_task.cancel()
				questing_task = None

			else:
				for p in walker.clients:
					p.sigil_status = False

				if sigil_task is not None and not sigil_task.cancelled():
					logger.debug('Sigil hotkey pressed, disabling auto sigil.')
					gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('SigilStatus', 'Disabled')))
					sigil_task.cancel()
					sigil_task = None
					for p in walker.clients:
						p.sigil_status = False
					sigil_status = False

				logger.debug('Questing hotkey pressed, enabling auto questing.')
				gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('QuestingStatus', 'Enabled')))
				questing_task = asyncio.create_task(try_task_coro(questing_loop, walker.clients, True))


	async def toggle_auto_pet_hotkey():
		global auto_pet_task
		global auto_pet_status

		if not freecam_status:
			auto_pet_status ^= True
			for p in walker.clients:
				p.auto_pet_status ^= True

			if auto_pet_task is not None and not auto_pet_task.cancelled():
				logger.debug(f'Disabling auto pet.')
				gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('Auto PetStatus', 'Disabled')))
				auto_pet_task.cancel()
				auto_pet_task = None

			else:
				logger.debug(f'Enabling auto pet.')
				gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('Auto PetStatus', 'Enabled')))
				auto_pet_task = asyncio.create_task(try_task_coro(auto_pet_loop, walker.clients, True))


	async def toggle_auto_potion_hotkey():
		global auto_potion_status
		
		if not freecam_status:
			auto_potion_status ^= True
			
			if auto_potion_status:
				logger.debug(f'Enabling auto potion.')
				gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('Auto PotionStatus', 'Enabled')))
			else:
				logger.debug(f'Disabling auto potion.')
				gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('Auto PotionStatus', 'Disabled')))


	# Generic hotkey callback factory — sends InvokeAction to GUI thread,
	# which calls the button's click handler. Works for ANY registered action.
	def _make_hotkey_callback(action_id):
		async def _callback():
			gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.InvokeAction, action_id))
		return _callback

	# Kill tool needs a direct async callback since it must work even with no GUI
	_kill_tool_callback = kill_tool_hotkey

	_active_bindings = {}  # action_id -> {"key": str, "modifiers": [str]}

	_FREECAM_ACTIONS = {"toggle_freecam", "freecam_tp"}

	async def enable_hotkeys(exclude_freecam: bool = False, debug: bool = False):
		global hotkey_status
		if not hotkey_status:
			if debug:
				logger.debug('Client selected, starting hotkey listener.')
			hotkeys = settings.get_hotkeys()
			for action_id, binding in hotkeys.items():
				if binding is None:
					continue
				if action_id == "kill_tool":
					continue  # kill_tool registered separately, always bound
				if exclude_freecam and action_id in _FREECAM_ACTIONS:
					continue
				mods = ModifierKeys.NOREPEAT
				for m in binding.get("modifiers", []):
					mods |= ModifierKeys[m]
				try:
					await listener.add_hotkey(Keycode[binding["key"]], _make_hotkey_callback(action_id), modifiers=mods)
					_active_bindings[action_id] = binding
				except Exception as e:
					logger.debug(f'Failed to register hotkey for {action_id}: {e}')
			hotkey_status = True


	async def disable_hotkeys(exclude_freecam: bool = False, debug: bool = False, exclude_kill: bool = True):
		global hotkey_status
		if hotkey_status:
			if debug:
				logger.debug('Client not selected, stopping hotkey listener.')
			for action_id, binding in list(_active_bindings.items()):
				if exclude_kill and action_id == "kill_tool":
					continue
				if exclude_freecam and action_id in _FREECAM_ACTIONS:
					continue
				mods = ModifierKeys.NOREPEAT
				for m in binding.get("modifiers", []):
					mods |= ModifierKeys[m]
				try:
					await listener.remove_hotkey(Keycode[binding["key"]], modifiers=mods)
					del _active_bindings[action_id]
				except Exception as e:
					logger.debug(f'Failed to remove hotkey for {action_id}: {e}')
			hotkey_status = False

	def get_foreground_client():
		if not walker.clients:
			return None
		foreground = [c for c in walker.clients if c.is_foreground]
		if len(foreground) > 0:
			return foreground[0]
		if not foreground_client:
			return walker.clients[0]
		return foreground_client

	def get_background_clients():
		return [c for c in walker.clients if not c.is_foreground]

	async def foreground_client_switching():
		await asyncio.sleep(2)
		# enable hotkeys if a client is selected, disable if none are
		while True:
			await asyncio.sleep(0.1)
			foreground_client_list = [c for c in walker.clients if c.is_foreground]
			if foreground_client_list:
				await enable_hotkeys(debug = True)
			else:
				await disable_hotkeys(debug = True)


	async def assign_foreground_clients():
		# assigns the foreground client and a list of background clients
		nonlocal foreground_client
		nonlocal background_clients
		while True:
			foreground_client = get_foreground_client()
			background_clients = get_background_clients()
			await asyncio.sleep(0.1)


	async def speed_switching():
		# handles updating the speed multiplier if a zone or realm change happens
		modified_speed = (int(speed_multiplier) - 1) * 100
		while True:
			await asyncio.sleep(0.1)
			# if speed multiplier is enabled, rewrite the multiplier value if the speed changes. If speed mult is disabled, rewrite the original untouched speed multiplier only if it equals the multiplier speed
			if not freecam_status:
				await asyncio.sleep(0.2)
				for c in walker.clients:
					if await c.client_object.speed_multiplier() != modified_speed:
						await c.client_object.write_speed_multiplier(modified_speed)


	async def is_client_in_combat_loop():
		async def async_in_combat(client: Client):
			# battle = Fighter(client)
			# while True:
			# 	if await battle.is_fighting():
			# 		client.in_combat = True
			# 	else:
			# 		client.in_combat = False
			# 	await asyncio.sleep(0.1)
			while True:
				# print(await client.game_client.is_freecam())
				if not freecam_status:
					client.in_combat = await client.in_battle()
				await asyncio.sleep(0.1)

		await asyncio.gather(*[async_in_combat(p) for p in walker.clients])


	async def combat_loop():
		logger.catch()
		# waits for combat for every client and handles them seperately.
		async def async_combat(client: Client):
			while True:
				await asyncio.sleep(1)
				if not freecam_status:
					while not await client.in_battle():
						await asyncio.sleep(1)

					if await client.in_battle():
						logger.debug(f'Client {client.title} in combat, handling combat.')

						#CONFIG COMBAT
						battle = SprintyCombat(client, StrCombatConfigProvider(client.combat_config), True)
						await battle.wait_for_combat()

		await asyncio.gather(*[async_combat(p) for p in walker.clients])

	async def dialogue_loop():
		# auto advances dialogue for every client, individually and concurrently
		async def async_dialogue(client: Client):
			while True:
				if not freecam_status:
					if await is_visible_by_path(client, advance_dialog_path):
						# if await is_visible_by_path(client, decline_quest_path) and not side_quest_status:
						# 	await client.send_key(key=Keycode.ESC)
						# 	await asyncio.sleep(0.1)
						# 	await client.send_key(key=Keycode.ESC)
						# else:
						await client.send_key(key=Keycode.SPACEBAR)
				await asyncio.sleep(0.1)

		await asyncio.gather(*[async_dialogue(p) for p in walker.clients])

	# logger.catch()
	async def questing_loop():
		# Auto questing on a per client basis.
		async def async_questing(client: Client):
			client.character_level = await client.stats.reference_level()

			while True:
				await asyncio.sleep(1)

				if client in walker.clients and questing_status:
					if questing_leader_pid is not None and len(walker.clients) > 1:
						if client.process_id == questing_leader_pid:
							# if follow leader is off, quest on all clients, passing through only the leader
							logger.debug(f'Client {client.title} - Handling questing for all clients.')
							questing = Quester(client, walker.clients, questing_leader_pid)
							await questing.auto_quest_leader(questing_friend_tp, gear_switching_in_solo_zones, hitter_client, ignore_pet_level_up, only_play_dance_game)
					else:
						# if follow leader is off, quest on all clients, passing through only the leader
						logger.debug(f'Client {client.title} - Handling questing.')
						questing = Quester(client, walker.clients, None)
						await questing.auto_quest(ignore_pet_level_up, only_play_dance_game)

		await asyncio.gather(*[async_questing(p) for p in walker.clients])

	async def anti_afk_questing_loop():
		async def async_afk_questing(client: Client):
			while True:
				global questing_task

				await asyncio.sleep(0.1)
				if not freecam_status:
					client_xyz = await client.body.position()
					await asyncio.sleep(120)
					client_xyz_2 = await client.body.position()
					distance_moved = calc_Distance(client_xyz, client_xyz_2)
					if distance_moved < 5.0 and not await client.in_battle() and not client.feeding_pet_status and not client.entity_detect_combat_status:

						# During questing, one or more clients may be waiting outside while the others are completing a solo zone quest - we do not want to restart in these cases
						client_in_solo_zone = False
						for p in walker.clients:
							if p.in_solo_zone:
								client_in_solo_zone = True

						# restart questing
						if questing_task is not None and not questing_task.cancelled() and not client_in_solo_zone:
								logger.debug(f'Questing appears to have halted - restarting.')
								questing_task.cancel()
								questing_task = None
								await asyncio.sleep(1.0)

								if questing_task is None:
									questing_task = asyncio.create_task(try_task_coro(questing_loop, walker.clients, True))


		await asyncio.gather(*[async_afk_questing(p) for p in walker.clients])

	# logger.catch()
	async def auto_pet_loop():
		# Auto questing on a per client basis.
		async def async_auto_pet(client: Client):
			while True:
				await asyncio.sleep(1)

				if client in walker.clients and auto_pet_status:
					await nomnom(client, ignore_pet_level_up=ignore_pet_level_up, only_play_dance_game=only_play_dance_game)


		await asyncio.gather(*[async_auto_pet(p) for p in walker.clients])

	async def nearest_duel_circle_distance_and_xyz(sprinter: SprintyClient):
		min_distance = None
		circle_xyz = None

		try:
			entities = await sprinter.get_base_entity_list()
		except ValueError:
			return None, None

		for entity in entities:
			try:
				entity_name = await entity.object_name()
			except wizwalker.MemoryReadError:
				entity_name = ''

			if entity_name == 'Duel Circle':
				entity_pos = await entity.location()
				distance = calc_Distance(entity_pos, await sprinter.client.body.position())

				if min_distance is None:
					min_distance = distance
					circle_xyz = entity_pos
				elif distance < min_distance:
					min_distance = distance
					circle_xyz = entity_pos
				# print('distance to duel circle: ', distance)

		return min_distance, circle_xyz

	async def is_duel_circle_joinable(p: Client):
		sprinter = SprintyClient(p)
		await asyncio.sleep(7)

		distance, duel_circle_xyz = await nearest_duel_circle_distance_and_xyz(sprinter)
		# if after 7 seconds we are not in a battle position, we either teleported while invincible or teleported to a non-joinable fight
		if distance is not None:
			if not (590 < distance < 610):
				logger.debug('Bad teleport.  Returning ' + p.title + ' to safe location.')
				if p.original_location_before_combat is not None:
					await p.teleport(p.original_location_before_combat)
					p.original_location_before_combat = None
				else:
					position = await p.body.position()
					await p.teleport(XYZ(position.x, position.y, position.z - 350))

				p.entity_detect_combat_status = False

				return False

			return True
		else:
			return False

	async def entity_detect_combat_loop():
		async def detect_combat(p: Client):
			global original_client_locations
			sprinter = SprintyClient(p)

			other_clients = []
			for c in walker.clients:
				if c != p:
					other_clients.append(c)

			safe_distance = 620
			while True:
				await asyncio.sleep(.5)

				if p.questing_status:
					if p.just_entered_combat is not None:
						# 5 seconds have passed since the client entered combat
						if time.time() >= (p.just_entered_combat + 7):
							# we are actually in combat
							if await p.in_battle():
								p.just_entered_combat = None
							# if we aren't in combat after 7 seconds, something went wrong - duel circle is likely not joinable
							else:
								# client_being_helped is None when you are the client that is being helped
								if p.client_being_helped is not None:
									is_circle_joinable = await is_duel_circle_joinable(p)
									# check_duel_circle_joinable = [asyncio.create_task(is_duel_circle_joinable(helper)) for helper in p.helper_clients]
									# done, pending = await asyncio.wait(check_duel_circle_joinable)
									#
									# is_circle_joinable = True
									# for d in done:
									# 	is_circle_joinable = d.result()


									if not is_circle_joinable:
										p.client_being_helped.duel_circle_joinable = False
										logger.debug('Client ' + p.client_being_helped.title + ' - ' + 'Duel circle not joinable - teleports halted.')
										p.client_being_helped = None

					if p.just_entered_combat is None:
						if True:
							distance, duel_circle_xyz = await nearest_duel_circle_distance_and_xyz(sprinter)

							if distance is None:
								if p.entity_detect_combat_status:
									p.just_left_combat = True
								else:
									p.entity_detect_combat_status = False

							# When fully in combat (once running animation occurs and selection phase begins) clients in any battle order are ~600 away from the center of the duel circle
							# extra leeway on this allows clients to teleport more quickly to ensure that they arrive before the selection phase even starts
							elif distance < safe_distance:
									p.entity_detect_combat_status = True

									# original_client_locations = dict()
									all_fighting_clients = [p]

									# don't teleport clients to duel circles that are closed off, and don't teleport clients if they are in separate instances
									if p.duel_circle_joinable and not p.in_solo_zone:
										p.helper_clients = []
										none_in_solo_zone = True
										all_already_in_battle = False
										for c in other_clients:
											client_is_hitter_client = False
											if hitter_client is not None:
												if hitter_client in c.title:
													client_is_hitter_client = True
													all_already_in_battle = True
													for cl in walker.clients:
														if hitter_client not in cl.title:
															if not cl.entity_detect_combat_status:
																all_already_in_battle = False

															if cl.in_solo_zone:
																none_in_solo_zone = False

											# if we are the hitter client, we've confirmed that we are the last to teleport, and no one is in a solo zone, or we are not the hitter client, then we can teleport
											if (client_is_hitter_client and all_already_in_battle and none_in_solo_zone) or not client_is_hitter_client:
												if await is_free(c) and not c.entity_detect_combat_status and not c.invincible_combat_timer and c.just_entered_combat is None:
													# player_distance = calc_Distance(await c.body.position(), await p.body.position())
													# print('player distance between [', c.title, '] and [', p.title, '] is: ', player_distance)

													if hitter_client is not None:
														if all_already_in_battle and hitter_client in c.title:
															# slight delay to ensure hitter makes it to the circle last
															await asyncio.sleep(1.0)

													if await c.zone_name() == await p.zone_name():
														if not c.entity_detect_combat_status:
															c.entity_detect_combat_status = True
															c.just_entered_combat = time.time()
															c.original_location_before_combat = await c.body.position()
															original_client_locations.update({c.process_id: await c.body.position()})
															c.client_being_helped = p
															if c not in p.helper_clients:
																p.helper_clients.append(c)
																all_fighting_clients.append(c)

															logger.debug('Combat detected from client ' + p.title + ' - teleporting client ' + c.title)
															try:
																await c.teleport(duel_circle_xyz)
																# just_entered_combat = True
															except ValueError:
																c.just_entered_combat = None
																pass
									helper_clients = []


							else:
								if p.entity_detect_combat_status:
									p.just_left_combat = True
								else:
									p.entity_detect_combat_status = False

							if p.just_left_combat and await is_free(p):
								p.just_left_combat = False
								# collect wisps, up to a certain number
								await collect_wisps_with_limit(p, limit=2)
								await asyncio.sleep(.3)

								# return helper clients to their previous safe location
								if p.process_id in original_client_locations:
									logger.debug('Client ' + p.title + ' - ' + 'Returning to safe location. ')

									try:
										await p.teleport(original_client_locations.get(p.process_id))
										original_client_locations.pop(p.process_id)
									except ValueError:
										print(traceback.print_exc())
										p.original_location_before_combat = None



								# just_left_combat = False

								# Mark wizard as invincible, as clients can get stuck standing in the middle of another client's battle circle due to teleporting while invincibile
								logger.debug('Client ' + p.title + ' - ' + 'Battle teleports off while invulnerable')
								p.invincible_combat_timer = True
								p.entity_detect_combat_status = False
								p.duel_circle_joinable = True
								p.client_being_helped = None
								# p.just_entered_combat = None

								# Timer seems to be about 6.5 seconds to become draggable again
								await asyncio.sleep(6.5)
								logger.debug('Client ' + p.title + ' - ' + 'Battle teleports re-enabled')
								p.invincible_combat_timer = False

		await asyncio.gather(*[detect_combat(p) for p in walker.clients])


	async def sigil_loop():
		# Auto sigil on a per client basis.
		async def async_sigil(client: Client):
			while True:
				await asyncio.sleep(1)
				if client in walker.clients and client.sigil_status and not freecam_status:
					sigil = Sigil(client, walker.clients, sigil_leader_pid)
					await sigil.wait_for_sigil()

		await asyncio.gather(*[async_sigil(p) for p in walker.clients])


	async def anti_afk_loop():
		# anti AFK implementation on a per client basis.
		if not anti_afk_status:
			return

		async def async_anti_afk(client: Client):
			# await client.root_window.debug_print_ui_tree()
			# print(await client.body.position())
			while True:
				global questing_task

				await asyncio.sleep(0.1)
				if not freecam_status:
					client_xyz = await client.body.position()
					await asyncio.sleep(350)
					client_xyz_2 = await client.body.position()
					distance_moved = calc_Distance(client_xyz, client_xyz_2)
					if distance_moved < 5.0 and not await client.in_battle() and not client.feeding_pet_status and not client.entity_detect_combat_status and not sigil_status:
						logger.debug(f"Client {client.title} - AFK client detected, moving slightly.")
						await client.send_key(key=Keycode.A)
						await asyncio.sleep(0.1)
						await client.send_key(key=Keycode.D)

		await asyncio.gather(*[async_anti_afk(p) for p in walker.clients])


	# Track which window handles were launched by us, mapped to account nickname
	launched_account_map: dict[int, str] = {}
	initial_setup_complete = False
	# Handles explicitly released via UnhookClient — skip in continuous detection
	released_handles: set[int] = set()
	# Handles currently mid-hook (activate_hooks in progress)
	_hooking_in_progress: set[int] = set()

	def _mask_uid(uid) -> str:
		s = str(uid)
		return '****' if len(s) <= 4 else '*' * (len(s) - 4) + s[-4:]

	def _kill_process_by_handle(handle):
		"""Terminate the OS process behind a window handle."""
		try:
			pid = utils.get_pid_from_handle(handle)
			if pid:
				PROCESS_TERMINATE = 0x0001
				h_proc = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
				if h_proc:
					ctypes.windll.kernel32.TerminateProcess(h_proc, 1)
					ctypes.windll.kernel32.CloseHandle(h_proc)
		except Exception as e:
			logger.error(f"Failed to kill process for handle {handle}: {e}")

	def _build_hooked_clients_info():
		# Prune stale entries for handles whose windows no longer exist
		all_handles = set(get_all_wizard_handles())
		stale = [h for h in launched_account_map if h not in all_handles]
		for h in stale:
			launched_account_map.pop(h)
			_hooking_in_progress.discard(h)

		hooked = []
		managed_accounts = set(launched_account_map.values())
		for c in walker.clients:
			nick = launched_account_map.get(c.window_handle)
			hooked.append({'title': c.title, 'handle': c.window_handle, 'account_nick': nick})
			# Also detect accounts via player_gid for manually-hooked clients
			if not nick:
				gid = getattr(c, 'player_gid', None)
				if gid:
					vault_nick = wizlaunch.get_nickname_by_gid(gid)
					if vault_nick:
						managed_accounts.add(vault_nick)
		# Unmanaged = running wizard handles not currently managed
		managed = set(walker._managed_handles)
		unmanaged = sorted(all_handles - managed)
		return {'hooked': hooked, 'unmanaged': unmanaged, 'managed_accounts': sorted(managed_accounts), 'hooking': sorted(_hooking_in_progress)}

	def _send_hooked_clients_update():
		gui_send_queue.put(deimosgui.GUICommand(
			deimosgui.GUICommandType.UpdateHookedClients,
			_build_hooked_clients_info()
		))

	async def _init_client_attrs(client):
		"""Initialize all per-client attributes. Called once per client after hooking."""
		client_speeds[client.process_id] = await client.client_object.speed_multiplier()
		client.combat_status = False
		client.questing_status = False
		client.sigil_status = False
		client.auto_pet_status = False
		client.feeding_pet_status = False
		client.use_team_up = use_team_up
		client.dance_hook_status = False
		client.entity_detect_combat_status = False
		client.invincible_combat_timer = False
		client.just_entered_combat = None
		client.just_left_combat = False
		client.helper_clients = []
		client.client_being_helped = None
		client.original_location_before_combat = None
		client.duel_circle_joinable = True
		client.in_solo_zone = False
		client.wizard_name = None
		client.character_level = await client.stats.reference_level()
		client.discard_duplicate_cards = discard_duplicate_cards
		client.kill_minions_first = kill_minions_first
		client.automatic_team_based_combat = automatic_team_based_combat
		client.latest_drops = ''
		client.combat_config = default_config
		client.use_potions = use_potions
		client.buy_potions = buy_potions
		client.client_to_follow = client_to_follow

		# Resolve vault nickname via account-level user_id
		try:
			uid = await client.game_client.user_id()
			logger.debug(f"[GID] _init_client_attrs '{client.title}': user_id={_mask_uid(uid)}")
			if uid and uid != 0:
				client.player_gid = uid
				vault_nick = wizlaunch.get_nickname_by_gid(uid)
				if vault_nick and client.window_handle not in launched_account_map:
					launched_account_map[client.window_handle] = vault_nick
				nick = launched_account_map.get(client.window_handle)
				if nick:
					wizlaunch.update_player_gid(nick, uid)
					logger.debug(f"[GID] Saved user_id {_mask_uid(uid)} for vault account '{nick}'")
			else:
				client.player_gid = None
				logger.debug(f"[GID] _init_client_attrs '{client.title}': user_id is 0, deferring")
		except Exception as e:
			client.player_gid = None
			logger.debug(f"[GID] _init_client_attrs '{client.title}': exception {e}")

		# Set follower/leader statuses for auto questing/sigil
		if client_to_follow and client_to_follow in client.title:
			global sigil_leader_pid
			sigil_leader_pid = client.process_id
		if client_to_boost and client_to_boost in client.title:
			global questing_leader_pid
			questing_leader_pid = client.process_id

	async def handle_gui():

		async def handle_coord_error(error: wizwalker.errors.MemoryReadError):
			if await is_visible_by_path(foreground_client, play_button_path):
				return
			if await foreground_client.is_loading():
				return
			if await foreground_client.zone_name() is None:
				return
			raise wizwalker.errors.MemoryReadError(f"{error} (Occurred in zone: {current_zone})") from error

		async def _highlight_entity_loop(client, entity_info):
			"""Continuously update the highlight overlay at an entity's projected screen position."""
			ex, ey, ez, entity_height = entity_info
			half_w = entity_height * 0.3  # approximate half-width in world units
			try:
				while True:
					try:
						cam = await get_camera_state(client)
						if cam is not None:
							# Project feet and head to get screen-space bounding rect
							feet = project_point(cam, ex, ey, ez)
							head = project_point(cam, ex, ey, ez + entity_height)
							if feet is not None and head is not None:
								# Project a point offset to the right in world space for width
								rx = cam['right_x']
								ry = cam['right_y']
								center_mid = project_point(cam, ex, ey, ez + entity_height * 0.5)
								side = project_point(cam, ex + rx * half_w, ey + ry * half_w, ez + entity_height * 0.5)
								if center_mid is not None and side is not None:
									screen_hw = abs(side[0] - center_mid[0])
								else:
									# Fallback: width proportional to height
									screen_hw = abs(head[1] - feet[1]) * 0.3
								screen_hw = max(screen_hw, 10)  # minimum width
								x1 = int(center_mid[0] - screen_hw) if center_mid else int(feet[0] - screen_hw)
								x2 = int(center_mid[0] + screen_hw) if center_mid else int(feet[0] + screen_hw)
								y1 = min(head[1], feet[1])
								y2 = max(head[1], feet[1])
								gui_send_queue.put(deimosgui.GUICommand(
									deimosgui.GUICommandType.UpdateHighlightBox,
									(client.window_handle, x1, y1, x2, y2)
								))
							elif feet is not None:
								# Head behind camera - just show small box at feet
								gui_send_queue.put(deimosgui.GUICommand(
									deimosgui.GUICommandType.UpdateHighlightBox,
									(client.window_handle, feet[0] - 30, feet[1] - 60, feet[0] + 30, feet[1])
								))
							else:
								gui_send_queue.put(deimosgui.GUICommand(
									deimosgui.GUICommandType.UpdateHighlightBox, None
								))
						else:
							gui_send_queue.put(deimosgui.GUICommand(
								deimosgui.GUICommandType.UpdateHighlightBox, None
							))
					except wizwalker.errors.MemoryReadError:
						pass
					except Exception as e:
						logger.debug(f"Highlight loop error: {e}")
					await asyncio.sleep(0.033)
			except asyncio.CancelledError:
				gui_send_queue.put(deimosgui.GUICommand(
					deimosgui.GUICommandType.UpdateHighlightBox, None
				))
				return

		async def _highlight_ui_window_loop(client, name_path):
			"""Continuously update the highlight overlay at a UI window's screen position."""
			try:
				while True:
					try:
						window = await get_window_from_path(client.root_window, name_path)
						if window and window is not False:
							rect = await window.scale_to_client()
							gui_send_queue.put(deimosgui.GUICommand(
								deimosgui.GUICommandType.UpdateHighlightBox,
								(client.window_handle, rect.x1, rect.y1, rect.x2, rect.y2)
							))
						else:
							gui_send_queue.put(deimosgui.GUICommand(
								deimosgui.GUICommandType.UpdateHighlightBox, None
							))
					except wizwalker.errors.MemoryReadError:
						pass
					except Exception as e:
						logger.debug(f"UI highlight loop error: {e}")
					await asyncio.sleep(0.033)
			except asyncio.CancelledError:
				gui_send_queue.put(deimosgui.GUICommand(
					deimosgui.GUICommandType.UpdateHighlightBox, None
				))
				return

		async def _entity_stream_loop(client):
			"""Continuously fetch entity list and send to GUI, sorted by distance."""
			try:
				while True:
					try:
						sprinter = SprintyClient(client)
						entities = await sprinter.get_base_entity_list()
						player_pos = await client.body.position()
						entity_data = []
						for entity in entities:
							entity_pos = await entity.location()
							entity_name = await entity.object_name()
							gid = await entity.global_id_full()
							entity_height = 170.0
							try:
								body = await entity.actor_body()
								if body is not None:
									h = await body.height()
									s = await body.scale()
									if h > 0:
										entity_height = h * s
							except Exception:
								pass
							dx = entity_pos.x - player_pos.x
							dy = entity_pos.y - player_pos.y
							dz = entity_pos.z - player_pos.z
							distance = (dx * dx + dy * dy + dz * dz) ** 0.5
							display = f'{entity_name} (dist: {trunc(distance, 1)}) - XYZ({trunc(entity_pos.x, 3)}, {trunc(entity_pos.y, 3)}, {trunc(entity_pos.z, 3)})'
							entity_data.append({
								'name': entity_name,
								'x': entity_pos.x, 'y': entity_pos.y, 'z': entity_pos.z,
								'height': entity_height,
								'gid': 0 if entity_name == 'Player Object' else gid,
								'distance': distance,
								'display': display,
							})
						entity_data.sort(key=lambda e: e['distance'])
						gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateEntityListData, entity_data))
					except wizwalker.errors.MemoryReadError:
						pass
					except Exception as e:
						logger.debug(f"Entity stream error: {e}")
					await asyncio.sleep(1.0)
			except asyncio.CancelledError:
				return

		# GUI is started on the main thread; queues are set up before main() runs
		global gui_send_queue
		global bot_task
		global flythrough_task
		global gui_thread
		global recv_queue
		global combat_task
		global dialogue_task
		global sigil_task
		global questing_task
		global speed_task
		global auto_pet_task
		global highlight_task
		global entity_stream_task
		enemy_stats = []
		current_pos = None
		current_rotation = None

		# Pause/resume state for client disconnect resilience
		paused_task_names = None
		previous_client_count = None
		# Track total wizard handle count to detect when unmanaged clients appear/disappear
		last_known_handle_count = 0

		while True:
			if walker.clients and foreground_client:
				try:
					current_zone = await foreground_client.zone_name()
					if current_zone and not await foreground_client.is_loading():
						if await foreground_client.game_client.is_freecam():
							camera = await foreground_client.game_client.free_camera_controller()
							current_pos = await camera.position()
							current_rotation: Orient = await camera.orientation()
							current_pos.x = trunc(current_pos.x, 3)
							current_pos.y = trunc(current_pos.y, 3)
							current_pos.z = trunc(current_pos.z, 3)
							current_rotation.yaw = trunc(current_rotation.yaw, 3)
							current_rotation.pitch = trunc(current_rotation.pitch, 3)
							current_rotation.roll = trunc(current_rotation.roll, 3)
						else:
							if parent := await foreground_client.client_object.parent():
								if await parent.object_name() == "Player Object":
									children = await parent.children()
									for pet_object in children:
										current_pos = await pet_object.location()
										current_rotation = await pet_object.orientation()
								else:
									current_pos: XYZ = await foreground_client.body.position()
									current_rotation: Orient = await foreground_client.body.orientation()
									current_pos.x = trunc(current_pos.x, 3)
									current_pos.y = trunc(current_pos.y, 3)
									current_pos.z = trunc(current_pos.z, 3)
									current_rotation.yaw = trunc(current_rotation.yaw, 3)
									current_rotation.pitch = trunc(current_rotation.pitch, 3)
									current_rotation.roll = trunc(current_rotation.roll, 3)
					else:
						current_pos: XYZ = XYZ(0, 0, 0)
						current_rotation: Orient = Orient(0, 0, 0)

					gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('Title', f'Client: {foreground_client.title}')))
					gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('Zone', f'Zone: {current_zone}')))
					gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('xyz', f'Position (XYZ): {current_pos.x}, {current_pos.y}, {current_pos.z}')))
					gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('pry', f'Orientation (PRY): {current_rotation.pitch}, {current_rotation.roll}, {current_rotation.yaw}')))
				except Exception:
					# Client process likely closed — remove dead clients, keep title gaps
					count_before = len(walker.clients)
					dead = walker.remove_dead_clients()
					if dead:
						# Clean up managed handles so get_new_clients() can detect relaunched clients
						for c in dead:
							if c.window_handle in walker._managed_handles:
								walker._managed_handles.remove(c.window_handle)
							launched_account_map.pop(c.window_handle, None)
							_hooking_in_progress.discard(c.window_handle)
							logger.info(f"Client '{c.title}' disconnected.")
						_send_hooked_clients_update()

						# Record which tasks were active, then cancel them all
						active_tasks = set()
						task_vars = {
							"combat": combat_task,
							"dialogue": dialogue_task,
							"sigil": sigil_task,
							"questing": questing_task,
							"speed": speed_task,
							"bot": bot_task,
							"auto_pet": auto_pet_task,
						}
						for name, task in task_vars.items():
							if task is not None and not task.cancelled():
								active_tasks.add(name)
								task.cancel()

						if "combat" in active_tasks:
							combat_task = None
						if "dialogue" in active_tasks:
							dialogue_task = None
						if "sigil" in active_tasks:
							sigil_task = None
						if "questing" in active_tasks:
							questing_task = None
						if "speed" in active_tasks:
							speed_task = None
						if "bot" in active_tasks:
							bot_task = None
						if "auto_pet" in active_tasks:
							auto_pet_task = None

						# Reset per-client status flags on remaining alive clients
						for c in walker.clients:
							c.combat_status = False
							c.sigil_status = False
							c.questing_status = False
							c.feeding_pet_status = False
							c.entity_detect_combat_status = False

						if active_tasks:
							previous_client_count = count_before
							paused_task_names = active_tasks
							logger.info(f"Client(s) disconnected. Bot tasks paused. Waiting for client count to be restored ({len(walker.clients)}/{previous_client_count}).")
							if "bot" in active_tasks:
								logger.warning("Bot script was interrupted and cannot be auto-resumed. Please restart it manually.")

						if not walker.clients:
							gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('Title', f'Client: None')))
							gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('Zone', f'Zone: ')))
							gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('xyz', f'Position (XYZ): ')))
							gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('pry', f'Orientation (PRY): ')))
					await asyncio.sleep(0.5)
			elif not walker.clients:
				await asyncio.sleep(0.1)

			# Retry user_id resolution for hooked clients that don't have one yet
			if initial_setup_complete and walker.clients:
				for c in walker.clients:
					if getattr(c, 'player_gid', None) is None:
						try:
							uid = await c.game_client.user_id()
							if uid and uid != 0:
								logger.debug(f"[GID] Retry resolved '{c.title}': user_id={_mask_uid(uid)}")
								c.player_gid = uid
								vault_nick = wizlaunch.get_nickname_by_gid(uid)
								if vault_nick and c.window_handle not in launched_account_map:
									launched_account_map[c.window_handle] = vault_nick
									_send_hooked_clients_update()
								nick = launched_account_map.get(c.window_handle)
								if nick:
									wizlaunch.update_player_gid(nick, uid)
									logger.debug(f"[GID] Retry saved user_id {_mask_uid(uid)} for '{nick}'")
									_send_hooked_clients_update()
							else:
								logger.debug(f"[GID] Retry '{c.title}': user_id still 0")
						except Exception as e:
							logger.debug(f"[GID] Retry '{c.title}': exception {e}")

			# Continuous detection — only auto-hook vault-launched clients
			if initial_setup_complete and not paused_task_names:
				all_handles = set(get_all_wizard_handles())
				managed = set(walker._managed_handles)
				unmanaged = all_handles - managed - released_handles

				# Auto-hook any unmanaged handle that was launched via the vault (in launch order)
				hooked_any = False
				launch_order = [h for h in launched_account_map if h in unmanaged]
				for handle in launch_order:
						walker._managed_handles.append(handle)
						nc = walker.client_cls(handle)
						walker.clients.append(nc)
						existing_nums = set()
						for c in walker.clients:
							if c.title.startswith('p') and c.title[1:].isdigit():
								existing_nums.add(int(c.title[1:]))
						num = 1
						while num in existing_nums:
							num += 1
						nc.title = f'p{num}'
						_hooking_in_progress.add(handle)
						_send_hooked_clients_update()
						try:
							await nc.activate_hooks()
							await _init_client_attrs(nc)
							logger.info(f"Auto-hooked vault-launched client '{nc.title}' ({launched_account_map[handle]}).")
							hooked_any = True
						except wizwalker.errors.HookAlreadyActivated:
							await _init_client_attrs(nc)
							logger.info(f"Auto-hooked vault-launched client '{nc.title}' ({launched_account_map[handle]}, already hooked).")
							hooked_any = True
						except Exception as e:
							logger.error(f"Failed to auto-hook vault-launched client (handle {handle}): {e}")
							walker._managed_handles.remove(handle)
							walker.clients.remove(nc)
						finally:
							_hooking_in_progress.discard(handle)

				if hooked_any:
					_send_hooked_clients_update()
					last_known_handle_count = len(get_all_wizard_handles())
					_restart_always_on_tasks()
					_restart_active_toggle_tasks()
				else:
					# Check if handle count changed (wizard window opened/closed externally)
					current_handle_count = len(all_handles)
					if current_handle_count != last_known_handle_count:
						last_known_handle_count = current_handle_count
						_send_hooked_clients_update()

			# Poll for new clients when in paused state (waiting for reconnection)
			if paused_task_names and len(walker.clients) < previous_client_count:
				new_clients = walker.get_new_clients()
				if new_clients:
					# Assign titles — fill gaps using the next available number
					existing_nums = set()
					for c in walker.clients:
						if c.title.startswith('p') and c.title[1:].isdigit():
							existing_nums.add(int(c.title[1:]))

					for nc in new_clients:
						num = 1
						while num in existing_nums:
							num += 1
						nc.title = f'p{num}'
						existing_nums.add(num)

					# Hook new clients individually
					for nc in new_clients:
						_hooking_in_progress.add(nc.window_handle)
						_send_hooked_clients_update()
						try:
							await nc.activate_hooks()
						except wizwalker.errors.HookAlreadyActivated:
							logger.debug(f"Client '{nc.title}' already hooked, skipping.")
						except Exception as e:
							logger.error(f"Failed to hook client '{nc.title}': {e}")
						finally:
							_hooking_in_progress.discard(nc.window_handle)
						await _init_client_attrs(nc)
						logger.info(f"New client '{nc.title}' hooked.")
					_send_hooked_clients_update()

					# Check if count restored
					if len(walker.clients) >= previous_client_count:
						# Re-enable tasks that were active before disconnect
						resumable = paused_task_names - {"bot"}
						for name in resumable:
							if name == "combat":
								for c in walker.clients:
									c.combat_status = True
								combat_task = asyncio.create_task(try_task_coro(combat_loop, walker.clients, True))
							elif name == "dialogue":
								dialogue_task = asyncio.create_task(try_task_coro(dialogue_loop, walker.clients, True))
							elif name == "sigil":
								for c in walker.clients:
									c.sigil_status = True
								sigil_task = asyncio.create_task(try_task_coro(sigil_loop, walker.clients, True))
							elif name == "questing":
								for c in walker.clients:
									c.questing_status = True
								questing_task = asyncio.create_task(try_task_coro(questing_loop, walker.clients, True))
							elif name == "speed":
								speed_task = asyncio.create_task(try_task_coro(speed_switching, walker.clients))
							elif name == "auto_pet":
								for c in walker.clients:
									c.feeding_pet_status = True
								auto_pet_task = asyncio.create_task(try_task_coro(auto_pet_loop, walker.clients, True))

						previous_client_count = None
						paused_task_names = None
						_restart_always_on_tasks()
						logger.info("Client count restored. Resuming bot tasks.")

			# Stuff sent by the window
			try:
			# Eat as much as the queue gives us. We will be freed by exception
				while True:
					com = recv_queue.get_nowait()
					match com.com_type:
						case deimosgui.GUICommandType.Close:
							if len(walker.clients) != 0:
								raise deimosgui.ToolClosedException
							os._exit(0) # "Fuck you, you're getting terminated homeboy" - Slack
						case deimosgui.GUICommandType.AttemptedClose:
							if not walker.clients:
								os._exit(0)
							raise deimosgui.ToolClosedException
						case deimosgui.GUICommandType.ToggleOption:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							match com.data:
								case GUIKeys.toggle_speedhack:
									await toggle_speed_hotkey()
								case GUIKeys.toggle_combat:
									await toggle_combat_hotkey()
								case GUIKeys.toggle_dialogue:
									await toggle_dialogue_hotkey()
								case GUIKeys.toggle_sigil:
									await toggle_sigil_hotkey()
								case GUIKeys.toggle_questing:
									await toggle_questing_hotkey()
								case GUIKeys.toggle_auto_pet:
									await toggle_auto_pet_hotkey()
								case GUIKeys.toggle_auto_potion:
									await toggle_auto_potion_hotkey()
								case GUIKeys.toggle_freecam:
									await toggle_freecam_hotkey()
								# case 'Side Quests':
								# 	await toggle_side_quests()
								case GUIKeys.toggle_camera_collision:
									if foreground_client:
										camera: ElasticCameraController = await foreground_client.game_client.elastic_camera_controller()
										collision_status = await camera.check_collisions()
										collision_status ^= True
										logger.debug(f'Camera Collisions {bool_to_string(collision_status)}')
										await camera.write_check_collisions(collision_status)
								case GUIKeys.toggle_show_expanded_logs:
									gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateConsole))
								case _:
									logger.debug(f'Unknown window toggle: {com.data}')
						case deimosgui.GUICommandType.Copy:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							match com.data:
								case GUIKeys.copy_zone:
									logger.debug('Copied Zone')
									pyperclip.copy(current_zone)
								case GUIKeys.copy_position:
									logger.debug('Copied Position')
									pyperclip.copy(f'XYZ({current_pos.x}, {current_pos.y}, {current_pos.z})')
								case GUIKeys.copy_rotation:
									logger.debug('Copied Rotation')
									pyperclip.copy(f'Orient({current_rotation.pitch}, {current_rotation.roll}, {current_rotation.yaw})')
								case GUIKeys.copy_entity_list:
									if foreground_client:
										logger.debug('Opening Entity List')
										gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.ShowEntityListPopup))
								case GUIKeys.copy_camera_position:
									if foreground_client:
										camera = await foreground_client.game_client.selected_camera_controller()
										camera_pos = await camera.position()
										logger.debug('Copied Selected Camera Position')
										pyperclip.copy(f'XYZ({camera_pos.x}, {camera_pos.y}, {camera_pos.z})')
								case GUIKeys.copy_camera_rotation:
									if foreground_client:
										camera = await foreground_client.game_client.selected_camera_controller()
										camera_pitch, camera_roll, camera_yaw = await camera.orientation()
										logger.debug('Copied Camera Rotations')
										pyperclip.copy(f'Orient({camera_pitch}, {camera_roll}, {camera_pitch})')
								case GUIKeys.copy_ui_tree:
									if foreground_client:
										foreground: Client = foreground_client
										ui_tree = ''
										ui_tree_texts = {}
										ui_tree_windows = []
										async def collect_node(window: Window, depth: int = 0, depth_symbol: str = '-'):
											name, type_name, children = await asyncio.gather(
												window.name(),
												window.maybe_read_type_name(),
												utils.wait_for_non_error(window.children),
											)
											line = f"{depth_symbol * depth} [{name}] {type_name}"
											child_results = await asyncio.gather(*(collect_node(c, depth + 1) for c in children))
											return [(line, window)] + [entry for sub in child_results for entry in sub]
										ui_tree_windows = await collect_node(foreground.root_window)
										ui_tree = '\n'.join(line for line, _ in ui_tree_windows) + '\n'
										async def _safe_text(line, window):
											try:
												text = await window.maybe_text()
												if text:
													ui_tree_texts[line] = text
											except Exception:
												pass
										await asyncio.gather(*(_safe_text(l, w) for l, w in ui_tree_windows))
										logger.debug(f'Copied UI Tree for client {foreground.title}')
										pyperclip.copy(ui_tree)
										# with open('ui_tree.txt', 'w') as f:
										# 	f.write(ui_tree)
										if ui_tree:
											logger.success("Available UI Paths:")
											gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.ShowUITreePopup, (ui_tree, ui_tree_texts)))
										else:
											logger.error("Failed to load UI tree. Please try again.")
								case GUIKeys.copy_stats:
									if enemy_stats:
										logger.debug('Copied Stats')
										pyperclip.copy('\n'.join(enemy_stats))
									else:
										logger.info('No stats are loaded. Select an enemy index corresponding to its position on the duel circle, then click the copy button.')
								
								case GUIKeys.copy_logs:
									gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.CopyConsole, None))
								case _:
									logger.debug(f'Unknown copy value: {com.data}')
						case deimosgui.GUICommandType.Teleport:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							match com.data:
								case GUIKeys.hotkey_quest_tp:
									await navmap_teleport_hotkey()
								case GUIKeys.mass_hotkey_mass_tp:
									await mass_navmap_teleport_hotkey()
								case GUIKeys.hotkey_freecam_tp:
									await tp_to_freecam_hotkey()
								case _:
									logger.debug(f'Unknown teleport type: {com.data}')
						case deimosgui.GUICommandType.CustomTeleport:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							if foreground_client:
								x_input = param_input(com.data['X'], current_pos.x)
								y_input = param_input(com.data['Y'], current_pos.y)
								z_input = param_input(com.data['Z'], current_pos.z)
								yaw_input = param_input(com.data['Yaw'], current_rotation.yaw)
								custom_xyz = XYZ(x=x_input, y=y_input, z=z_input)
								logger.debug(f'Teleporting client {foreground_client.title} to {custom_xyz}, yaw= {yaw_input}')
								await foreground_client.teleport(custom_xyz)
								await foreground_client.body.write_yaw(yaw_input)
						case deimosgui.GUICommandType.EntityTeleport:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							if foreground_client:
								sprinter = SprintyClient(foreground_client)
								gid_str = com.data.get('gid', '') if isinstance(com.data, dict) else ''
								name_str = com.data.get('name', '') if isinstance(com.data, dict) else str(com.data)
								target_entity = None
								if gid_str:
									try:
										target_gid = int(gid_str)
										entities = await sprinter.get_base_entity_list()
										for entity in entities:
											if await entity.global_id_full() == target_gid:
												target_entity = entity
												break
									except (ValueError, TypeError):
										logger.error(f'Invalid GID: {gid_str}')
								if target_entity is None and name_str:
									entities = await sprinter.get_base_entities_with_vague_name(name_str)
									if entities:
										target_entity = await sprinter.find_closest_of_entities(entities)
								if target_entity:
									entity_pos = await target_entity.location()
									await foreground_client.teleport(entity_pos)
						case deimosgui.GUICommandType.SelectEnemy:
							if not walker.clients:
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindowValues, ('EnemyInput', [])))
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindowValues, ('AllyInput', [])))
								continue
							if foreground_client and await foreground_client.in_battle():
								ally_index, enemy_index, base_damage, school_id, crit_status, force_school_status, swapped, view_side = com.data
								if not base_damage:
									base_damage = None
								else:
									base_damage = int(base_damage)
								view_target = (view_side == 'enemy')
								result = await total_stats(foreground_client, ally_index, enemy_index, base_damage, school_id, crit_status, force_school_status, swapped=swapped, view_target=view_target)
								if result is None:
									continue
								stat_lines, ally_names, enemy_names, ally_i, enemy_i, school_name, slot_info = result
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('stat_viewer', stat_lines)))
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindowValues, ('EnemyInput', enemy_names)))
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindowValues, ('AllyInput', ally_names)))
								if enemy_i < len(enemy_names):
									gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('EnemyInput', enemy_names[enemy_i])))
								if ally_i < len(ally_names):
									gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('AllyInput', ally_names[ally_i])))
								# school_name not sent to dropdown — but sent as calc_school for readout
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('calc_school', school_name)))
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('slot_info', slot_info)))
							else:
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindowValues, ('EnemyInput', [])))
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindowValues, ('AllyInput', [])))
						case deimosgui.GUICommandType.XYZSync:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							await xyz_sync_hotkey()
						case deimosgui.GUICommandType.XPress:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							await x_press_hotkey()
						case deimosgui.GUICommandType.FriendTeleport:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							await friend_teleport_sync_hotkey()
						# case deimosgui.GUICommandType.ToggleDialogueSideQuests:
					# 	if not walker.clients:
					# 		logger.info("This GUI option requires hooks to be active, skipping.")
					# 		continue
					# 	await toggle_dialogue_side_quests_hotkey()
						case deimosgui.GUICommandType.RebindHotkey:
							action_id, new_key, new_mods = com.data
							# Remove old binding from listener if active
							old_binding = _active_bindings.get(action_id)
							if old_binding:
								old_mods = ModifierKeys.NOREPEAT
								for m in old_binding.get("modifiers", []):
									old_mods |= ModifierKeys[m]
								try:
									await listener.remove_hotkey(Keycode[old_binding["key"]], modifiers=old_mods)
								except Exception:
									pass
								del _active_bindings[action_id]
							# Register new binding
							if new_key:
								callback = _kill_tool_callback if action_id == "kill_tool" else _make_hotkey_callback(action_id)
								if hotkey_status or action_id == "kill_tool":
									mods = ModifierKeys.NOREPEAT
									for m in new_mods:
										mods |= ModifierKeys[m]
									try:
										await listener.add_hotkey(Keycode[new_key], callback, modifiers=mods)
										_active_bindings[action_id] = {"key": new_key, "modifiers": new_mods}
									except Exception as e:
										logger.debug(f'Failed to register rebound hotkey for {action_id}: {e}')
							else:
								pass  # settings already cleared by GUI side
							logger.debug(f'Hotkey rebound: {action_id} -> {new_key} {new_mods}')
						case deimosgui.GUICommandType.AnchorCam:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							if foreground_client:
								if freecam_status:
									await toggle_freecam_hotkey()
								camera = await foreground_client.game_client.elastic_camera_controller()
								sprinter = SprintyClient(foreground_client)
								gid_str = com.data.get('gid', '') if isinstance(com.data, dict) else ''
								name_str = com.data.get('name', '') if isinstance(com.data, dict) else str(com.data)
								target_entity = None
								if gid_str:
									try:
										target_gid = int(gid_str)
										entities = await sprinter.get_base_entity_list()
										for entity in entities:
											if await entity.global_id_full() == target_gid:
												target_entity = entity
												break
									except (ValueError, TypeError):
										logger.error(f'Invalid GID: {gid_str}')
								if target_entity is None and name_str:
									entities = await sprinter.get_base_entities_with_vague_name(name_str)
									if entities:
										target_entity = await sprinter.find_closest_of_entities(entities)
								if target_entity:
									entity_name = await target_entity.object_name()
									logger.debug(f'Anchoring camera to entity {entity_name}')
									await camera.write_attached_client_object(target_entity)
						# case deimosgui.GUICommandType.SetPetWorld:
						# 	if (com.data[1] is None):
						# 		logger.debug('Invalid pet world selected!')
						# 	else:
						# 		logger.debug(f'Setting Auto Pet World to {com.data[1]}')
						# 		assign_pet_level(com.data[1])
						case deimosgui.GUICommandType.SetCamPosition:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							if foreground_client:
								if not freecam_status:
									await toggle_freecam_hotkey()
								camera: DynamicCameraController = await foreground_client.game_client.selected_camera_controller()
								camera_pos: XYZ = await camera.position()
								camera_pitch, camera_roll, camera_yaw = await camera.orientation()
								x_input = param_input(com.data['X'], camera_pos.x)
								y_input = param_input(com.data['Y'], camera_pos.y)
								z_input = param_input(com.data['Z'], camera_pos.z)
								yaw_input = param_input(com.data['Yaw'], camera_yaw)
								roll_input = param_input(com.data['Roll'], camera_roll)
								pitch_input = param_input(com.data['Pitch'], camera_pitch)
								input_pos = XYZ(x_input, y_input, z_input)
								logger.debug(f'Teleporting Camera to {input_pos}, yaw={yaw_input}, roll={roll_input}, pitch={pitch_input}')
								await camera.write_position(input_pos)
								await camera.update_orientation(Orient(pitch_input, roll_input, yaw_input))
						case deimosgui.GUICommandType.SetCamDistance:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							if foreground_client:
								camera = await foreground_client.game_client.elastic_camera_controller()
								current_zoom = await camera.distance()
								current_min = await camera.min_distance()
								current_max = await camera.max_distance()
								distance_input = param_input(com.data["Distance"], current_zoom)
								min_input = param_input(com.data["Min"], current_min)
								max_input = param_input(com.data["Max"], current_max)
								logger.debug(f'Setting camera distance to {distance_input}, min={min_input}, max={max_input}')
								if com.data["Distance"]:
									await camera.write_distance_target(distance_input)
									await camera.write_distance(distance_input)
								if com.data["Min"]:
									await camera.write_min_distance(min_input)
									await camera.write_zoom_resolution(min_input)
								if com.data["Max"]:
									await camera.write_max_distance(max_input)
						case deimosgui.GUICommandType.PopulateCamera:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							if foreground_client:
								camera = await foreground_client.game_client.selected_camera_controller()
								camera_pos = await camera.position()
								camera_pitch, camera_roll, camera_yaw = await camera.orientation()
								elastic_camera = await foreground_client.game_client.elastic_camera_controller()
								current_zoom = await elastic_camera.distance()
								current_min = await elastic_camera.min_distance()
								current_max = await elastic_camera.max_distance()
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('CamXInput', f'{camera_pos.x:.2f}')))
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('CamYInput', f'{camera_pos.y:.2f}')))
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('CamZInput', f'{camera_pos.z:.2f}')))
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('CamYawInput', f'{camera_yaw:.2f}')))
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('CamRollInput', f'{camera_roll:.2f}')))
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('CamPitchInput', f'{camera_pitch:.2f}')))
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('CamEntityInput', 'Player Object')))
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('CamDistanceInput', f'{current_zoom:.2f}')))
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('CamMinInput', f'{current_min:.2f}')))
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('CamMaxInput', f'{current_max:.2f}')))
								logger.debug('Populated camera fields with current values.')
						case deimosgui.GUICommandType.PopulatePlayerGID:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							if foreground_client:
								gid = await foreground_client.game_client.player_gid()
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('CamEntityGIDInput', str(gid))))
						case deimosgui.GUICommandType.GoToZone:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							if foreground_client:
								clients = [foreground_client]
								if com.data[0]:
									for c in background_clients:
										clients.append(c)
								zoneChanged = await toZoneDisplayName(clients, com.data[1])
								if zoneChanged == 0:
									logger.debug('Reached destination zone: ' + await foreground_client.zone_name())
								else:
									logger.error('Failed to go to zone.  It may be spelled incorrectly, or may not be supported.')
						case deimosgui.GUICommandType.GoToWorld:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							if foreground_client:
								clients = [foreground_client]
								if com.data[0]:
									for c in background_clients:
										clients.append(c)
								await to_world(clients, com.data[1])
						case deimosgui.GUICommandType.GoToBazaar:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							if foreground_client:
								clients = [foreground_client]
								if com.data:
									for c in background_clients:
										clients.append(c)
								zoneChanged = await toZone(clients, 'WizardCity/WC_Streets/Interiors/WC_OldeTown_AuctionHouse')
								if zoneChanged == 0:
									logger.debug('Reached destination zone: ' + await foreground_client.zone_name())
								else:
									logger.error('Failed to go to zone.  It may be spelled incorrectly, or may not be supported.')
						case deimosgui.GUICommandType.RefillPotions:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							if foreground_client:
								clients = [foreground_client]
								if com.data:
									for c in background_clients:
										clients.append(c)
								await asyncio.gather(*[auto_potions_force_buy(client, True) for client in clients])
						case deimosgui.GUICommandType.ExecuteFlythrough:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							async def _flythrough():
								try:
									await execute_flythrough(foreground_client, com.data)
									await foreground_client.camera_elastic()
								finally:
									gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('FlythroughStatus', 'Disabled')))
							if foreground_client:
								flythrough_task = asyncio.create_task(_flythrough())
								gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('FlythroughStatus', 'Enabled')))
						case deimosgui.GUICommandType.KillFlythrough:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							if flythrough_task is not None and not flythrough_task.cancelled():
								flythrough_task.cancel()
								flythrough_task = None
								await asyncio.sleep(0)
								await foreground_client.camera_elastic()
							gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('FlythroughStatus', 'Disabled')))
						case deimosgui.GUICommandType.HighlightEntity:
							if highlight_task and not highlight_task.done():
								highlight_task.cancel()
							if foreground_client and com.data:
								highlight_task = asyncio.create_task(
									_highlight_entity_loop(foreground_client, com.data))

						case deimosgui.GUICommandType.HighlightUIWindow:
							if highlight_task and not highlight_task.done():
								highlight_task.cancel()
							if foreground_client and com.data:
								highlight_task = asyncio.create_task(
									_highlight_ui_window_loop(foreground_client, com.data))

						case deimosgui.GUICommandType.ClearHighlight:
							if highlight_task and not highlight_task.done():
								highlight_task.cancel()
								highlight_task = None
							gui_send_queue.put(deimosgui.GUICommand(
								deimosgui.GUICommandType.UpdateHighlightBox, None
							))

						case deimosgui.GUICommandType.StartEntityStream:
							if entity_stream_task and not entity_stream_task.done():
								entity_stream_task.cancel()
							if foreground_client:
								entity_stream_task = asyncio.create_task(_entity_stream_loop(foreground_client))

						case deimosgui.GUICommandType.StopEntityStream:
							if entity_stream_task and not entity_stream_task.done():
								entity_stream_task.cancel()
								entity_stream_task = None

						case deimosgui.GUICommandType.ExecuteBot:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							command_data: str = com.data
							expert_mode = command_data.startswith("###deimos_expertmode")
							async def run_bot():
								logger.debug('Started Bot')
								if expert_mode:
									while True:
										v = vm.VM(walker.clients)
										try:
											v.load_from_text(command_data)
											v.running = True
											while v.running:
												await v.step()
										except Exception as e:
											logger.exception(e)
										v.running = False
										if v.killed:
											break
										await asyncio.sleep(1)
								else:
									split_commands = command_data.splitlines()
									web_commands_strs = ['webpage', 'pull', 'embed']
									new_commands = []
									for command_str in split_commands:
										command_tokens = tokenize(command_str)
										if command_tokens and command_tokens[0].lower in web_commands_strs:
											web_commands = read_webpage(command_tokens[1])
											new_commands.extend(web_commands)
										else:
											new_commands.append(command_str)
									while True:
										for command_str in new_commands:
											await parse_command(walker.clients, command_str)
										await asyncio.sleep(1)
							if bot_task is not None and not bot_task.cancelled():
								bot_task.cancel()
								logger.debug('Bot Killed')
								bot_task = None
							bot_task = asyncio.create_task(try_task_coro(run_bot, walker.clients, True))
							bot_task.add_done_callback(lambda _t: gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('BotStatus', 'Disabled'))))
							gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('BotStatus', 'Enabled')))
						case deimosgui.GUICommandType.KillBot:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							if bot_task is not None and not bot_task.cancelled():
								bot_task.cancel()
								logger.debug('Bot Killed')
								bot_task = None
						case deimosgui.GUICommandType.SetPlaystyles:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							combat_configs = delegate_combat_configs(str(com.data), len(walker.clients))
							for i, client in enumerate(walker.clients):
								client.combat_config = combat_configs.get(i, default_config)
							await toggle_combat_hotkey(False)
							await toggle_combat_hotkey(False)
						case deimosgui.GUICommandType.SetScale:
							if not walker.clients:
								logger.info("This GUI option requires hooks to be active, skipping.")
								continue
							desired_scale = param_input(com.data, 1.0)
							logger.debug(f'Set Scale to {desired_scale}')
							await asyncio.gather(*[client.body.write_scale(desired_scale) for client in walker.clients])

						case deimosgui.GUICommandType.LoadAccounts:
							gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateAccountList, wizlaunch.list_accounts()))

						case deimosgui.GUICommandType.SaveAccount:
							nickname = com.data
							try:
								await asyncio.to_thread(wizlaunch.prompt_save_account, nickname)
								logger.info(f"Account '{nickname}' saved.")
							except RuntimeError as e:
								logger.info(f"Account save cancelled or failed: {e}")
							gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateAccountList, wizlaunch.list_accounts()))

						case deimosgui.GUICommandType.DeleteAccount:
							wizlaunch.delete_account(com.data)
							logger.info(f"Account '{com.data}' removed.")
							gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateAccountList, wizlaunch.list_accounts()))

						case deimosgui.GUICommandType.LaunchInstance:
							nicknames, game_path = com.data
							if not game_path:
								game_path = str(utils.get_wiz_install())
							else:
								utils.override_wiz_install_location(game_path)
							# Filter out accounts already managed (hooked) by launch map or player_gid
							already_managed = set(launched_account_map.values())
							for c in walker.clients:
								gid = getattr(c, 'player_gid', None)
								if gid:
									vault_nick = wizlaunch.get_nickname_by_gid(gid)
									if vault_nick:
										already_managed.add(vault_nick)
							nicknames = [n for n in nicknames if n not in already_managed]
							if not nicknames:
								logger.info("All selected accounts are already launched and hooked.")
							else:
								logger.info(f"Launching {len(nicknames)} instance(s)...")
							# Clear any released handles so newly launched clients get auto-hooked
							released_handles.clear()
							gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.ClearLaunchCheckboxes))
							try:
								results = await asyncio.to_thread(wizlaunch.launch_instances, nicknames, game_path)
								for nickname, handle in results.items():
									launched_account_map[handle] = nickname
									logger.info(f"Launched and logged in '{nickname}'.")
							except Exception as e:
								logger.error(f"Error launching instances: {e}")


						case deimosgui.GUICommandType.ReorderAccounts:
							wizlaunch.reorder_accounts(com.data)

						case deimosgui.GUICommandType.ReorderClients:
							handles = com.data
							client_map = {c.window_handle: c for c in walker.clients}
							new_order = [client_map[h] for h in handles if h in client_map]
							remaining = [c for c in walker.clients if c.window_handle not in set(handles)]
							walker.clients[:] = new_order + remaining
							for i, c in enumerate(walker.clients):
								c.title = f'p{i + 1}'
							_send_hooked_clients_update()

						case deimosgui.GUICommandType.UnhookClient:
							handle = com.data
							for c in walker.clients[:]:
								if c.window_handle == handle:
									try:
										c.title = 'Wizard101'
										await c.close()
									except Exception:
										pass
									if c.window_handle in walker._managed_handles:
										walker._managed_handles.remove(c.window_handle)
									walker.clients.remove(c)
									released_handles.add(handle)
									logger.info(f"Unhooked client (handle {handle}).")
									break
							_send_hooked_clients_update()
							if walker.clients:
								_restart_always_on_tasks()
								_restart_active_toggle_tasks()

						case deimosgui.GUICommandType.HookClient:
							handle = com.data
							# Remove from released set so it can be managed
							released_handles.discard(handle)
							# Check handle is still valid and not already managed
							if handle in walker._managed_handles:
								logger.debug(f"Handle {handle} already managed, skipping.")
								_send_hooked_clients_update()
								continue
							all_handles = get_all_wizard_handles()
							if handle not in all_handles:
								logger.error(f"Handle {handle} no longer exists.")
								_send_hooked_clients_update()
								continue
							# Create client, assign title, hook, init
							walker._managed_handles.append(handle)
							nc = walker.client_cls(handle)
							walker.clients.append(nc)
							existing_nums = set()
							for c in walker.clients:
								if c.title.startswith('p') and c.title[1:].isdigit():
									existing_nums.add(int(c.title[1:]))
							num = 1
							while num in existing_nums:
								num += 1
							nc.title = f'p{num}'
							_hooking_in_progress.add(handle)
							_send_hooked_clients_update()
							try:
								await nc.activate_hooks()
								await _init_client_attrs(nc)
								logger.info(f"Manually hooked client '{nc.title}' (handle {handle}).")
							except wizwalker.errors.HookAlreadyActivated:
								await _init_client_attrs(nc)
								logger.info(f"Manually hooked client '{nc.title}' (handle {handle}, already hooked).")
							except Exception as e:
								logger.error(f"Failed to hook client (handle {handle}): {e}")
								walker._managed_handles.remove(handle)
								walker.clients.remove(nc)
								_hooking_in_progress.discard(handle)
								_send_hooked_clients_update()
								continue
							_hooking_in_progress.discard(handle)
							_send_hooked_clients_update()
							_restart_always_on_tasks()
							_restart_active_toggle_tasks()

						case deimosgui.GUICommandType.KillClient:
							handle = com.data
							# If handle belongs to a hooked client, unhook first
							for c in walker.clients[:]:
								if c.window_handle == handle:
									try:
										c.title = 'Wizard101'
										await c.close()
									except Exception:
										pass
									if c.window_handle in walker._managed_handles:
										walker._managed_handles.remove(c.window_handle)
									walker.clients.remove(c)
									launched_account_map.pop(handle, None)
									break
							# Terminate the OS process
							_kill_process_by_handle(handle)
							released_handles.discard(handle)
							logger.info(f"Killed client (handle {handle}).")
							_send_hooked_clients_update()
							if walker.clients:
								_restart_always_on_tasks()
								_restart_active_toggle_tasks()

						case deimosgui.GUICommandType.RelaunchClient:
							handle, nickname = com.data
							# Unhook the hooked client
							for c in walker.clients[:]:
								if c.window_handle == handle:
									try:
										c.title = 'Wizard101'
										await c.close()
									except Exception:
										pass
									if c.window_handle in walker._managed_handles:
										walker._managed_handles.remove(c.window_handle)
									walker.clients.remove(c)
									launched_account_map.pop(handle, None)
									break
							# Kill the process
							_kill_process_by_handle(handle)
							released_handles.discard(handle)
							logger.info(f"Killed client for relaunch (handle {handle}, account '{nickname}').")
							_send_hooked_clients_update()
							# Relaunch via wizlaunch (credentials stay in Rust)
							try:
								game_path = str(utils.get_wiz_install())
								await asyncio.sleep(1)
								new_handle = await asyncio.to_thread(wizlaunch.launch_instance, nickname, game_path)
								launched_account_map[new_handle] = nickname
								logger.info(f"Relaunched and logged in '{nickname}'.")
								_send_hooked_clients_update()
							except Exception as e:
								logger.error(f"Error relaunching '{nickname}': {e}")
							if walker.clients:
								_restart_always_on_tasks()
								_restart_active_toggle_tasks()

						case deimosgui.GUICommandType.UpdateSettings:
							global speed_multiplier, use_potions, rpc_status, drop_status, anti_afk_status
							global buy_potions, use_team_up, client_to_follow, client_to_boost
							global questing_friend_tp, gear_switching_in_solo_zones, hitter_client
							global ignore_pet_level_up, only_play_dance_game
							global kill_minions_first, automatic_team_based_combat, discard_duplicate_cards
							settings_dict = com.data
							for key, value in settings_dict.items():
								match key:
									case 'speed_multiplier': speed_multiplier = value
									case 'use_potions': use_potions = value
									case 'rich_presence': rpc_status = value
									case 'drop_logging': drop_status = value
									case 'use_anti_afk': anti_afk_status = value
									case 'buy_potions': buy_potions = value
									case 'use_team_up': use_team_up = value
									case 'client_to_follow': client_to_follow = value
									case 'client_to_boost': client_to_boost = value
									case 'friend_teleport': questing_friend_tp = value
									case 'gear_switching_in_solo_zones': gear_switching_in_solo_zones = value
									case 'hitter_client': hitter_client = value
									case 'ignore_pet_level_up': ignore_pet_level_up = value
									case 'only_play_dance_game': only_play_dance_game = value
									case 'kill_minions_first': kill_minions_first = value
									case 'automatic_team_based_combat': automatic_team_based_combat = value
									case 'discard_duplicate_cards': discard_duplicate_cards = value
							logger.debug(f'Settings updated: {list(settings_dict.keys())}')

			except queue.Empty:
				pass

			if walker.clients:
				gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.UpdateWindow, ('Auto PetStatus', bool_to_string(auto_pet_status))))
			
			await asyncio.sleep(0.1)

		else:
			while True:
				await asyncio.sleep(1)

	async def potion_usage_loop():
		# Auto potion usage on a per client basis.
		async def async_potion(client: Client):
			if use_potions:
				while True:
					await asyncio.sleep(1)
					if auto_potion_status and await is_free(client) and not any([freecam_status, client.sigil_status, client.questing_status]):
						await auto_potions(client, buy = False)

		await asyncio.gather(*[async_potion(p) for p in walker.clients])


	async def rpc_loop():
		if not rpc_status:
			return

		async def _close_rpc(rpc):
			"""Close RPC and its underlying transport to avoid ResourceWarning."""
			try:
				if hasattr(rpc, 'sock_writer') and rpc.sock_writer:
					rpc.sock_writer.close()
					await rpc.sock_writer.wait_closed()
			except Exception:
				pass
			try:
				await rpc.close()
			except Exception:
				pass

		rpc = None
		client: Client = None
		while True:
			# Connect / reconnect
			if rpc is None:
				try:
					rpc = AioPresence(1000159655357587566)
					await rpc.connect()
				except Exception as e:
					logger.debug(f'Discord RPC connection failed: {e}')
					await _close_rpc(rpc)
					rpc = None
					await asyncio.sleep(15)
					continue

			await asyncio.sleep(1)

			# Disconnect RPC when no clients are managed
			if not walker.clients:
				if rpc is not None:
					try:
						await rpc.clear()
					except Exception:
						pass
					await _close_rpc(rpc)
					rpc = None
				client = None
				continue

			# Pick the foreground client, or fall back to first
			client = walker.clients[0]
			for c in walker.clients:
				if c.is_foreground:
					client = c
					break

			# If our tracked client was removed, reset
			if client not in walker.clients:
				client = walker.clients[0]

			try:
				zone_name = await client.zone_name()
			except Exception:
				client = None
				continue

			if zone_name:
				zone_list = zone_name.split('/')
				if len(zone_list):
					status_str = zone_list[0]
				else:
					status_str = zone_name

				# parse zone name and make it more visually appealing
				if len(zone_list) > 1:
					if 'Housing_' in zone_name:
						status_str = status_str.replace('Housing_', '')
						end_zone_list = zone_list[-1].split('_')
						end_zone = f' - {end_zone_list[-1]}'

					elif 'Housing' in zone_name:
						end_zone_list = zone_list[-1].split('_')

						if 'School' in zone_list:
							status_str = end_zone_list[0] + 'House'

						else:
							status_str = zone_list[1]

						end_zone = f' - {end_zone_list[-1]}'

					else:
						end_zone = None

					if not end_zone:
						area_list: list[str] = zone_list[-1].split('_')
						del area_list[0]

						for a in area_list.copy():
							if any([s.isdigit() for s in a]):
								area_list.remove(a)

						seperator = ' '
						area = seperator.join(area_list)
						zone_word_list = re.findall('[A-Z][^A-Z]*', area)
						if zone_word_list:
							end_zone = f' - {seperator.join(zone_word_list)}'

						else:
							end_zone = ''

			else:
				end_zone = ''

			status_str = status_str.replace('DragonSpire', 'Dragonspyre')
			status_list = status_str.split('_')
			if len(status_list[0]) <= 3:
				del status_list[0]

			seperator = ' '
			status_str = seperator.join(status_list)

			status_list = re.findall('[A-Z][^A-Z]*', status_str)
			status_str = seperator.join(status_list)

			if 'ext' in end_zone.lower():
				end_zone = ' - Outside'

			elif 'int' in end_zone.lower():
				end_zone = ' - Inside'

			try:
				in_battle = await client.in_battle()
			except Exception:
				client = None
				continue

			if in_battle:
				task_str = 'Fighting '

			elif questing_status:
				task_str = 'Questing '

			elif sigil_status:
				task_str = 'Farming '

			else:
				task_str = ''

			# Assign if a client is currently selected or not
			if not any([c.is_foreground for c in walker.clients]):
				details_pane = 'Idle'

			else:
				details_pane = 'Active'

			try:
				# Update the discord RPC status
				await rpc.update(state=f'{task_str}In {status_str}{end_zone}', details=details_pane)

			except Exception:
				await _close_rpc(rpc)
				rpc = None


	def ban_thread():
		shake = discsdk.serialize_message(
			discsdk.Opcodes.Handshake,
			{
				"v": discsdk.rpc_version,
				"client_id": str(discsdk.app_id)
			}
		)
		while True:
			try:
				banlistcontents = requests.get(f"https://raw.githubusercontent.com/{tool_author}/{tool_name.lower()}-bans/main/{tool_name}Bans.txt").content.decode()
				banlist = set([x.split(" ")[0].strip() for x in banlistcontents.splitlines()])

				handle = discsdk.connect()
				discsdk.send(handle, shake)
				resp = discsdk.recv(handle)
				discsdk.close(handle)

				user_id = resp["data"]["user"]["id"]
				if user_id in banlist:
					break
			except:
				pass

			time.sleep(5 * 60)


	async def drop_logging_loop():
		# Auto potion usage on a per client basis.
		await asyncio.gather(*[logging_loop(p) for p in walker.clients])


	async def zone_check_loop():
		zone_blacklist = [
			'Raids',
			'Battlegrounds'
		]

		explicit_zone_blacklist = [
			'WizardCity/WC_Duel_Arena_New',
			'WizardCity/KT_Duel_Arena',
			'WizardCity/MB_Arena',
			'WizardCity/MS_Arena',
			'WizardCity/DS_Arena',
			'WizardCity/CL_Arena',
			'WizardCity/ZF_Arena',
			'WizardCity/AV_Arena',
			'WizardCity/AZ_Arena',
			'WizardCity/PA_Arena',
			'WizardCity/GH_Arena',
			'WizardCity/LM_Arena'

		]

		async def async_zone_check(client: Client):
			while True:
				await asyncio.sleep(0.25)
				zone_name = await client.zone_name()
				if zone_name in explicit_zone_blacklist:
					logger.critical(f'Client {client.title} entered area with known anticheat, killing {tool_name}.')
					await kill_tool(False)
				if zone_name and '/' in zone_name:
					split_zone_name = zone_name.split('/')

					if any([i in split_zone_name[0] for i in zone_blacklist]):
						logger.critical(f'Client {client.title} entered area with known anticheat, killing {tool_name}.')
						await kill_tool(False)

		await asyncio.gather(*[async_zone_check(p) for p in walker.clients])


	await asyncio.sleep(0)
	global walker
	walker = ClientHandler()
	# walker.clients = []
	global gui_task
	gui_task = asyncio.create_task(handle_gui())
	await asyncio.sleep(2)
	# logger.debug("1")

	async def ban_watcher():
		known_ban = False
		try:
			rkey = winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Slackaduts\Deimos", access=winreg.KEY_READ)
			a = winreg.QueryValueEx(rkey, "badboy")[0]
			known_ban = a != 0
		except:
			pass

		if not known_ban:
			ban_task = threading.Thread(target=ban_thread)
			ban_task.daemon = True # make thread die with deimos if it exist
			ban_task.start()
			while ban_task.is_alive():
				await asyncio.sleep(1)
		try:
			rkey = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Slackaduts\Deimos", access=winreg.KEY_ALL_ACCESS)
			winreg.SetValueEx(rkey, "badboy", 0, winreg.REG_DWORD, 1)
		except:
			pass
		cMessageBox(None, "Deimos has encountered a fatal error (Code 0C24). Please contact slackaduts on discord for more info.", "Deimos error", 0x10 | 0x1000)
		sys.exit(0)


	async def hooking_logic():
		await asyncio.sleep(0.1)
		if not get_all_wizard_handles():
			logger.debug('Waiting for a Wizard101 client to be opened...')
			while not get_all_wizard_handles():
				await asyncio.sleep(1)
		override_wiz_install_using_handle()
		logger.debug('Wizard101 client(s) detected. Hook clients from the Launcher tab.')
	await hooking_logic()
	logger.debug('Ready. Hook clients from the Launcher tab.')
	global client_speeds
	client_speeds = {}
	_send_hooked_clients_update()
	initial_setup_complete = True

	# Register kill_tool hotkey (always bound, separate from enable/disable cycle)
	_kill_binding = settings.get_hotkeys().get("kill_tool")
	if _kill_binding:
		_kill_mods = ModifierKeys.NOREPEAT
		for _m in _kill_binding.get("modifiers", []):
			_kill_mods |= ModifierKeys[_m]
		await listener.add_hotkey(Keycode[_kill_binding["key"]], kill_tool_hotkey, modifiers=_kill_mods)
		_active_bindings["kill_tool"] = _kill_binding
	await enable_hotkeys()
	logger.debug('Hotkeys ready!')
	tool_status = True
	exc = None

	async def tool_active():
		while tool_status:
			await asyncio.sleep(0.1)

	all_tasks = {}

	# Names of always-on tasks that use walker.clients snapshots and must be
	# restarted when the client list changes.
	SNAPSHOT_TASK_NAMES = [
		'anti_afk_loop', 'is_client_in_combat_loop', 'entity_detect_combat_loop',
		'potion_usage_loop', 'drop_logging_loop', 'zone_check_loop', 'anti_afk_questing_loop'
	]
	SNAPSHOT_TASK_FUNCS = {
		'anti_afk_loop': anti_afk_loop,
		'is_client_in_combat_loop': is_client_in_combat_loop,
		'entity_detect_combat_loop': entity_detect_combat_loop,
		'potion_usage_loop': potion_usage_loop,
		'drop_logging_loop': drop_logging_loop,
		'zone_check_loop': zone_check_loop,
		'anti_afk_questing_loop': anti_afk_questing_loop,
	}

	def _restart_always_on_tasks():
		"""Cancel and recreate snapshot-based always-on tasks so they pick up new clients."""
		for name in SNAPSHOT_TASK_NAMES:
			old = all_tasks.get(name)
			if old is not None and not old.cancelled():
				old.cancel()
			all_tasks[name] = asyncio.create_task(SNAPSHOT_TASK_FUNCS[name]())

	def _restart_active_toggle_tasks():
		"""Cancel and recreate any currently-active toggle tasks so they pick up new clients."""
		global combat_task, dialogue_task, sigil_task, questing_task, speed_task, auto_pet_task

		if combat_task is not None and not combat_task.cancelled():
			combat_task.cancel()
			for c in walker.clients:
				c.combat_status = True
			combat_task = asyncio.create_task(try_task_coro(combat_loop, walker.clients, True))

		if dialogue_task is not None and not dialogue_task.cancelled():
			dialogue_task.cancel()
			dialogue_task = asyncio.create_task(try_task_coro(dialogue_loop, walker.clients, True))

		if sigil_task is not None and not sigil_task.cancelled():
			sigil_task.cancel()
			for c in walker.clients:
				c.sigil_status = True
			sigil_task = asyncio.create_task(try_task_coro(sigil_loop, walker.clients, True))

		if questing_task is not None and not questing_task.cancelled():
			questing_task.cancel()
			for c in walker.clients:
				c.questing_status = True
			questing_task = asyncio.create_task(try_task_coro(questing_loop, walker.clients, True))

		if speed_task is not None and not speed_task.cancelled():
			speed_task.cancel()
			speed_task = asyncio.create_task(try_task_coro(speed_switching, walker.clients))

		if auto_pet_task is not None and not auto_pet_task.cancelled():
			auto_pet_task.cancel()
			for c in walker.clients:
				c.feeding_pet_status = True
			auto_pet_task = asyncio.create_task(try_task_coro(auto_pet_loop, walker.clients, True))

	try:
		all_tasks['foreground_client_switching'] = asyncio.create_task(foreground_client_switching())
		all_tasks['assign_foreground_clients'] = asyncio.create_task(assign_foreground_clients())
		all_tasks['anti_afk_loop'] = asyncio.create_task(anti_afk_loop())
		all_tasks['is_client_in_combat_loop'] = asyncio.create_task(is_client_in_combat_loop())
		all_tasks['entity_detect_combat_loop'] = asyncio.create_task(entity_detect_combat_loop())
		all_tasks['potion_usage_loop'] = asyncio.create_task(potion_usage_loop())
		all_tasks['rpc_loop'] = asyncio.create_task(rpc_loop())
		all_tasks['drop_logging_loop'] = asyncio.create_task(drop_logging_loop())
		all_tasks['zone_check_loop'] = asyncio.create_task(zone_check_loop())
		all_tasks['anti_afk_questing_loop'] = asyncio.create_task(anti_afk_questing_loop())
		all_tasks['ban_watcher'] = asyncio.create_task(ban_watcher())
		all_tasks['tool_active'] = asyncio.create_task(tool_active())
		all_tasks['gui'] = gui_task

		while True:
			pending = [t for t in all_tasks.values() if t is not None and not t.done()]
			if not pending:
				break
			done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_EXCEPTION)

			should_exit = False
			for t in done:
				exc = t.exception()
				if exc is None:
					continue
				elif isinstance(exc, deimosgui.ToolClosedException):
					logger.info("Tool close triggered by user.")
					should_exit = True
				elif t == all_tasks.get('gui'):
					# GUI task errors are always fatal
					logger.opt(exception=exc).error("GUI task crashed")
					should_exit = True
				else:
					# Client-dependent task died (memory error, dead process, etc.)
					# Non-fatal — the client is likely closed
					task_name = next((k for k, v in all_tasks.items() if v is t), '?')
					logger.opt(exception=exc).warning(f"Task '{task_name}' ended")
			if should_exit:
				break

	finally:
		for task in all_tasks.values():
			if task is not None and not task.cancelled():
				task.cancel()
		# Also cancel any active toggle tasks
		for task in [combat_task, dialogue_task, sigil_task, questing_task, speed_task, auto_pet_task, bot_task]:
			if task is not None and not task.cancelled():
				task.cancel()

		await tool_finish()
		# Signal GUI thread that unhooking is done so it can exit cleanly
		try:
			gui_send_queue.put(deimosgui.GUICommand(deimosgui.GUICommandType.Close))
		except Exception:
			pass


def bool_to_string(input: bool):
	if input:
		return 'Enabled'

	else:
		return 'Disabled'


# def handle_tool_updating():
# 	version = get_latest_version()
# 	update_server = None

# 	try:
# 		update_server = read_webpage(f"{repo_path_raw}/LatestVersion.txt")
# 	except Exception as e:
# 		print(f"Exception \"{type(e).__name__}\" occured when checking for updates: \"{e}\"")
# 		return
	
# 	if update_server is None:
# 		return

# 	if update_server is not None and update_server[1].lower() == 'false':
# 		raise KeyboardInterrupt

# 	if update_server is not None:
# 		version_specific_data = update_server[2:]
# 		version_status_check = ' '.join(version_specific_data)

# 		if tool_version in version_status_check:
# 			version_status_index = index_with_str(version_specific_data, tool_version)
# 			version_status = version_specific_data[version_status_index].split(' ')[1]

# 			if version_status.lower() == 'false':
# 				raise KeyboardInterrupt

# 			elif version_status.lower() == 'force':
# 				auto_update()

# 		if version and auto_updating:
# 			if is_version_greater(version, tool_version):
# 				auto_update()

# 			if not is_version_greater(tool_version, version):
# 				config_update()


if __name__ == "__main__":
	# Validate configs and update the tool
	# handle_tool_updating()

	current_log = logger.add(f"logs/{tool_name} - {generate_timestamp()}.log", encoding='utf-8', enqueue=True, backtrace=True)

	# Set up GUI queues before starting anything
	gui_send_queue = queue.Queue()
	recv_queue = queue.Queue()

	# Run async backend in a background thread so the GUI can run on the main thread (required by Qt)
	backend_thread = threading.Thread(target=lambda: asyncio.run(main()), daemon=True)
	backend_thread.start()

	# Run GUI on the main thread (swap queue order: sending from window = receiving from backend)
	deimosgui.manage_gui(recv_queue, gui_send_queue, theme_dict, tool_name, tool_version, gui_on_top, gui_langcode, gui_font, gui_font_size, tool_author, settings=settings)

	logger.remove(current_log)
