from wizwalker import Client
from wizwalker.memory.memory_objects.window import Window
from wizwalker.memory.memory_object import Primitive
from src.utils import get_window_from_path, is_visible_by_path
from src.paths import chat_window_path, main_chat_channel_path, group_chat_channel_path, house_chat_channel_path, friend_chat_channel_path, channel_one_chat_channel_path, channel_two_chat_channel_path, channel_three_chat_channel_path, guild_chat_channel_path, team_up_chat_channel_path
from typing import List
from loguru import logger
import re
import asyncio

# CREDIT TO AARON FOR IMPLEMENTING THIS ORIGINALLY, IM REDOING HIS IMPLEMENTATION HERE -slack

drop_types = [
    'PetSnack',
    'Reagent',
    'Housing',
    'Pet',
    'Shoes',
    'Seed',
    'Jewel',
    'Robe',
    'Hat',
    'Athame',
    'Weapon',
    'Deck',
    'Ring',
    'Amulet',
]

chat_channel_list = [
    main_chat_channel_path, 
    group_chat_channel_path, 
    house_chat_channel_path, 
    friend_chat_channel_path, 
    channel_one_chat_channel_path, 
    channel_two_chat_channel_path, 
    channel_three_chat_channel_path, 
    guild_chat_channel_path, 
    team_up_chat_channel_path
]


async def get_chat(client: Client) -> str:
    # Returns the text directly from the chat window
    if await is_visible_by_path(client, chat_window_path):
        chat_window = await get_window_from_path(client.root_window, chat_window_path)
        if chat_window:
            raw_chat_text = await chat_window.maybe_text()
            return raw_chat_text

        else:
            return ''

    else:
        return ''


async def get_current_active_chat_channel(client: Client) -> List[str]:
    for window_path in chat_channel_list:
        if await is_visible_by_path(client, window_path):
            channel_window = await get_window_from_path(client.root_window, window_path)
            if channel_window:
                if await channel_window.read_value_from_offset(872, Primitive.bool): # value for if the channel is active
                    return window_path
    
    return None # this should not happen


def filter_drops(input_list: List[str]) -> List[str]:
    # Takes in a list of chat window text and only returns the item drops.
    drops = []

    for raw_i in input_list.copy():
        # Ensures this message came from the system and not another player, it's safe to assume no player will ever say this
        if 'Art_Chat_System.dds' in raw_i:
            # Matches everything after "> <"
            i = re.findall('(?<=> <).*|$', raw_i)[0]

            if i:
                # Matches everything after ; and before >, excluding both
                if ';' in i:
                    drop_type: str = re.findall('(?<=;).*?[^>]*|$', i)[0]

                if drop_type in drop_types:
                    # Match everything in between > <
                    raw_drop: str = re.findall('>.*?<|$', i)[0]
                    # Remove arrow brackets
                    drop: str = re.findall('[^>]+[^<]+|$', raw_drop)[0]
                    drop = drop.replace(' ', '', 1)
                    drops.append(drop)

            elif ':' in raw_i.lower():
                # Matches everything after : and before >, excluding both
                drop: str = re.findall('(?<=:).*?[^<]*|$', raw_i)[0]
                drop = drop.replace(' ', '', 1)
                drops.append(drop)

    return drops


def find_new_stuff(old: str, new: str) -> str:
    # CREDIT TO SIROLAF FOR THIS FUNCTION
	found_idx = -1

	while True:
		found_idx = new.find(old)
		if found_idx >= 0:
			break
		old = old[1:]
		if len(old) == 0:
			break

	if found_idx < 0:
		return new # entire string is new
	return new[found_idx+len(old):]


async def logging_loop(client: Client):
    # TODO: Finish this loop and create a system for determining new drops
    chat_text = await get_chat(client)
    if chat_text:
        temp_drops = filter_drops(chat_text.split('\n'))
        client.latest_drops = '\n'.join(temp_drops)
    current_channel = await get_current_active_chat_channel(client)
    while True:
        await asyncio.sleep(1)

        if await is_visible_by_path(client, chat_window_path):
            chat_text = await get_chat(client)
            #if chat_text:
            temp_drops = filter_drops(chat_text.split('\n'))
            temp_channel = await get_current_active_chat_channel(client)
            if current_channel != temp_channel:
                client.latest_drops = '\n'.join(temp_drops)
                current_channel = temp_channel
            else:
                new_drops = find_new_stuff(client.latest_drops, '\n'.join(temp_drops))
                client.latest_drops = '\n'.join(temp_drops)

                if new_drops:
                    new_drops_list = new_drops.split('\n')
                    if len(new_drops_list) > 1 and not new_drops_list[0]:
                        new_drops_list.pop(0)
                    [logger.debug(f'{client.title} - New Drop: {drop}') for drop in new_drops_list]
