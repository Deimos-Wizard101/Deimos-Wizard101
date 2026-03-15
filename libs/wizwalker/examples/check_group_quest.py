import asyncio

from wizwalker import ClientHandler


async def check_group_quest(client):
    ssm = client.social_systems_manager

    has_group_quest = await ssm.has_group_quest()

    if has_group_quest:
        quest_gid = await ssm.group_quest_gid()
        goal_gid = await ssm.group_goal_gid()
        print("You are a FOLLOWER (group quest is active)")
        print(f"  Quest GID: {quest_gid}")
        print(f"  Goal GID:  {goal_gid}")
    else:
        print("No group quest active — you are the LEADER or not in a party quest")


async def main():
    handler = ClientHandler()
    client = handler.get_new_clients()[0]

    try:
        print("Preparing")
        await client.activate_hooks()

        await check_group_quest(client)
    finally:
        print("Closing")
        await handler.close()


if __name__ == "__main__":
    asyncio.run(main())
