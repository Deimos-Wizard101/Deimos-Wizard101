import asyncio

from wizwalker import ClientHandler
from wizwalker.combat import CombatHandler


HITNAME = "thunder snake"


class LostSoulDestroyer(CombatHandler):
    async def handle_round(self):
        try:
            hit = await self.get_card_named(HITNAME)
        except ValueError:
            print(f"No cards named {HITNAME} in hand.")
        else:
            monsters = await self.get_all_monster_members()
            lost_soul = monsters[0]

            print(f"Casting {HITNAME} on lost soul")
            await hit.cast(lost_soul)


async def main():
    handler = ClientHandler()
    client = handler.get_new_clients()[0]

    try:
        print("Preparing")
        await client.activate_hooks()
        print("Ready for battle")

        async with client.mouse_handler:
          await LostSoulDestroyer(client).wait_for_combat()
    finally:
        print("Closing")
        await handler.close()


if __name__ == "__main__":
    asyncio.run(main())
