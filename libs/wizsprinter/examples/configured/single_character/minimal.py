"""
Very simple example for using WizSprinter's combat system.
It will handle battles for you using config.txt
"""

import asyncio
import os
import sys

from wizwalker.extensions.wizsprinter import WizSprinter, SprintyCombat, CombatConfigProvider


os.chdir(os.path.dirname(sys.argv[0]))


async def main():
    async with WizSprinter() as handler:
        client = handler.get_new_clients()[0]

        print("Preparing")
        await client.activate_hooks()
        print("It's sprintin' time")

        while True:
            combat = SprintyCombat(client, CombatConfigProvider("./config.txt"))
            await combat.wait_for_combat()


if __name__ == "__main__":
    asyncio.run(main())