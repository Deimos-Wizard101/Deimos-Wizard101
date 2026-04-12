**Do not contact anyone besides CowHunter privately about this repo.**

WizSprinter is a semi-official extension to the `WizWalker library <https://github.com/StarrFox/wizwalker>`_.

It adds:

WizSprinter (WizWalker extension):
    - upgrade_clients
    - extended get_new_clients
    - extended remove_dead_clients
    - extended get_ordered_clients

SprintyClient (Client extension):
    - better teleport
    - get_base_entities_with_vague_name
    - get_base_entities_with_behaviors
    - get_health_wisps
    - get_mana_wisps
    - get_mobs
    - find_safe_entities_from
    - find_closest_of_entities
    - find_closest_by_predicate
    - find_closest_by_name
    - find_closest_by_vague_name
    - find_closest_health_wisp
    - find_closest_mana_wisp
    - find_closest_mob
    - tp_to_closest_of
    - tp_to_closest_by_name
    - tp_to_closest_by_vague_name
    - tp_to_closest_health_wisp
    - tp_to_closest_mana_wisp
    - tp_to_closest_mob
    - calc_health_ratio
    - calc_mana_ratio
    - has_potion
    - use_potion
    - needs_potion
    - use_potion_if_needed

SprintyCombat (Implementation of a CombatHandler):
    - CombatConfigProvider to parse a config file
    - Full CombatHandler with some logic
