from typing import *

from wizwalker import ClientHandler, Client

from .sprinty_client import SprintyClient


def upgrade_clients(clients: List[Client]) -> List[SprintyClient]:
    for client in clients:
        client.__class__ = SprintyClient
    return clients


class WizSprinter(ClientHandler):
    def __repr__(self):
        return f"<WizSprinter {self.clients=}>"

    def get_new_clients(self) -> List[SprintyClient]:
        """Upgraded get_new_clients method that returns SprintyClients"""
        return upgrade_clients(super().get_new_clients())

    def remove_dead_clients(self) -> List[SprintyClient]:
        """
        Remove and return clients that are no longer running

        Returns:
            List of the dead clients removed
        """
        return upgrade_clients(super().remove_dead_clients())

    def get_ordered_clients(self) -> List[SprintyClient]:
        """
        Get clients ordered by their position on the screen

        Returns:
            List of the ordered clients
        """
        return upgrade_clients(super().get_ordered_clients())
