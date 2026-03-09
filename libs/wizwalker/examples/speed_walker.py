import asyncio
from sys import argv

from wizwalker import ClientHandler


class SpeedWalker(ClientHandler):
    def __init__(self, speed_multiplier: float):
        super().__init__()
        self.speed_multiplier = speed_multiplier

        self._zone_change_tasks = []

    async def speed_up(self, client=None):
        if client:
            await client.client_object.write_speed_multiplier(
                int(self.speed_multiplier * 100)
            )

        else:
            for client in self.clients:
                await client.client_object.write_speed_multiplier(
                    int(self.speed_multiplier * 100)
                )

    async def zone_change_task(self, client):
        while True:
            await client.wait_for_zone_change()
            await self.speed_up(client)

    async def run(self):
        self.get_new_clients()
        print("Preparing for speed... one moment")
        await self.activate_all_client_hooks()
        print("Ready for speed!")
        await self.speed_up()

        for client in self.clients:
            self._zone_change_tasks.append(
                asyncio.create_task(self.zone_change_task(client))
            )

        while True:
            await asyncio.sleep(1)


async def main(speed_multiplier: float):
    speed_walker = SpeedWalker(speed_multiplier)

    try:
        await speed_walker.run()
    finally:
        await speed_walker.close()


if __name__ == "__main__":
    multiplier = 2

    if len(argv) > 1:
        to_convert = argv[-1]
        try:
            multiplier = float(to_convert)
        except ValueError:
            print(f"{to_convert} is not a valid float")
            exit()

    asyncio.run(main(multiplier))
