import asyncio
import re
from asyncio import Task as AsyncTask, TaskGroup

from wizwalker import AddressOutOfRange, Client, XYZ, Keycode, MemoryReadError, Primitive
from wizwalker.memory import DynamicClientObject
from wizwalker.memory.memory_objects.quest_data import QuestData, GoalData
from wizwalker.extensions.wizsprinter import SprintyClient
from wizwalker.extensions.wizsprinter.wiz_sprinter import Coroutine, upgrade_clients
from wizwalker.extensions.wizsprinter.wiz_navigator import toZone
from wizwalker.extensions.scripting.deck_builder import DeckBuilder
from src.teleport_math import navmap_tp, calc_Distance
from src.deck_encoder import DeckEncoderDecoder

from wizwalker.extensions.scripting.utils import _maybe_get_named_window, _cycle_to_online_friends, _click_on_friend, _friend_list_entry
from src.utils import _cycle_friends_list

from .tokenizer import *
from .parser import *
from .ir import *

from src.drop_logger import get_chat, filter_drops, find_new_stuff
from src.auto_pet import dancedance
from src.dance_game_hook import attempt_activate_dance_hook
from src.utils import is_visible_by_path, is_free, get_window_from_path, refill_potions, refill_potions_if_needed \
                    , logout_and_in, click_window_by_path, get_quest_name
from src.command_parser import teleport_to_friend_from_list
from src.config_combat import delegate_combat_configs, default_config

from loguru import logger

class Task:
    def __init__(self, stack=None, ip=0):
        self.stack = stack or []
        self.ip = ip
        self.running = True  # Task is active unless marked otherwise
        self.waitfor:AsyncTask|None = None

class Scheduler:
    def __init__(self):
        # a task represents a stack
        self.tasks:list[Task] = []
        self.current_task_index = 0

    def add_task(self, task):
        self.tasks.append(task)

    def remove_task(self, task):
        self.tasks.remove(task)

    def get_current_task(self):
        return self.tasks[self.current_task_index]

    def switch_task(self):
        self.current_task_index = (self.current_task_index + 1) % len(self.tasks)


class VMError(Exception):
    pass


class UntilInfo:
    def __init__(self, expr: Expression, id: int, exit_point: int, stack_size: int):
        self.expr = expr
        self.id = id
        self.exit_point = exit_point
        self.stack_size = stack_size


