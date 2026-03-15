import asyncio
from copy import copy
from functools import cached_property
from pathlib import Path
from typing import List, Optional, Type

import wizwalker
from wizwalker import utils
from .client import Client


class ClientHandler:
    """
    Manages clients
    """

    def __init__(self, *, client_cls: Type[Client] = Client):
        self.client_cls = client_cls

        self._managed_handles = []
        self.clients: List[Client] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def __repr__(self):
        return f"<WizWalker {self.clients=}>"

    @cached_property
    def install_location(self) -> Path:
        """
        Wizard101 install location
        """
        return utils.get_wiz_install()

    @staticmethod
    def start_wiz_client():
        """
        Start a new client
        """
        utils.start_instance()

    def get_foreground_client(self) -> Optional[wizwalker.Client]:
        for client in self.clients:
            if client.is_foreground:
                return client

    def get_new_clients(self) -> List[Client]:
        """
        Get all new clients currently not managed

        Returns:
            List of new clients added
        """
        all_handles = utils.get_all_wizard_handles()

        new_clients = []
        for handle in all_handles:
            if handle not in self._managed_handles:
                self._managed_handles.append(handle)

                new_client = self.client_cls(handle)
                self.clients.append(new_client)
                new_clients.append(new_client)

        return new_clients

    def remove_dead_clients(self) -> List[Client]:
        """
        Remove and return clients that are no longer running

        Returns:
             List of the dead clients removed
        """
        # so we can remove from self.clients
        clients_proxy = copy(self.clients)

        dead_clients = []
        for client in clients_proxy:
            if not client.is_running():
                dead_clients.append(client)
                self.clients.remove(client)

        return dead_clients

    def get_ordered_clients(self) -> List[Client]:
        """
        Get client's ordered by their position on the screen

        Returns:
            List of the ordered clients
        """
        return utils.order_clients(self.clients)

    async def activate_all_client_hooks(self, wait_for_ready: bool = True):
        """
        Activate hooks for all clients
        """
        hook_tasks = []

        for client in self.clients:
            hook_tasks.append(
                asyncio.create_task(
                    client.activate_hooks(wait_for_ready=wait_for_ready)
                )
            )

        if wait_for_ready:
            for task in hook_tasks:
                await task

    async def activate_all_client_mouseless(self):
        """
        Activates mouseless hook for all clients
        """
        for client in self.clients:
            await client.mouse_handler.activate_mouseless()

    async def close(self):
        """
        Closes all clients
        """
        for client in self.clients:
            await client.close()
