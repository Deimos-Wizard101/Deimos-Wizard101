# Conditional Expressions for Combat Config

Conditions let you gate combat priorities on runtime state. They are optional
and purely additive -- existing configs work unchanged.

## Syntax

```
?(target.attribute op value) spell @ target
```

A condition is placed before the spell/move in a priority. If it evaluates to
`false`, that priority is skipped and the next one in the `|` chain is tried.

Conditions are per-priority, not per-line. Each priority in a `|` chain can
have its own condition, or none at all.

## Targets

### Single targets

| Target      | Description                          |
|-------------|--------------------------------------|
| `self`      | Your own wizard                      |
| `boss`      | The boss enemy (if present)          |
| `enemy`     | First enemy (same as `enemy(0)`)     |
| `enemy(N)`  | Nth enemy (0-indexed)                |
| `ally`      | First ally (same as `ally(0)`)       |
| `ally(N)`   | Nth ally (0-indexed)                 |

### Group targets (require aggregation)

Group targets check a condition across multiple members. You must wrap them
in an aggregation function:

| Syntax                | Evaluates to true when...                         |
|-----------------------|---------------------------------------------------|
| `any(enemies)`        | **At least one** enemy satisfies the comparison   |
| `all(enemies)`        | **Every** enemy satisfies the comparison          |
| `avg(enemies)`        | The **mean** of the attribute satisfies it        |
| `any(allies)`         | **At least one** ally satisfies the comparison    |
| `all(allies)`         | **Every** ally satisfies the comparison           |
| `avg(allies)`         | The **mean** of the attribute satisfies it        |

Note: `allies` includes yourself (the client wizard).

## Attributes

### Member attributes

Any async no-argument method on `CombatMember` can be used as an attribute.

| Attribute       | Type  | Has `max_`? | Notes                         |
|-----------------|-------|-------------|-------------------------------|
| `health`        | int   | Yes         | Current hit points            |
| `max_health`    | int   | --          | Maximum hit points            |
| `mana`          | int   | Yes         | Current mana                  |
| `max_mana`      | int   | --          | Maximum mana                  |
| `normal_pips`   | int   | No          | White pips                    |
| `power_pips`    | int   | No          | Power pips                    |
| `shadow_pips`   | int   | No          | Shadow pips                   |
| `level`         | int   | No          | Creature level                |
| `is_boss`       | bool  | No          | 1 if boss, 0 otherwise        |
| `is_dead`       | bool  | No          | 1 if dead, 0 otherwise        |
| `is_stunned`    | bool  | No          | 1 if stunned, 0 otherwise     |
| `is_player`     | bool  | No          | 1 if player wizard             |
| `is_monster`    | bool  | No          | 1 if monster                   |
| `is_minion`     | bool  | No          | 1 if minion                    |

Booleans compare numerically: `True == 1`, `False == 0`.

### Hanging effect attributes