class VM:
    def __init__(self, clients: list[Client]):
        self._clients = upgrade_clients(clients) # guarantee it's usable
        self.program: list[Instruction] = []
        self.running = False
        self.killed = False
        self._scheduler = Scheduler()
        self._scheduler.add_task(Task())
        self.current_task = self._scheduler.get_current_task()
        self._any_player_client = [] # Using this to store the client(s) that satisfied the condition of any player
        self._timers = {}
        self.logged_data = {
            'goal': {},
            'quest': {},
            'zone': {}
        }
        self._constants = {
            'True': True,
            'False': False,
        } 

        # Every until loop condition must be checked for every vm step.
        # Once a condition becomes True, all untils that were entered later must be exited and removed.
        # This means that the stack must be rolled back to the index stored here and the rhs of this list is discarded.
        self._until_infos: list[UntilInfo] = []

    def reset(self):
        self.program = []
        for _ in self._scheduler.tasks:
            self._scheduler.tasks.pop()
        self._scheduler.add_task(Task())
        self.current_task = self._scheduler.get_current_task()
        self._until_infos = []
        self._timers = {}
        self._any_player_client = []
        self._constants = {
            'True': True,
            'False': False,
        }
        self.logged_data = {
            'goal': {},
            'quest': {},
            'zone': {}
        }


    def stop(self):
        self.running = False

    def kill(self):
        self.stop()
        self.killed = True

    
    async def define_constant(self, name, value):
        # Special handling for Keycode constants
        if isinstance(value, str) and hasattr(Keycode, value):
            value = getattr(Keycode, value)
        self._constants[name] = value

    def load_from_text(self, code: str):
        compiler = Compiler.from_text(code)
        self.program = compiler.compile()
        #self.program = self.test_program

    def player_by_num(self, num: int) -> SprintyClient:
        i = num - 1
        if i >= len(self._clients):
            return None
            #tail = "client is open" if len(self._clients) == 1 else "clients are open"
            #raise VMError(f"Attempted to get client {num}, but only {len(self._clients)} {tail}")
        return self._clients[i]

    async def select_friend_from_list(self, client: SprintyClient, name: str):
        async with client.mouse_handler:
            try:
                friends_window = await _maybe_get_named_window(
                    client.root_window, "NewFriendsListWindow"
                )
                if not await friends_window.is_visible():
                    raise ValueError("Friends list not visible")
            except ValueError:
                friend_button = await _maybe_get_named_window(client.root_window, "btnFriends")
                await client.mouse_handler.click_window(friend_button)
                await asyncio.sleep(0.4)
                friends_window = await _maybe_get_named_window(
                    client.root_window, "NewFriendsListWindow"
                )

            await _cycle_to_online_friends(client, friends_window)

            friends_list_window = await _maybe_get_named_window(friends_window, "listFriends")
            
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

            # Find and select the friend
            friend, friend_index = await _cycle_friends_list(
                client,
                right_button,
                friends_list_window,
                None,
                None,
                name,
                current_page,
            )

            if friend is None:
                logger.error(f"Could not find friend with name {name}")
                return False

            # Click on the friend to select them
            await _click_on_friend(client, friends_list_window, friend_index)
            
            return True
    def _select_players(self, selector: PlayerSelector) -> list[SprintyClient]:
        if selector.mass:
            return self._clients
        elif selector.any_player:
            return []
        elif selector.same_any:
            return self._any_player_client
        else:
            result: list[SprintyClient] = []
            if selector.inverted:
                for i in range(len(self._clients)):
                    if i + 1 in selector.player_nums:
                        continue
                    result.append(self.player_by_num(i + 1))
            else:
                for num in selector.player_nums:
                    client = self.player_by_num(num)
                    if client:  # Only add the client if it exists
                        result.append(client)
            return result
            
    async def _fetch_tracked_quest(self, client: SprintyClient) -> QuestData:
        tracked_id = await client.quest_id()
        qm = await client.quest_manager()
        for quest_id, quest in (await qm.quest_data()).items():
            if quest_id == tracked_id:
                return quest
        raise VMError(f"Unable to fetch the currently tracked quest for client with title {client.title}")

    async def _fetch_tracked_quest_text(self, client: SprintyClient) -> str:
        quest = await self._fetch_tracked_quest(client)
        name_key = await quest.name_lang_key()
        name: str = await client.cache_handler.get_langcode_name(name_key)
        return name.lower().strip()

    async def _fetch_quests(self, client: SprintyClient) -> list[tuple[int, QuestData]]:
        result = []
        qm = await client.quest_manager()
        for quest_id, quest in (await qm.quest_data()).items():
            result.append((quest_id, quest))
        return result

    async def _fetch_quest_text(self, client: SprintyClient, quest: QuestData) -> str:
        name_key = await quest.name_lang_key()
        if name_key == "Quest Finder":
            name = name_key
        else:
            name: str = await client.cache_handler.get_langcode_name(name_key)
        return name.lower().strip()

    async def _fetch_tracked_goal_text(self, client: SprintyClient) -> str:
        goal_txt = await get_quest_name(client)
        goal_txt = re.sub(r'<[^>]*>', '', goal_txt)
        if '(' in goal_txt:
            goal_txt = goal_txt[:goal_txt.find("(")]
        return goal_txt.lower().strip()

    async def _check_drops(self, client: SprintyClient, item_name: str) -> bool:
        chat_text = await get_chat(client)
        if not chat_text:
            return False
            
        drops = filter_drops(chat_text.split('\n'))

        if not hasattr(client, '_last_chat_state'):
            client._last_chat_state = ''
        
        new_chat_content = find_new_stuff(client._last_chat_state, '\n'.join(drops))
        client._last_chat_state = '\n'.join(drops)
        
        # If there are no new drops, return False
        if not new_chat_content:
            return False
        
        # Check if any new drops match the item_name
        new_drops = new_chat_content.split('\n')
        for drop in new_drops:
            if drop and item_name.lower() in drop.lower():
                logger.debug(f"Found new dropped item matching '{item_name}': {drop}")
                return True
                        
        return False
    
    async def _check_duel_round(self, client: SprintyClient) -> int:
        try:
            if not await client.in_battle():
                return 0
                
            duel = client.duel
            if duel:
                current_round = await duel.round_num()
                return current_round
            return 0
        except Exception as e:
            logger.error(f"Error getting duel round: {e}")
            return 0
    
    async def _extract_data_info(self, data):
        if isinstance(data, str):
            # Check if this is a constant reference (starts with $)
            if data.startswith('$'):
                const_name = data[1:]
                if const_name in self._constants:
                    return self._constants[const_name]
                else:
                    logger.warning(f"Constant '{const_name}' not found")
                    return data
            return data
        elif hasattr(data, 'string'):
            # Check if string expression is a constant reference
            if data.string.startswith('$'):
                const_name = data.string[1:]
                if const_name in self._constants:
                    return self._constants[const_name]
                else:
                    logger.warning(f"Constant '{const_name}' not found")
                    return data.string
            return data.string
        elif hasattr(data, 'ident'):
            ident = data.ident
            # First check if this is a constant reference
            if ident.startswith('$'):
                const_name = ident[1:]
                if const_name in self._constants:
                    return self._constants[const_name]
                else:
                    logger.warning(f"Constant '{const_name}' not found")
                    return ident
            # Then check if the identifier itself is a constant
            elif ident in self._constants:
                return self._constants[ident]
            else:
                try:
                    return await self.eval(data)
                except Exception as e:
                    logger.error(f"Failed to evaluate identifier {ident}: {e}")
                    return ident
        elif isinstance(data, list) and all(isinstance(item, str) for item in data):
            return "/".join(data)
            
        # For any other expression type, try to evaluate it
        else:
            try:
                return await self.eval(data)
            except Exception as e:
                logger.error(f"Failed to extract zone name: {e}")
                return str(data)

    async def _eval_command_expression(self, expression: CommandExpression):
        assert expression.command.kind == CommandKind.expr
        assert type(expression.command.data) is list

        if not expression.command.data:
            return False

        assert type(expression.command.data[0]) is ExprKind


        selector = expression.command.player_selector
        assert selector is not None
        clients = self._select_players(selector)
        
        # If no clients match the selector and it's not an any_player selector, return False
        if not clients and not selector.any_player:
            return False
        
        match expression.command.data[0]:
            case ExprKind.constant_check:
                constant_name = expression.command.data[1]
                expected_value = expression.command.data[2]
                
                if constant_name in self._constants:
                    actual_value = self._constants[constant_name] 
                    # Handle string representations of booleans
                    if isinstance(expected_value, bool) and isinstance(actual_value, str):
                        if actual_value.lower() == "true":
                            actual_value = True
                        elif actual_value.lower() == "false":
                            actual_value = False
                    
                    return actual_value == expected_value
                return False
            
            case ExprKind.zone_changed:
                expected_zone = None
                if len(expression.command.data) > 1:
                    expected_zone = await self._extract_data_info(expression.command.data[1])
                
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    
                    for client in self._clients:
                        current_zone = await client.zone_name()
                        last_zone = self.logged_data['zone'].get(client.title, None)
                        
                        if current_zone is None:
                            continue
                            
                        if expected_zone:
                            if current_zone.lower() == expected_zone.lower():
                                self._any_player_client.append(client)
                                self.logged_data['zone'][client.title] = current_zone
                                found_any = True
                        else:
                            if last_zone is None:
                                self.logged_data['zone'][client.title] = current_zone.lower()
                            elif current_zone.lower() != last_zone.lower():
                                self._any_player_client.append(client)
                                self.logged_data['zone'][client.title] = current_zone.lower()
                                found_any = True
                                
                    return found_any
                else:
                    all_valid = True
                    
                    for client in clients:
                        current_zone = await client.zone_name()
                        last_zone = self.logged_data['zone'].get(client.title, None)
                        
                        if current_zone is None:
                            all_valid = False
                            if not expected_zone:
                                continue
                            else:
                                break
                                
                        if expected_zone:
                            if current_zone.lower() != expected_zone.lower():
                                all_valid = False
                                break
                            self.logged_data['zone'][client.title] = current_zone
                        else:
                            if last_zone is None:
                                self.logged_data['zone'][client.title] = current_zone.lower()
                                all_valid = False
                            elif current_zone.lower() == last_zone.lower():
                                all_valid = False
                            else:
                                self.logged_data['zone'][client.title] = current_zone.lower()
                                
                    return all_valid
            case ExprKind.goal_changed:
                expected_goal = None
                if len(expression.command.data) > 1:
                    expected_goal = await self._extract_data_info(expression.command.data[1])
                    
                    if expected_goal is None:
                        logger.error("Failed to extract goal name from expression")
                        return False
                    expected_goal = expected_goal.lower()
                
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    
                    for client in self._clients:
                        current_goal = await self._fetch_tracked_goal_text(client)
                        if current_goal is not None:
                            current_goal = current_goal.lower()
                        last_goal = self.logged_data['goal'].get(client.title, None)
                        
                        if expected_goal:
                            if current_goal == expected_goal:
                                self._any_player_client.append(client)
                                self.logged_data['goal'][client.title] = current_goal
                                found_any = True
                        else:
                            if last_goal is None:
                                self.logged_data['goal'][client.title] = current_goal
                            elif current_goal != last_goal:
                                self._any_player_client.append(client)
                                self.logged_data['goal'][client.title] = current_goal
                                found_any = True
                                
                    return found_any
                else:
                    all_valid = True
                    
                    for client in clients:
                        current_goal = await self._fetch_tracked_goal_text(client)
                        if current_goal is not None:
                            current_goal = current_goal.lower()
                        last_goal = self.logged_data['goal'].get(client.title, None)
                        
                        if expected_goal:
                            if current_goal != expected_goal:
                                all_valid = False
                                break
                            self.logged_data['goal'][client.title] = current_goal
                        else:
                            if last_goal is None:
                                self.logged_data['goal'][client.title] = current_goal
                                all_valid = False
                            elif current_goal == last_goal:
                                all_valid = False
                            else:
                                self.logged_data['goal'][client.title] = current_goal
                                
                    return all_valid

            case ExprKind.quest_changed:
                if len(expression.command.data) > 1:
                    quest_data = expression.command.data[1]
                    expected_quest = await self._extract_data_info(quest_data)
                    
                    if expected_quest is None:
                        logger.error("Failed to extract quest name from expression")
                        return False
                    
                    expected_quest = expected_quest.lower()
                    
                    if selector.any_player:
                        self._any_player_client = []
                        found_any = False
                        for client in self._clients:
                            current_quest = await self._fetch_tracked_quest_text(client)
                            if current_quest is not None:
                                current_quest = current_quest.lower()
                            last_quest = self.logged_data['quest'].get(client.title, None)
                            
                            if current_quest == expected_quest and (last_quest is None or current_quest != last_quest):
                                self._any_player_client.append(client)
                                self.logged_data['quest'][client.title] = current_quest
                                found_any = True
                        return found_any
                    else:
                        all_match = True
                        for client in clients:
                            current_quest = await self._fetch_tracked_quest_text(client)
                            if current_quest is not None:
                                current_quest = current_quest.lower()
                            last_quest = self.logged_data['quest'].get(client.title, None)
                            
                            if current_quest != expected_quest or (last_quest is not None and current_quest == last_quest):
                                all_match = False
                                break
                            
                            self.logged_data['quest'][client.title] = current_quest
                        return all_match
                else:
                    if selector.any_player:
                        self._any_player_client = []
                        found_any = False
                        for client in self._clients:
                            current_quest = await self._fetch_tracked_quest_text(client)
                            if current_quest is not None:
                                current_quest = current_quest.lower()
                            last_quest = self.logged_data['quest'].get(client.title, None)
                            
                            if last_quest is None:
                                self.logged_data['quest'][client.title] = current_quest
                            elif current_quest != last_quest:
                                self._any_player_client.append(client)
                                self.logged_data['quest'][client.title] = current_quest
                                found_any = True
                        return found_any
                    else:
                        all_changed = True
                        for client in clients:
                            current_quest = await self._fetch_tracked_quest_text(client)
                            if current_quest is not None:
                                current_quest = current_quest.lower()
                            last_quest = self.logged_data['quest'].get(client.title, None)
                            
                            if last_quest is None:
                                self.logged_data['quest'][client.title] = current_quest
                                all_changed = False
                            elif current_quest == last_quest:
                                all_changed = False
                            else:
                                self.logged_data['quest'][client.title] = current_quest
                        return all_changed

            case ExprKind.duel_round:
                expected_round = await self._extract_data_info(expression.command.data[1])
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    for client in self._clients:
                        current_round = await self._check_duel_round(client)
                        if current_round == expected_round:
                            self._any_player_client.append(client)
                            found_any = True
                    return found_any
                else:
                    for client in clients:
                        current_round = await self._check_duel_round(client)
                        if current_round != expected_round:
                            return False
                    return True
            case ExprKind.items_dropped:
                item_name = await self._extract_data_info(expression.command.data[1])
                assert type(item_name) == str
                
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    for client in self._clients:
                        if await self._check_drops(client, item_name):
                            self._any_player_client.append(client)
                            found_any = True
                    return found_any
                else:
                    for client in clients:
                        if not await self._check_drops(client, item_name):
                            return False
                    return True
            case ExprKind.window_visible:
                path = await self._extract_data_info(expression.command.data[1])
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    for client in self._clients:
                        if isinstance(path, IdentExpression):
                            path = await self.eval(path)
                        if await is_visible_by_path(client, path):
                            self._any_player_client.append(client)
                            found_any = True
                    return found_any
                else:
                    for client in clients:
                        if isinstance(path, IdentExpression):
                            path = await self.eval(path)
                        if not await is_visible_by_path(client, path):
                            return False
                    return True
            case ExprKind.window_disabled:
                path = await self._extract_data_info(expression.command.data[1])
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    for client in self._clients:
                        if isinstance(path, IdentExpression):
                            path = await self.eval(path)
                        root = client.root_window
                        window = await get_window_from_path(root, path)
                        if window != False and await window.is_control_grayed():
                            self._any_player_client.append(client)
                            found_any = True
                    return found_any
                else:
                    for client in clients:
                        if isinstance(path, IdentExpression):
                            path = await self.eval(path)
                        root = client.root_window
                        window = await get_window_from_path(root, path)
                        if window == False:
                            return False
                        elif not await window.is_control_grayed():
                            return False
                    return True
            case ExprKind.in_range: # NOTE: if client is playing as pet, they are counted as an entity
                data = [await c.client_object.global_id_full() for c in clients]
                target = await self._extract_data_info(expression.command.data[1])
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    for client in self._clients:
                        entities = await client.get_base_entity_list()
                        for entity in entities:
                            entity_name = await entity.object_name()
                            entity_gid = await entity.global_id_full()
                            
                            if entity_gid in data: continue
                            if not entity_name: continue
                            # Check if target is a substring of entity_name
                            if target.lower() in entity_name.lower() or entity_name.lower() == target.lower():
                                self._any_player_client.append(client)
                                found_any = True
                                break
                    return found_any
                else:
                    for client in clients:
                        entities = await client.get_base_entity_list()
                        found = False
                        for entity in entities:
                            entity_name = await entity.object_name()
                            entity_gid = await entity.global_id_full()

                            if entity_gid in data: continue
                            if not entity_name: continue
                            # Check if target is a substring of entity_name
                            if target.lower() in entity_name.lower() or entity_name.lower() == target.lower(): 
                                found = True
                        if not found:
                            return False
                    return True
            case ExprKind.same_place:
                data = [await c.client_object.global_id_full() for c in clients]
                target = len(data)
                for client in clients:
                    entities = await client.get_base_entity_list()
                    found = 0
                    for entity in entities:
                        idx = 0
                        while idx < len(data):
                            entity_gid = await entity.global_id_full()
                            if data[idx]==entity_gid:
                                found += 1
                            idx+=1
                    if found != target:
                        return False
                return True

            case ExprKind.in_zone:
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    for client in self._clients:
                        zone = await client.zone_name()
                        expected = await self._extract_data_info(expression.command.data[1])
                        if expected == zone:
                            self._any_player_client.append(client)
                            found_any = True
                    return found_any
                else:
                    for client in clients:
                        zone = await client.zone_name()
                        expected = await self._extract_data_info(expression.command.data[1])
                        if expected != zone:
                            return False
                    return True
            case ExprKind.same_zone:
                if len(clients) == 0:
                    return True
                expected_zone = await clients[0].zone_name()
                for client in clients[1:]:
                    if await client.zone_name() != expected_zone:
                        return False
                return True
            case ExprKind.same_quest:
                if len(clients) == 0:
                    return True
                expected_quest_text = await self._fetch_tracked_quest_text(clients[0])
                for client in clients[1:]:
                    quest_text = await self._fetch_tracked_quest_text(client)
                    if expected_quest_text != quest_text:
                        return False
                return True
            case ExprKind.same_yaw:
                if len(clients) == 0:
                    return True
                expected_yaw = await clients[0].body.yaw()
                rounded_expected_yaw = round(expected_yaw, 1)
                for client in clients[1:]:
                    yaw = await client.body.yaw()
                    rounded_client_yaw = round(yaw, 1)
                    if rounded_expected_yaw != rounded_client_yaw:
                        return False
                return True
            case ExprKind.same_xyz:
                if len(clients) == 0:
                    return True
                expected_pos = await clients[0].body.position()
                for client in clients[1:]:
                    pos = await client.body.position()
                    distance = calc_Distance(expected_pos, pos)
                    if distance > 5.0: 
                        return False
                return True
            case ExprKind.playercount:
                expected_count = await self._extract_data_info(expression.command.data[1])

                if isinstance(expected_count, float):
                    expected_count = int(expected_count)
                elif isinstance(expected_count, str):
                    try:
                        expected_count = int(expected_count)
                    except ValueError:
                        raise ValueError(f"Invalid number '{expected_count}'")
                return expected_count == len(self._clients)
            case ExprKind.tracking_quest:
                expected_text = await self._extract_data_info(expression.command.data[1])
                assert type(expected_text) == str
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    for client in self._clients:
                        name = await self._fetch_tracked_quest_text(client)
                        if name == expected_text:
                            self._any_player_client.append(client)
                            found_any = True
                    return found_any
                else:
                    for client in clients:
                        name = await self._fetch_tracked_quest_text(client)
                        if name != expected_text:
                            return False
                    return True
            case ExprKind.tracking_goal:
                expected_text = await self._extract_data_info(expression.command.data[1])
                assert type(expected_text) == str
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    for client in self._clients:
                        text = await self._fetch_tracked_goal_text(client)
                        if text == expected_text:
                            self._any_player_client.append(client)
                            found_any = True
                    return found_any
                else:
                    for client in clients:
                        text = await self._fetch_tracked_goal_text(client)
                        if text != expected_text:
                            return False
                    return True
            case ExprKind.loading:
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    for client in self._clients:
                        if await client.is_loading():
                            self._any_player_client.append(client)
                            found_any = True
                    return found_any
                else:
                    for client in clients:
                        if not await client.is_loading():
                            return False
                    return True
            case ExprKind.in_combat:
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    for client in self._clients:
                        if await client.in_battle():
                            self._any_player_client.append(client)
                            found_any = True
                    return found_any
                else:
                    for client in clients:
                        if not await client.in_battle():
                            return False
                    return True
            case ExprKind.has_quest:
                expected_text = await self._extract_data_info(expression.command.data[1])
                assert type(expected_text) == str
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    for client in self._clients:
                        for _, quest in await self._fetch_quests(client):
                            if await self._fetch_quest_text(client, quest) == expected_text:
                                self._any_player_client.append(client)
                                found_any = True
                                break
                    return found_any
                else:
                    for client in clients:
                        found = False
                        for _, quest in await self._fetch_quests(client):
                            if await self._fetch_quest_text(client, quest) == expected_text:
                                found = True
                                break
                        if not found:
                            return False
                    return True
            case ExprKind.has_dialogue:
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    for client in self._clients:
                        if await client.is_in_dialog():
                            self._any_player_client.append(client)
                            found_any = True
                    return found_any
                else:
                    for client in clients:
                        if not await client.is_in_dialog():
                            return False
                    return True
            case ExprKind.has_xyz:
                target_pos: XYZ = await self._extract_data_info(expression.command.data[1]) # type: ignore

                if not isinstance(target_pos, XYZ):
                    raise ValueError(f"Invalid XYZ value '{target_pos}'")
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    for client in self._clients:
                        client_pos = await client.body.position()
                        if abs(target_pos - client_pos) <= 1:
                            self._any_player_client.append(client)
                            found_any = True
                    return found_any
                else:
                    for client in clients:
                        client_pos = await client.body.position()
                        if abs(target_pos - client_pos) > 1:
                            return False
                    return True
            case ExprKind.has_yaw:
                target_yaw: float = await self._extract_data_info(expression.command.data[1]) # type: ignore

                if not isinstance(target_yaw, float):
                    raise ValueError(f"Invalid yaw value '{target_yaw}'")
                if selector.any_player:
                    self._any_player_client = []
                    found_any = False
                    for client in self._clients:
                        client_yaw = await client.body.yaw()
                        # Round both values to the nearest tenth for comparison
                        rounded_client_yaw = round(client_yaw, 1)
                        rounded_target_yaw = round(target_yaw, 1)
                        if rounded_client_yaw == rounded_target_yaw:
                            self._any_player_client.append(client)
                            found_any = True
                    return found_any
                else:
                    for client in clients:
                        client_yaw = await client.body.yaw()
                        # Round both values to the nearest tenth for comparison
                        rounded_client_yaw = round(client_yaw, 1)
                        rounded_target_yaw = round(target_yaw, 1)
                        if rounded_client_yaw != rounded_target_yaw:
                            return False
                    return True
            case _:
                raise VMError(f"Unimplemented expression: {expression}")

    async def eval(self, expression: Expression, client: Client | None = None):
        match expression:
            case IdentExpression():
                return expression.ident
            case ConstantReferenceExpression():
                if expression.name in self._constants:
                    return self._constants[expression.name]
                raise VMError(f"Unknown constant: ${expression.name}")
            case ConstantCheckExpression():
                constant_name = expression.name

                if expression.value is None:
                    if constant_name in self._constants:
                        return self._constants[constant_name]
                    raise VMError(f"Unknown constant: {constant_name}")

                expected_value = await self.eval(expression.value)

                if constant_name in self._constants:
                    actual_value = self._constants[constant_name]
                    if isinstance(expected_value, bool) and isinstance(actual_value, str):
                        if actual_value.lower() == "true":
                            actual_value = True
                        elif actual_value.lower() == "false":
                            actual_value = False
                    
                    return actual_value == expected_value
                return False
            case RangeMinExpression():
                range_value = await self.eval(expression.range_expr, client)
                if isinstance(range_value, str):
                    try:
                        min_val, _ = map(float, range_value.split('-'))
                        return min_val
                    except ValueError:
                        raise VMError(f"Invalid range format: {range_value}. Expected format like '1-100'")
                else:
                    raise VMError(f"Range expression must evaluate to a string, got {range_value}")
                    
            case RangeMaxExpression():
                range_value = await self.eval(expression.range_expr, client)
                if isinstance(range_value, str):
                    try:
                        _, max_val = map(float, range_value.split('-'))
                        return max_val
                    except ValueError:
                        raise VMError(f"Invalid range format: {range_value}. Expected format like '1-100'")
                else:
                    raise VMError(f"Range expression must evaluate to a string, got {range_value}")
            case IndexAccessExpression():
                container = await self.eval(expression.expr, client)
                index = await self.eval(expression.index, client)
                
                if isinstance(container, list) and isinstance(index, (int, float)):
                    index_int = int(index)
                    if 0 <= index_int < len(container):
                        return container[index_int]
                    else:
                        # Return 0 for out of bounds index
                        return 0.0
                else:
                    # If not a list or index is not a number, return 0
                    return 0.0
            case AndExpression():
                for expr in expression.expressions:
                    if not await self.eval(expr, client):
                        return False
                return True
            case OrExpression():
                for expr in expression.expressions:
                    if await self.eval(expr, client):
                        return True
                return False
            case CommandExpression():
                return await self._eval_command_expression(expression)
            case NumberExpression():
                return expression.number
            case XYZExpression():
                return XYZ(
                    await self.eval(expression.x, client), # type: ignore
                    await self.eval(expression.y, client), # type: ignore
                    await self.eval(expression.z, client), # type: ignore
                )
            case UnaryExpression():
                match expression.operator.kind:
                    case TokenKind.minus:
                        result = await self.eval(expression.expr, client)
                        return -result # type: ignore
                    case TokenKind.keyword_not:
                        # First evaluate the expression to populate _any_player_client
                        expr_result = await self.eval(expression.expr, client)
                        
                        if (isinstance(expression.expr, CommandExpression) and 
                            expression.expr.command.player_selector.any_player):
                            # Invert the selection - clients that didn't match become the new matches
                            current_matches = self._any_player_client.copy()
                            self._any_player_client = [c for c in self._clients if c not in current_matches]
                        
                        # Return negated result
                        return not expr_result
                    case _:
                        raise VMError(f"Unimplemented unary expression: {expression}")
            case StringExpression():
                return expression.string
            case StrFormatExpression():
                format_str = expression.format_str
                values = []
                for eval in expression.values:
                    result = await self.eval(eval, client)
                    values.append(result)
                return format_str % tuple(values)
            case KeyExpression():
                key = expression.key
                if key not in Keycode.__members__:
                    raise VMError(f"Unknown key code: {key}")
                return Keycode[expression.key]
            case EquivalentExpression():
                left = await self.eval(expression.lhs, client)
                right = await self.eval(expression.rhs, client)

                if isinstance(left, list) and len(left) > 0:
                    left = left[0]
                if isinstance(right, list) and len(right) > 0:
                    right = right[0]
                    
                return left == right
            case DivideExpression():
                left = await self.eval(expression.lhs, client)
                right = await self.eval(expression.rhs, client)
                return (left / right) # type: ignore
            case GreaterExpression():
                left = await self.eval(expression.lhs, client)
                right = await self.eval(expression.rhs, client)
                if isinstance(left, list) and len(left) > 0:
                    left = left[0] 
                if isinstance(right, list) and len(right) > 0:
                    right = right[0] 
                return (left > right)
            case Eval():
                return await self._eval_expression(expression, client) #type: ignore
            case SelectorGroup():
                players = self._select_players(expression.players)
                expr = expression.expr
                if expression.players.any_player:
                    self._any_player_client = []
                    found_any = False
                    for anyplayer in self._clients:
                        result = await self.eval(expr, anyplayer)
                        if result:
                            self._any_player_client.append(anyplayer)
                            found_any = True
                    
                    return found_any
                else:
                    for player in players:
                        if not await self.eval(expr, player):
                            return False
                    return True
            case ReadVarExpr():
                loc = await self.eval(expression.loc)
                assert(loc != None and type(loc) == int)
                test = self.current_task.stack[loc]
                return test
            case StackLocExpression():
                return expression.offset
            case SubExpression():
                lhs = await self.eval(expression.lhs, client)
                rhs = await self.eval(expression.rhs, client)
                assert(isinstance(lhs, (int, float)))
                assert(isinstance(rhs, (int, float)))
                return lhs - rhs
            
            case ListExpression():
                result = []
                
                if hasattr(expression, 'items') and isinstance(expression.items, list):
                    for item in expression.items:
                        evaluated_item = await self.eval(item, client)
                        if isinstance(evaluated_item, list):
                            result.extend(evaluated_item)
                        else:
                            result.append(evaluated_item)
                elif hasattr(expression, 'items') and isinstance(expression.items, ListExpression):
                    inner_result = await self.eval(expression.items, client)
                    result = inner_result if isinstance(inner_result, list) else [inner_result]
                elif hasattr(expression, 'expr') and isinstance(expression.expr, ListExpression):
                    inner_result = await self.eval(expression.expr, client)
                    result = inner_result if isinstance(inner_result, list) else [inner_result]
                elif hasattr(expression, 'expr'):
                    single_result = await self.eval(expression.expr, client)
                    result = [single_result]
                
                return result
            case ContainsStringExpression():
                lhs = await self.eval(expression.lhs, client)
                rhs = await self.eval(expression.rhs, client)
                
                if isinstance(rhs, list):
                    return any(item in lhs for item in rhs)
                
                # Original behavior for single string
                return (rhs in lhs) #type: ignore
            case _:
                raise VMError(f"Unimplemented expression type: {expression}")

    async def _eval_expression(self, eval: Eval, client: Client):
        kind = eval.kind
        match kind:
            case EvalKind.duel_round:
                if await client.in_battle():
                    return await client.duel.round_num()
            case EvalKind.account_level:
                return await client.stats.reference_level()
            case EvalKind.health:
                return await client.stats.current_hitpoints()
            case EvalKind.max_health:
                return await client.stats.max_hitpoints()
            case EvalKind.mana:
                return await client.stats.current_mana()
            case EvalKind.max_mana:
                return await client.stats.max_mana()
            case EvalKind.energy:
                return await client.current_energy()
            case EvalKind.max_energy:
                return await client.stats.energy_max()
            case EvalKind.bagcount:
                return (await client.backpack_space())[0]
            case EvalKind.max_bagcount:
                return (await client.backpack_space())[1]
            case EvalKind.gold:
                return await client.stats.current_gold()
            case EvalKind.max_gold:
                return await client.stats.base_gold_pouch()
            case EvalKind.windowtext:
                path = eval.args[0]
                assert(type(path) == list)
                try:
                    window = await get_window_from_path(client.root_window, path)
                    if window:
                        try:
                            text = await window.maybe_text()
                            if text:
                                return text.lower()
                        except (ValueError, MemoryReadError):
                            pass

                        # retry with the less reliable offset that is only defined for control elements
                        try:
                            text = await window.read_wide_string_from_offset(616)
                            return text.lower()
                        except (ValueError, MemoryReadError):
                            pass
                    return "" # If window path doesn't exist or any other error occurs, return empty string
                except Exception:
                    # If window path doesn't exist or any other error occurs, return empty string
                    return ""
            case EvalKind.windownum:
                path = eval.args[0]
                assert(type(path) == list)
                try:
                    window = await get_window_from_path(client.root_window, path)
                    if window:
                        try:
                            text = await window.maybe_text()
                            if text:
                                # If there's a slash, extract both parts as separate numbers
                                if '/' in text:
                                    parts = text.split('/')
                                    result = []
                                    for part in parts:
                                        numeric_text = ''.join(c for c in part if c.isdigit() or c == '.' or c == '-')
                                        if numeric_text:
                                            result.append(float(numeric_text))
                                        else:
                                            result.append(0.0)

                                    if len(result) > 0:
                                        # Return the list for indexed access
                                        return result
                                    return 0.0
                                else:
                                    # Extract numeric value from the whole text
                                    numeric_text = ''.join(c for c in text if c.isdigit() or c == '.' or c == '-')
                                    if numeric_text:
                                        # For single values, return as a single-item list for consistency
                                        return [float(numeric_text)]
                                    return [0.0]
                        except (ValueError, MemoryReadError):
                            pass

                        # retry with the less reliable offset that is only defined for control elements
                        try:
                            text = await window.read_wide_string_from_offset(616)
                            if '/' in text:
                                parts = text.split('/')
                                result = []
                                for part in parts:
                                    numeric_text = ''.join(c for c in part if c.isdigit() or c == '.' or c == '-')
                                    if numeric_text:
                                        result.append(float(numeric_text))
                                    else:
                                        result.append(0.0)
                                
                                if len(result) > 0:
                                    # Return the list for indexed access
                                    return result
                                return 0.0
                            else:
                                numeric_text = ''.join(c for c in text if c.isdigit() or c == '.' or c == '-')
                                if numeric_text:
                                    return [float(numeric_text)]
                                return [0.0]
                        except (ValueError, MemoryReadError):
                            pass
                except (ValueError, MemoryReadError):
                    pass
                return [0.0]
            case EvalKind.playercount:
                return len(self._clients)
            case EvalKind.potioncount:
                return await client.stats.potion_charge()
            case EvalKind.max_potioncount:
                return await client.stats.potion_max()
            case EvalKind.any_player_list:
                return [c.title for c in self._any_player_client] if self._any_player_client else [self._clients[0].title]

    async def exec_deimos_call(self, instruction: Instruction):
        assert instruction.kind == InstructionKind.deimos_call
        assert type(instruction.data) == list

        selector: PlayerSelector = instruction.data[0]
        if selector.any_player and self._any_player_client:
            clients = self._any_player_client
        elif selector.any_player:
            clients = [] 
            for client in self._clients:
                clients = [client]  # Use the first client found
                break
        else:
            clients = self._select_players(selector)
        
        # Skip execution if no valid clients were selected
        if not clients:
            return

        
        async def eval_arg(arg, client):
            if isinstance(arg, Expression):
                if isinstance(arg, IdentExpression):
                    constant_name = arg.ident
                    if constant_name in self._constants:
                        return self._constants[constant_name]
                    else:
                        #logger.error(f"Undefined constant referenced by IdentExpression: ${constant_name}")
                        return constant_name  
                return await self.eval(arg, client)
            elif isinstance(arg, str) and arg.startswith('$'):
                constant_name = arg[1:]  # Remove the $ prefix
                if constant_name in self._constants:
                    return self._constants[constant_name]
                else:
                    logger.error(f"Undefined constant: {arg}")
                    return arg 
            return arg

        # TODO: is eval always fast enough to run in order during a TaskGroup
        match instruction.data[1]:     
            case "set_zone":
                for client in clients:
                    zone_name = await client.zone_name()
                    self.logged_data['zone'][client.title] = zone_name
                    logger.debug(f"Client {client.title}: Current zone: {zone_name}")
            case "set_goal":
                for client in clients:
                    current_goal = await self._fetch_tracked_goal_text(client)
                    self.logged_data['goal'][client.title] = current_goal
                    logger.debug(f"Client {client.title}: Current goal: {current_goal}")
            case "set_quest":
                for client in clients:
                    current_quest = await self._fetch_tracked_quest_text(client)
                    self.logged_data['quest'][client.title] = current_quest
                    logger.debug(f"Client {client.title}: Current quest: {current_quest}")
            case "autopet":
                async def vm_play_dance_game(client: Client):
                    try:
                        logger.debug(f"Client {client.title}: Starting pet dance game.")
                        logger.debug(f"Client {client.title}: Activating dance game hook")
                        await attempt_activate_dance_hook(client)

                        await dancedance(client)
                        
                        logger.debug(f"Client {client.title}: Finished pet dance game.")
                        return True
                    except Exception as e:
                        logger.error(f"Error in pet play dance game for {client.title}: {e}")
                        return False
                
                # Create tasks for each client
                tasks = []
                for client in clients:
                    async def timeout_dance_game(client):
                        try:
                            await asyncio.wait_for(vm_play_dance_game(client), timeout=60)
                        except asyncio.TimeoutError:
                            logger.error(f"Client {client.title}: Pet dance game timed out.")
                        return False
                    task = asyncio.create_task(timeout_dance_game(client))
                    tasks.append(task)

                if tasks:
                    await asyncio.gather(*tasks)
                    
                logger.debug("All clients have finished pet dance game")
            case "teleport":
                args = instruction.data[2]
                assert type(args) == list
                assert type(args[0]) == TeleportKind
                async with asyncio.TaskGroup() as tg:
                    match args[0]:
                        case TeleportKind.position:
                            for client in clients:
                                pos = await eval_arg(args[1], client)
                                tg.create_task(client.teleport(pos))
                        case TeleportKind.plusteleport:
                            for client in clients:
                                pluspos = await eval_arg(args[1], client)
                                clientpos = await client.body.position()
                                newpos = XYZ(clientpos.x + pluspos.x, clientpos.y + pluspos.y, clientpos.z + pluspos.z)
                                tg.create_task(client.teleport(newpos))
                        case TeleportKind.minusteleport:
                            for client in clients:
                                minuspos = await eval_arg(args[1], client)
                                clientpos = await client.body.position()
                                newpos = XYZ(clientpos.x - minuspos.x, clientpos.y - minuspos.y, clientpos.z - minuspos.z)
                                tg.create_task(client.teleport(newpos))
                        case TeleportKind.entity_literal:
                            use_navmap = False
                            if len(args) > 2 and args[-2] == TeleportKind.nav:
                                use_navmap = True
                                name = await eval_arg(args[-1], clients[0])
                            else:
                                name = await eval_arg(args[-1], clients[0])
                            
                            for client in clients:
                                async def tp_to_entity(client):
                                    entity = await client.find_closest_by_name(name)
                                    if entity:
                                        pos = await entity.location()
                                        if use_navmap:
                                            await navmap_tp(client, pos)
                                        else:
                                            await client.teleport(pos)
                                tg.create_task(tp_to_entity(client))
                        case TeleportKind.entity_vague:
                            use_navmap = False
                            if len(args) > 2 and args[-2] == TeleportKind.nav:
                                use_navmap = True
                                vague = await eval_arg(args[-1], clients[0])
                            else:
                                vague = await eval_arg(args[-1], clients[0])
                            
                            for client in clients:
                                async def tp_to_vague_entity(client):
                                    entity = await client.find_closest_by_vague_name(vague)
                                    if entity:
                                        pos = await entity.location()
                                        if use_navmap:
                                            await navmap_tp(client, pos)
                                        else:
                                            await client.teleport(pos)
                                tg.create_task(tp_to_vague_entity(client))
                        case TeleportKind.mob:
                            for client in clients:
                                tg.create_task(client.tp_to_closest_mob())
                        case TeleportKind.quest:
                            # TODO: "quest" could instead be treated as an XYZ expression or something
                            for client in clients:
                                pos = await client.quest_position.position()
                                tg.create_task(navmap_tp(client, pos))
                        case TeleportKind.friend_icon:
                            async def proxy(client: SprintyClient): # type: ignore
                                # probably doesn't need mouseless
                                async with client.mouse_handler:
                                    await teleport_to_friend_from_list(client, icon_list=2, icon_index=0)
                            for client in clients:
                                tg.create_task(proxy(client))
                        case TeleportKind.friend_name:
                            name = await eval_arg(args[-1], clients[0])
                            if isinstance(name, str) and name.startswith('$'):
                                constant_name = name[1:]
                                if constant_name in self._constants:
                                    name = self._constants[constant_name]
                            
                            async def proxy(client: SprintyClient): # type: ignore
                                async with client.mouse_handler:
                                    await teleport_to_friend_from_list(client, name=name)
                            for client in clients:
                                tg.create_task(proxy(client))
                        case TeleportKind.client_num:
                            num = await eval_arg(args[-1], clients[0])
                            target_client = self.player_by_num(num)
                            target_pos = await target_client.body.position()
                            for client in clients:
                                tg.create_task(client.teleport(target_pos))
                        case _:
                            raise VMError(f"Unimplemented teleport kind: {instruction}")
            case "goto":
                args = instruction.data[2]
                assert type(args) == list
                async with asyncio.TaskGroup() as tg:
                    for client in clients:
                        pos = await eval_arg(args[0], client)
                        tg.create_task(client.goto(pos.x, pos.y))
            case "waitfor":
                args = instruction.data[2]
                completion: bool = args[-1]
                assert type(completion) == bool

                async def waitfor_coro(coro, invert: bool, interval=0.25):
                    while not (invert ^ await coro()):
                        await asyncio.sleep(interval)

                async def waitfor_impl(coro, interval=0.25):
                    nonlocal completion
                    await waitfor_coro(coro, completion, interval)

                method_map = {
                    WaitforKind.dialog: Client.is_in_dialog,
                    WaitforKind.battle: Client.in_battle,
                    WaitforKind.free: is_free,
                }
                if args[0] in method_map:
                    method = method_map[args[0]]
                    async with asyncio.TaskGroup() as tg:
                        for client in clients:
                            async def proxy(): # type: ignore
                                return await method(client)
                            tg.create_task(waitfor_impl(proxy))
                else:
                    match args[0]:
                        case WaitforKind.zonechange:
                            if completion:
                                async with asyncio.TaskGroup() as tg:
                                    for client in clients:
                                        tg.create_task(waitfor_coro(client.is_loading, True))
                            else:
                                async with asyncio.TaskGroup() as tg:
                                    for client in clients:
                                        starting_zone = await client.zone_name()
                                        async def proxy():
                                            return starting_zone != (await client.zone_name())
                                        tg.create_task(waitfor_coro(proxy, False))
                        case WaitforKind.window:
                            window_path = await eval_arg(args[1], clients[0] if clients else None)
                            async with asyncio.TaskGroup() as tg:
                                for client in clients:
                                    async def proxy():
                                        return await is_visible_by_path(client, window_path)
                                    tg.create_task(waitfor_impl(proxy))
                        case _:
                            raise VMError(f"Unimplemented waitfor kind: {instruction}")
            case "sendkey":
                args = instruction.data[2]
                async with asyncio.TaskGroup() as tg:
                    for client in clients:
                        key = await eval_arg(args[0], client)
                        time = 0.1 if args[1] is None else await eval_arg(args[1], client)
                        tg.create_task(client.send_key(key, time))
            case "usepotion":
                args = instruction.data[2]
                potion_tasks = []
                
                for client in clients:
                    if len(args) > 0:
                        health_num = await eval_arg(args[0], client)
                        mana_num = await eval_arg(args[1], client)
                        
                        async def _use_potion_if_needed(client, health_threshold, mana_threshold):
                            async with client.mouse_handler:
                                await client.use_potion_if_needed(int(health_threshold), int(mana_threshold))
                        
                        potion_tasks.append(_use_potion_if_needed(client, health_num, mana_num))
                    else:
                        async def _use_potion(client):
                            async with client.mouse_handler:
                                await client.use_potion()

                        potion_tasks.append(_use_potion(client))
                
                if potion_tasks:
                    await asyncio.gather(*potion_tasks)
            case "buypotions":
                args = instruction.data[2]
                ifneeded = await eval_arg(args[0], clients[0]) if clients else False
                async with asyncio.TaskGroup() as tg:
                    for client in clients:
                        if ifneeded:
                            tg.create_task(refill_potions_if_needed(client, mark=True, recall=True))
                        else:
                            tg.create_task(refill_potions(client, mark=True, recall=True))
            case "relog":
                async with asyncio.TaskGroup() as tg:
                    for client in clients:
                        tg.create_task(logout_and_in(client))
            case "cursor":
                args = instruction.data[2]
                async with asyncio.TaskGroup() as tg:
                    for client in clients:
                        match args[0]:
                            case CursorKind.position:
                                async def proxy(client: SprintyClient, x: float, y: float):
                                    async with client.mouse_handler:
                                            await client.mouse_handler.set_mouse_position(int(x), int(y))
                                x = await eval_arg(args[1], client)
                                y = await eval_arg(args[2], client)
                                tg.create_task(proxy(client, x, y))
                                await asyncio.sleep(.2)
                            case CursorKind.window:
                                path = await eval_arg(args[1], client)
                                async def proxy(client: SprintyClient, path: list):
                                    window = await get_window_from_path(client.root_window, path)
                                    if window:
                                        async with client.mouse_handler:
                                            await client.mouse_handler.set_mouse_position_to_window(window)
                                tg.create_task(proxy(client, path))
                                await asyncio.sleep(.2)
            case "click":
                args = instruction.data[2]
                async with asyncio.TaskGroup() as tg:
                    for client in clients:
                        match args[0]:
                            case ClickKind.position:
                                async def proxy(client: SprintyClient, x: float, y: float):
                                    async with client.mouse_handler:
                                        await client.mouse_handler.click(int(x), int(y))
                                x = await eval_arg(args[1], client)
                                y = await eval_arg(args[2], client)
                                tg.create_task(proxy(client, x, y))
                            case ClickKind.window:
                                path = await eval_arg(args[1], client)
                                async def proxy(client: SprintyClient, path: list):
                                    await click_window_by_path(client, path)
                                tg.create_task(proxy(client, path))
                            case _:
                                raise VMError(f"Unimplemented click kind: {instruction}")
            case "tozone":
                args = instruction.data[2]
                async with asyncio.TaskGroup() as tg:
                    for client in clients:
                        zone_path = await eval_arg(args[0], client)
                        tg.create_task(toZone([client], "/".join(zone_path) if isinstance(zone_path, list) else zone_path))
            case "select_friend":
                args = instruction.data[2]
                friend_name = await eval_arg(args[0], clients[0]) if clients else args[0]
                
                async with asyncio.TaskGroup() as tg:
                    for client in clients:
                        tg.create_task(self.select_friend_from_list(client, friend_name))
            case _:
                raise VMError(f"Unimplemented deimos call: {instruction}")

    async def exec_compound_deimos_call(self, command_entries):
        tasks = []
        
        for entry in command_entries:
            player_selector, command_name, command_data = entry

            instruction = Instruction(
                kind=InstructionKind.deimos_call,
                data=[player_selector, command_name, command_data]
            )

            tasks.append(self.exec_deimos_call(instruction))
        
        # Execute all commands in parallel
        await asyncio.gather(*tasks)

    async def _process_untils(self):
        for i in range(len(self._until_infos) - 1, -1, -1):
            info = self._until_infos[i]
            try:
                if await self.eval(info.expr):
                    self.current_task.ip = info.exit_point
                    return
            except VMError:
                # If evaluation fails (e.g., due to non-existent player), treat as true
                # This will cause the VM to skip the until block
                self.current_task.ip = info.exit_point
                return

    async def run_waitfor(self, coro):
        if not self.current_task.waitfor:
            self.current_task.waitfor = asyncio.create_task(coro)
        elif self.current_task.waitfor.done():
            self.current_task.waitfor = None
            self.current_task.ip += 1

    async def step(self):
        if not self.running:
            return
        await asyncio.sleep(0)
        self.current_task = self._scheduler.get_current_task()
        await self._process_untils() # must run before the next instruction is fetched
        if not self.current_task.running:
            self._scheduler.switch_task()
            return
        instruction = self.program[self.current_task.ip]

        match instruction.kind:
            case InstructionKind.restart_bot:
                self.reset()
                self.current_task.ip = 0
                logger.debug("Bot Restarted")
            case InstructionKind.declare_constant:
                name, expr = instruction.data
                value = await self.eval(expr)
                await self.define_constant(name, value)
                self.current_task.ip += 1
            case InstructionKind.set_timer:
                assert isinstance(instruction.data, str), "Timer name must be a string"
                timer_name = instruction.data
                self._timers[timer_name] = asyncio.get_event_loop().time()
                logger.debug(f"Timer '{timer_name}' started")
                self.current_task.ip += 1
            case InstructionKind.end_timer:
                assert isinstance(instruction.data, str), "Timer name must be a string"
                timer_name = instruction.data
                if timer_name in self._timers:
                    elapsed_seconds = asyncio.get_event_loop().time() - self._timers[timer_name]
                    hours, remainder = divmod(int(elapsed_seconds), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    
                    time_str = f"{hours:02}:{minutes:02}:{seconds:02}"
                    
                    logger.debug(f"Timer '{timer_name}' ended - Elapsed time: {time_str}")
                    del self._timers[timer_name]
                else:
                    logger.warning(f"Attempted to end timer '{timer_name}' that was never started")
                self.current_task.ip += 1
            case InstructionKind.kill:
                self._any_player_client = []
                self.kill()
                logger.debug("Bot Killed")
            case InstructionKind.sleep:
                assert instruction.data != None
                time = await self.eval(instruction.data)

                if isinstance(time, (int, str)):
                    time = float(time)
                
                await asyncio.sleep(time)
                self.current_task.ip += 1
            case InstructionKind.jump:
                assert type(instruction.data) == int
                self.current_task.ip += instruction.data
            case InstructionKind.jump_if:
                assert type(instruction.data) == list
                try:
                    condition_met = await self.eval(instruction.data[0])
                    if condition_met:
                        self.current_task.ip += instruction.data[1]
                    else:
                        self.current_task.ip += 1
                except VMError:
                    if instruction.data[1] > 1:  # This is likely a while loop
                        self.current_task.ip += instruction.data[1]  # Skip the entire scope
                    else:
                        self.current_task.ip += 1  # Just move to the next instruction

            case InstructionKind.jump_ifn:
                assert type(instruction.data) == list
                try:
                    condition_met = await self.eval(instruction.data[0])
                    if condition_met:
                        self.current_task.ip += 1
                    else:
                        self.current_task.ip += instruction.data[1]
                except VMError:
                    self.current_task.ip += 1  # Move to the next instruction (skip the loop body)
            case InstructionKind.call:
                assert(type(instruction.data) == int)
                self.current_task.stack.append(self.current_task.ip + 1)
                self.current_task.ip += instruction.data
            case InstructionKind.ret:
                self.current_task.ip = self.current_task.stack.pop()
            case InstructionKind.enter_until:
                assert type(instruction.data) == list
                self._until_infos.append(UntilInfo(
                    expr=instruction.data[0],
                    id=instruction.data[1],
                    exit_point=self.current_task.ip + instruction.data[2],
                    stack_size=len(self.current_task.stack)
                ))
                self.current_task.ip += 1
            case InstructionKind.exit_until:
                for i in range(len(self._until_infos) - 1, -1, -1):
                    info = self._until_infos[i]
                    if info.id == instruction.data:
                        self._until_infos = self._until_infos[:i]
                        self.current_task.stack = self.current_task.stack[:info.stack_size]
                        break
                self.current_task.ip += 1 

            case InstructionKind.setdeck:
                async def setdeck(client: SprintyClient, token: str):
                    logger.debug(f"Setting {client.title}'s deck...")
                    async with DeckBuilder(client) as deck_builder:
                        await deck_builder.set_deck_preset(deck)
                assert type(instruction.data) == list
                clients = self._select_players(instruction.data[0])
                token = instruction.data[1]
                assert type(token) == str
                coder = DeckEncoderDecoder(token=token)
                deck = coder.decode()
                async with TaskGroup() as tg:
                    for client in clients:
                        tg.create_task(setdeck(client, token))
                logger.debug("Successfully set decks.")
                self.current_task.ip += 1

            case InstructionKind.getdeck:
                async def getdeck(client:SprintyClient):
                    async with DeckBuilder(client) as deck_builder:
                        deck = await deck_builder.get_deck_preset()
                        coder = DeckEncoderDecoder(deck=deck)
                        token = coder.encode()
                        logger.debug(f"{client.title}: --> {token} <--");

                assert type(instruction.data) == list
                clients = self._select_players(instruction.data[0])
                logger.debug("Reading deck...")
                async with TaskGroup() as tg:
                    for client in clients:
                        tg.create_task(getdeck(client))
                self.current_task.ip += 1
 
            case InstructionKind.log_single:
                assert(isinstance(instruction.data, Expression))

                if isinstance(instruction.data, IdentExpression):
                    ident = instruction.data.ident
                    if ident in self._constants:
                        logger.debug(f"{ident} = {self._constants[ident]}")
                    else:
                        logger.debug(ident)
                else:
                    value = await self.eval(instruction.data)
                    logger.debug(value)
                
                self.current_task.ip += 1
            case InstructionKind.log_multi:
                assert type(instruction.data) == list
                clients = self._select_players(instruction.data[0])
                expr = instruction.data[1]
                for client in clients:
                    string = await self.eval(expr, client)
                    logger.debug(f"{client.title} - {string}")
                self.current_task.ip += 1

            case InstructionKind.label | InstructionKind.nop:
                self.current_task.ip += 1

            case InstructionKind.push_stack:
                self.current_task.stack.append(None)
                self.current_task.ip += 1

            case InstructionKind.write_stack:
                assert(instruction.data != None)
                offset, expr = instruction.data
                self.current_task.stack[offset] = await self.eval(expr)
                self.current_task.ip += 1

            case InstructionKind.pop_stack:
                self.current_task.stack.pop()
                self.current_task.ip += 1
            case InstructionKind.set_yaw:
                assert(type(instruction.data)==list)
                selector = instruction.data[0]
                yaw = instruction.data[1]
                
                if selector.any_player and self._any_player_client:
                    clients = self._any_player_client
                elif selector.any_player:
                    clients = []
                    for client in self._clients:
                        clients = [client] 
                        break
                else:
                    clients = self._select_players(selector)
                
                if clients:
                    async with TaskGroup() as tg:
                        for client in clients:
                            tg.create_task(client.body.write_yaw(yaw))
                self.current_task.ip += 1
            case InstructionKind.load_playstyle:
                logger.debug("Loading playstyle")
                delegated = delegate_combat_configs(instruction.data, len(self._clients)) # type: ignore
                logger.debug(delegated)
                for i, client in enumerate(self._clients):
                    client.combat_config = delegated.get(i, default_config)
                self.current_task.ip += 1

            case InstructionKind.deimos_call:
                player_selector, command_name, data = instruction.data
                deimos_call_instruction = Instruction(
                    kind=InstructionKind.deimos_call,
                    data=[player_selector, command_name, data]
                )
                await self.exec_deimos_call(deimos_call_instruction)
                self.current_task.ip += 1
            case InstructionKind.compound_deimos_call:
                # instruction.data contains a list of [player_selector, command_name, command_data] entries
                await self.exec_compound_deimos_call(instruction.data)
                self.current_task.ip += 1  
            case _:
                raise VMError(f"Unimplemented instruction: {instruction}")
        if self.current_task.ip >= len(self.program):
            self.current_task.running = False
        if not True in [t.running for t in self._scheduler.tasks] or not self.running:
            self.stop()
        else:
            self._scheduler.switch_task()
            await asyncio.sleep(0)

    async def run(self):
        self.running = True
        while self.running:
            await self.step()
