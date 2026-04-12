"""
Very simple example for using WizSprinter's combat system.
It will handle battles for you automatically, which has inherent weaknesses but high convenience
"""

import asyncio

from wizwalker.extensions.wizsprinter import WizSprinter, SprintyCombat, CombatConfigGenerator


async def main():
    async with WizSprinter() as handler:
        client = handler.get_new_clients()[0]

        print("Preparing")
        await client.activate_hooks()
        print("It's sprintin' time")

        while True:
            combat = SprintyCombat(client, CombatConfigGenerator())
            await combat.wait_for_combat()


if __name__ == "__main__":
    asyncio.run(main())