These count active hanging effects on a member by reading their participant's
effect list at runtime. No `max_` counterpart (don't use with `%`).

| Attribute             | Counts                                                |
|-----------------------|-------------------------------------------------------|
| `charms`              | All charm effects (blades, weaknesses, etc.)          |
| `beneficial_charms`   | Positive charms only (blades, damage boosts)          |
| `harmful_charms`      | Negative charms only (weaknesses, mantle)             |
| `wards`               | All ward effects (shields, traps, etc.)               |
| `beneficial_wards`    | Positive wards only (shields, absorbs)                |
| `harmful_wards`       | Negative wards only (traps)                           |
| `over_time`           | All over-time effects (DOTs and HOTs)                 |
| `beneficial_over_time`| Heals over time only                                  |
| `harmful_over_time`   | Damage over time only                                 |

Disposition matching follows the game's logic: an effect with disposition
`both` matches either `beneficial` or `harmful` queries.

## Operators

| Op   | Meaning                |
|------|------------------------|
| `<`  | Less than              |
| `<=` | Less than or equal     |
| `>`  | Greater than           |
| `>=` | Greater than or equal  |
| `==` | Equal                  |
| `!=` | Not equal              |

## Values

- **Hard number**: `2000`, `0`, `3.5`
- **Percentage**: `50%` -- computes `(current / max) * 100` using the
  corresponding `max_` attribute (e.g. `health` uses `max_health`).
  Only works for attributes that have a `max_` counterpart (see table above).

## Spell type: `req_met`

The `req_met` keyword can be added to any `any<...>` spell template to filter
cards by whether their built-in `ConditionalSpellEffect` requirements are
satisfied given the current combat state.

Many spells in Wizard101 have conditional branches -- they do extra damage if
the target has traps, heal more if you have blades, or unlock bonus effects
based on hanging effects, pips, health, school, etc. Without `req_met`, the
bot picks any matching card regardless of whether its conditions would trigger.
With `req_met`, only cards whose conditional requirements are actually met
will be selected.

```
any<damage&req_met> @ enemy
```

This finds a damage card whose `ConditionalSpellEffect` requirements are
satisfied for the target. If no card meets its own requirements, the priority
fails and falls through to the next `|` alternative.

`req_met` works with all other spell types and can be combined with conditions:

```
?(enemy.harmful_wards >= 3) any<damage&req_met> @ enemy
```

Cards that have no `ConditionalSpellEffect` always pass the `req_met` check.

## Examples

---

### Basic: heal when low

```
?(self.health < 50%) any<heal> @ self | any<damage> @ enemy
```

If your health is below 50%, try to heal yourself. If the condition fails
(health is fine) or no heal card is available, fall through to attacking.

---

### Hard number threshold

```
?(self.health < 2000) any<heal> @ self
```

Heal when health drops below 2000 absolute, regardless of your max HP.

---

### Prioritize the boss

```
?(boss.health > 0) any<damage> @ boss | any<damage> @ enemy
```

Hit the boss if one exists and is alive. If there's no boss in this fight
the condition safely returns false (no crash) and falls through.

---

### Heal a specific ally

```
?(ally(0).health < 30%) any<heal> @ ally(0)
```

Heal your first ally if they drop below 30% HP. If you're solo (no allies),
the condition fails silently and this priority is skipped.

---

### Blade up when healthy, heal when not

```
?(self.health > 70%) any<blade> @ self | any<heal> @ self | any<damage> @ enemy
```

If you're above 70% HP, buff yourself with a blade. Otherwise try to heal.
Last resort: just attack.

---

### Pip-gated finisher

```
?(self.power_pips >= 4) any<damage&aoe> @ aoe | any<damage> @ enemy
```

Only attempt the big AoE if you have at least 4 power pips. Otherwise
single-target.

---

### Shadow pip check

```
?(self.shadow_pips >= 1) Shadow Shrike @ self | any<blade> @ self
```

Cast Shadow Shrike if you have a shadow pip, otherwise blade up.

---

### Full support rotation

```
?(ally(0).health < 40%) any<heal> @ ally(0)
?(ally(1).health < 40%) any<heal> @ ally(1)
?(ally(2).health < 40%) any<heal> @ ally(2)
?(self.health < 40%) any<heal> @ self
any<blade> @ self | any<damage> @ enemy
```

Check each ally in order, then yourself, and heal whoever is low. If nobody
needs healing, blade or attack. Each line is a separate round priority --
only the first successful cast happens per round.

---

### Only AoE non-boss mob fights

```
?(all(enemies).is_boss == 0) any<damage&aoe> @ aoe | any<damage> @ enemy
```

Only use AoE if none of the enemies are bosses (i.e. a pure mob fight).
Otherwise single-target. Useful for street fights where you don't want to
waste a big AoE when there's a boss to focus down.

---

### AoE when enemies are mostly healthy

```
?(avg(enemies).health > 60%) any<damage&aoe> @ aoe | any<damage> @ enemy
```

AoE if the average enemy HP is above 60%. Once they're low enough that
single-target would finish them off, switch to single-target.

---

### Heal when any teammate is hurt

```
?(any(allies).health < 40%) any<heal> @ ally | any<damage> @ enemy
```

If any member of your team (including yourself) is below 40%, try to heal.
The `@ ally` target then picks which ally to actually cast on.

---

### Team-wide low HP emergency

```
?(all(allies).health < 30%) any<heal&aoe> @ aoe | ?(any(allies).health < 30%) any<heal> @ ally | any<damage> @ enemy
```

If everyone is below 30%, use an AoE heal. If only some are low, single heal.
Otherwise attack.

---

### Finish off a weak enemy

```
?(enemy(0).health < 20%) any<damage> @ enemy(0) | any<damage&aoe> @ aoe | any<damage> @ enemy
```

If the first enemy is nearly dead, focus them down. Otherwise AoE or
attack normally.

---

### Multiple conditions in one line

```
?(self.health < 50%) any<heal> @ self | ?(boss.health > 0) any<damage> @ boss | any<damage> @ enemy
```

Each `|`-separated priority can have its own condition (or none). They are
evaluated left to right. The first priority whose condition passes *and*
whose spell successfully casts is used.

---

### Round-specific with conditions

```
{1} ?(self.shadow_pips >= 1) Shadow Shrike @ self | any<blade> @ self
?(self.health < 50%) any<heal> @ self | any<damage> @ enemy
```

Round 1: use Shadow Shrike if shadow pip is available, else blade.
All other rounds: heal if low, else attack.

---

### Enchanted spell with condition

```
?(self.power_pips >= 3) any<damage> [any<enchant>] @ boss | any<damage> @ enemy
```

If you have enough pips, cast an enchanted damage spell at the boss.
Otherwise just attack any enemy without enchanting.

---

### Conditional pass (stall for pips)

```
?(self.power_pips < 3) pass | any<damage&aoe> @ aoe
```

If you don't have enough pips yet, pass. Once you do, AoE.

---

### Nuke when traps are stacked

```
?(enemy.harmful_wards >= 3) any<damage> @ enemy | any<trap> @ enemy
```

If the enemy has 3 or more traps on them, hit. Otherwise keep stacking traps.

---

### Detonate when enemy has a DOT

```
?(enemy.harmful_over_time >= 1) Detonate @ enemy | any<damage> @ enemy
```

If the enemy has a DOT ticking, detonate it for burst damage. Otherwise
just attack normally.

---

### Blade stack then hit

```
?(self.beneficial_charms >= 3) any<damage> @ enemy | any<blade> @ self
```

Keep blading until you have 3+ blades stacked, then attack.

---

### Cleanse weakness before attacking

```
?(self.harmful_charms >= 1) any<charm> @ self | any<damage> @ enemy
```

If you have a weakness (harmful charm), cleanse it first. Otherwise attack.
(Assumes you have a cleanse charm card.)

---

### Shield up when no shields

```
?(self.beneficial_wards == 0) any<ward> @ self | any<damage> @ enemy
```

If you have no shields, put one up. Otherwise attack.

---

### Wait for traps before nuking (group)

```
?(all(enemies).harmful_wards >= 2) any<damage&aoe> @ aoe | any<trap> @ enemy
```

Only AoE if every enemy has at least 2 traps. Otherwise keep trapping.

---

### Only use conditional damage cards when requirements are met

```
any<damage&req_met> @ enemy | any<damage> @ enemy
```

Try to use a damage card whose built-in conditional effects (extra damage
if target has traps, etc.) would actually trigger. If none qualify, fall
back to any damage card.

---

### Conditional spell + hanging effect gate

```
?(enemy.harmful_wards >= 3) any<damage&req_met> @ enemy | any<trap> @ enemy
```

Only attempt a damage card that benefits from traps when the enemy actually
has 3+ traps. Double-gated: the condition checks the trap count, and
`req_met` ensures the card's own requirements are satisfied too.

---

### Full combo: trap, blade, nuke

```
?(self.beneficial_charms >= 2) ?(enemy.harmful_wards >= 2) any<damage&req_met> @ enemy | any<blade> @ self | any<trap> @ enemy | any<damage> @ enemy
```

Only go for the big hit when you have 2+ blades AND the enemy has 2+ traps
AND the card's requirements are met. Otherwise blade, trap, or just attack.
Note: two conditions on the same priority is not supported -- use separate
lines for multi-gate logic:

```
?(self.beneficial_charms >= 2) ?(enemy.harmful_wards >= 2) ...   <-- WRONG (only one condition per priority)

?(self.beneficial_charms < 2) any<blade> @ self                  <-- RIGHT
?(enemy.harmful_wards < 2) any<trap> @ enemy
any<damage&req_met> @ enemy | any<damage> @ enemy
```

The first two lines handle buffing. Once both fail (you have enough blades
and the enemy has enough traps), the third line fires.

---

## Error handling

All condition failures silently skip the priority (return false):

- **Member not found**: no boss in fight, not enough allies/enemies for the
  index, solo fight with `ally(0)`, etc.
- **Attribute missing**: typo in attribute name or method doesn't exist
- **No `max_` counterpart**: using `%` with an attribute that has no max
  (e.g. `normal_pips`)
- **Division by zero**: max value is 0
- **Hanging effect read failure**: participant not accessible, memory error
- **`req_met` evaluation failure**: card has no conditional effects (passes),
  or requirement evaluation throws (treated as not met, skips card)
- **Any other exception**: caught and treated as false

This means conditions are always safe -- they never crash the bot. A
condition that can't be evaluated just skips that priority.

## Backward compatibility

Conditions are fully optional. Every existing config parses and runs
identically -- the `condition?` in the grammar is optional, and
`MoveConfig.condition` defaults to `None`. No changes are needed to any
existing config files.

The `req_met` spell type is also optional. Existing `any<damage>` templates
work exactly as before. Only configs that explicitly include `req_met` will
trigger the card requirement check.
