# Playstyles

This folder contains optional combat playstyle profiles that can be imported from the Deimos Playstyles tab.

## Myth Level 12 Questing

`Myth Level 12 Questing.txt` is an early-game Myth profile for questing before Humongofrog and Orthrus. It uses a small, conservative priority list:

- Try Mythblade on round 1 when the first enemy is not already low health.
- Hit with Troll, Cyclops, then Blood Bat, using a Sun damage enchant if one is available.
- Keep hitting in later rounds rather than setting up complex minion or utility logic.
- Fall back to any available damage spell only after the named early Myth hits fail.

The profile does not modify your deck. For best results, keep the in-game deck small and do not pack extra pet, treasure, or off-school attacks unless you want the final `any<damage>` fallback to consider them.

Profile-scoped questing options are declared as comments at the top of the file:

- `scan_nearby_side_quests: true` checks a small radius for nearby, non-combat NPCs before quest movement, accepts available dialogue, and switches to a local accepted side quest when the game exposes a quest-helper goal in the current zone.
- `health_wisp_threshold: 0.80` looks for a nearby safe health wisp when the wizard is at or below 80% health.
- Side-quest scanning uses cooldowns and a visited-NPC cache so the bot does not repeatedly talk to the same NPC.
- The `Side Questing` hotkey can be enabled from the Hotkeys tab for the same scan/accept/prioritize behavior outside this profile.
- If an active side quest fails to progress or has no quest-helper marker for repeated loops, it is skipped for 30 minutes and the bot switches to the next local side quest or back to a main quest.
- The scanner can accept nearby optional quest dialogue, but the client API does not expose a reliable "this NPC offers a quest" flag before talking to the NPC.
