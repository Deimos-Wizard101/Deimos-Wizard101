"""Chat and buddy test CLI.

Run on 2 game clients. Use option 1 to get each client's GID,
then use option 2 to send a whisper or option 3 to send a buddy request.

Requires ChatSendHook which hooks the game's main loop to execute
social actions on the main thread safely.

Controls:
  1      - Print your character's GID
  2      - Send a directed chat message to a target GID
  3      - Send buddy request to a GID
  Ctrl+C - Unhook cleanly and exit
"""

import asyncio

from wizwalker import ClientHandler


async def main():
    handler = ClientHandler()
    clients = handler.get_new_clients()
    if not clients:
        print("No game clients found. Launch Wizard101 first.")
        return

    client = clients[0]
    print(f"Attached to client (PID: {client._pymem.process_id})")

    try:
        print("Activating hooks...")
        await client.activate_hooks()

        print("Activating chat send hook...")
        await client.hook_handler.activate_chat_send_hook()

        print("Activating chat receive hook...")
        await client.hook_handler.activate_chat_hook(wait_for_ready=False)

        print("\n=== Chat & Buddy Test CLI ===")
        print("  1      - Get your GID")
        print("  2      - Send directed chat to a GID")
        print("  3      - Send buddy request to a GID")
        print("  4      - Wait for incoming whisper")
        print("  5      - Read last received whisper")
        print("  Ctrl+C - Exit\n")

        while True:
            choice = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("> ").strip()
            )

            if choice == "1":
                gid = await client.game_client.player_gid()
                print(f"  Your GID: {gid}")

            elif choice == "2":
                target_str = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("  Target GID: ").strip()
                )
                try:
                    target_gid = int(target_str)
                except ValueError:
                    print("  Invalid GID")
                    continue

                msg = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("  Message: ").strip()
                )
                if not msg:
                    print("  Empty message")
                    continue

                print(f"  Sending to {target_gid}: {msg!r}")
                try:
                    await client.chat_owner.send_msg(msg, target_gid=target_gid)
                    print("  Sent!")
                except Exception as e:
                    print(f"  Send failed: {e}")

            elif choice == "3":
                target_str = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("  Target GID: ").strip()
                )
                try:
                    target_gid = int(target_str)
                except ValueError:
                    print("  Invalid GID")
                    continue

                print(f"  Sending buddy request to {target_gid}...")
                try:
                    await client.chat_owner.add_player(target_gid)
                    print("  Sent!")
                except Exception as e:
                    print(f"  Failed: {e}")

            elif choice == "4":
                print("  Waiting for incoming whisper (10s timeout)...")
                try:
                    sender, msg, cnt = await client.chat_owner.wait_for_message(10.0)
                    print(f"  From {sender}: {msg!r} (msg #{cnt})")
                except asyncio.TimeoutError:
                    print("  No message received within timeout")
                except Exception as e:
                    print(f"  Error: {e}")

            elif choice == "5":
                try:
                    sender, msg, cnt = await client.chat_owner.recv_message()
                    print(f"  From {sender}: {msg!r} (msg #{cnt})")
                except Exception as e:
                    print(f"  Error: {e}")

            else:
                print("  Unknown option. Use 1-5 or Ctrl+C.")

    except KeyboardInterrupt:
        print("\nCtrl+C received")
    finally:
        print("Unhooking...")
        try:
            await client.hook_handler.deactivate_chat_hook()
        except Exception:
            pass
        try:
            await client.hook_handler.deactivate_chat_send_hook()
        except Exception:
            pass
        await handler.close()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
