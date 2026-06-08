from enum import Enum, IntFlag


class HangingDisposition(Enum):
    both = 0
    beneficial = 1
    harmful = 2


class DuelPhase(Enum):
    starting = 0
    pre_planning = 1
    planning = 2
    pre_execution = 3
    execution = 4
    resolution = 5
    victory = 6
    ended = 7
    max = 10


class SigilInitiativeSwitchMode(Enum):
    none = 0
    reroll = 1
    switch = 2


class DuelExecutionOrder(Enum):
    sequential = 0
    alternating = 1


class PipAquiredByEnum(Enum):
    unknown = 0
    normal = 1
    power = 2
    normal_to_power_conversion = 4
    impede_pips = 5


class DelayOrder(Enum):
    any_order = 0
    first = 1
    second = 2


class FusionState(Enum):
    fs_invalid = 0
    fs_partial = 1
    fs_valid = 2


class WindowStyle(IntFlag):
    has_back = 1
    scale_children = 2
    can_move = 4
    can_scroll = 16
    focus_locked = 64
    can_focus = 128
    can_dock = 32
    do_not_capture_mouse = 256
    is_transparent = 256
    effect_fadeid = 512
    effect_highlight = 1024
    has_no_border = 2048
    ignore_parent_scale = 4096
    use_alpha_bounds = 8192
    auto_grow = 16384
    auto_shrink = 32768
    auto_resize = 49152


class WindowFlags(IntFlag):
    visible = 1
    noclip = 2
    dock_outside = 131072
    dock_left = 128
    dock_top = 512
    dock_right = 256
    dock_bottom = 1024
    parent_size = 786432
    parent_width = 262144
    parent_height = 524288
    hcenter = 32768
    vcenter = 65536
    disabled = 2147483648


class SpellSourceType(Enum):
    caster = 0
    pet = 1
    shadow_creature = 2
    weapon = 3
    equipment = 4


class SpellEffects(Enum):
    invalid_spell_effect = 0
    damage = 1
    damage_no_crit = 2
    heal = 3
    heal_percent = 4
    set_heal_percent = 114
    steal_health = 5
    reduce_over_time = 6
    detonate_over_time = 7
    push_charm = 8
    steal_charm = 9
    push_ward = 10
    steal_ward = 11
    push_over_time = 12
    steal_over_time = 13
    remove_charm = 14
    remove_ward = 15
    remove_over_time = 16
    remove_aura = 17
    swap_all = 18
    swap_charm = 19
    swap_ward = 20
    swap_over_time = 21
    modify_incoming_damage = 23
    modify_incoming_damage_flat = 120
    maximum_incoming_damage = 24
    modify_incoming_heal = 25
    modify_incoming_heal_flat = 119
    modify_incoming_damage_type = 26
    modify_incoming_armor_piercing = 27
    modify_outgoing_damage = 28
    modify_outgoing_damage_flat = 122
    modify_outgoing_heal = 29
    modify_outgoing_heal_flat = 121
    modify_outgoing_damage_type = 30
    modify_outgoing_armor_piercing = 31
    modify_outgoing_steal_health = 32
    modify_incoming_steal_health = 33
    bounce_next = 34
    bounce_previous = 35
    bounce_back = 36
    bounce_all = 37
    absorb_damage = 38
    absorb_heal = 39
    modify_accuracy = 40
    dispel = 41
    confusion = 42
    cloaked_charm = 43
    cloaked_ward = 44
    stun_resist = 45
    clue = 112
    pip_conversion = 46
    crit_boost = 47
    crit_block = 48
    polymorph = 49
    delay_cast = 50
    modify_card_cloak = 51
    modify_card_damage = 52
    modify_card_accuracy = 54
    modify_card_mutation = 55
    modify_card_rank = 56
    modify_card_armor_piercing = 57
    summon_creature = 66
    teleport_player = 67
    stun = 68
    dampen = 69
    reshuffle = 70
    mind_control = 71
    modify_pips = 72
    modify_power_pips = 73
    modify_shadow_pips = 74
    modify_hate = 75
    damage_over_time = 76
    heal_over_time = 77
    modify_power_pip_chance = 78
    modify_rank = 79
    stun_block = 80
    reveal_cloak = 81
    instant_kill = 82
    afterlife = 83
    deferred_damage = 84
    damage_per_total_pip_power = 85
    modify_card_heal = 53
    modify_card_charm = 58
    modify_card_ward = 59
    modify_card_outgoing_damage = 60
    modify_card_outgoing_accuracy = 61
    modify_card_outgoing_heal = 62
    modify_card_outgoing_armor_piercing = 63
    modify_card_incoming_damage = 64
    modify_card_absorb_damage = 65
    cloaked_ward_no_remove = 87
    add_combat_trigger_list = 88
    remove_combat_trigger_list = 89
    backlash_damage = 90
    modify_backlash = 91
    intercept = 92
    shadow_self = 93
    shadow_creature = 94
    modify_shadow_creature_level = 95
    select_shadow_creature_attack_target = 96
    shadow_decrement_turn = 97
    crit_boost_school_specific = 98
    spawn_creature = 99
    un_polymorph = 100
    power_pip_conversion = 101
    protect_card_beneficial = 102
    protect_card_harmful = 103
    protect_beneficial = 104
    protect_harmful = 105
    divide_damage = 106
    collect_essence = 107
    kill_creature = 108
    dispel_block = 109
    confusion_block = 110
    modify_pip_round_rate = 111
    max_health_damage = 113
    untargetable = 115
    make_targetable = 116
    force_targetable = 117
    remove_stun_block = 118
    exit_combat = 123
    suspend_pips = 124
    resume_pips = 125
    auto_pass = 126
    stop_auto_pass = 127
    vanish = 128
    stop_vanish = 129
    max_health_heal = 130
    heal_by_ward = 131
    taunt = 132
    pacify = 133
    remove_target_restriction = 134
    convert_hanging_effect = 135
    add_spell_to_deck = 136
    add_spell_to_hand = 137
    modify_incoming_damage_over_time = 138
    modify_incoming_heal_over_time = 139
    modify_card_damage_by_rank = 140
    push_converted_charm = 141
    steal_converted_charm = 142
    push_converted_ward = 143
    steal_converted_ward = 144
    push_converted_over_time = 145
    steal_converted_over_time = 146
    remove_converted_charm = 147
    remove_converted_ward = 148
    remove_converted_over_time = 149
    modify_over_time_duration = 150
    modify_school_pips = 151
    shadow_pact = 152
    minion_rank_damage = 22


class EffectTarget(Enum):
    invalid_target = 0
    spell = 1
    specific_spells = 2
    target_global = 3
    enemy_team = 4
    enemy_team_all_at_once = 5
    friendly_team = 6
    friendly_team_all_at_once = 7
    enemy_single = 8
    friendly_single = 9
    minion = 10
    friendly_minion = 17
    self = 11
    at_least_one_enemy = 13
    preselected_enemy_single = 12
    multi_target_enemy = 14
    multi_target_friendly = 15
    friendly_single_not_me = 16

class EffectKinds(Enum):
    charm = 2
    curse = 3
    dot = 4
    hot = 5
    jinx = 1
    ward = 0

class ObjectType(Enum):
    undefined = 0
    player = 1
    npc = 2
    prop = 3
    object = 4
    house = 5
    key = 6
    old_key = 7
    deed = 8
    mail = 9
    recipe = 17
    equip_head = 10
    equip_chest = 11
    equip_legs = 12
    equip_hands = 13
    equip_finger = 14
    equip_feet = 15
    equip_ear = 16
    building_block = 18
    building_block_solid = 19
    golf = 20
    door = 21
    pet = 22
    fabric = 23
    window = 24
    roof = 25
    horse = 26
    structure = 27
    housing_texture = 28
    plant = 29


# TODO: are these ids static?
class MagicSchool(Enum):
    ice = 72777
    sun = 78483
    life = 2330892
    fire = 2343174
    star = 2625203
    myth = 2448141
    moon = 2504141
    death = 78318724
    storm = 83375795
    gardening = 663550619
    castle_magic = 806477568
    whirly_burly = 931528087
    balance = 1027491821
    shadow = 1429009101
    fishing = 1488274711
    cantrips = 1760873841


class FogMode(Enum):
  fog = 1
  filter = 2


class AccountPermissions(IntFlag):
    no_permissions = 0b0
    can_chat = 0b1
    can_filtered_chat = 0b10
    can_open_chat = 0b100
    can_open_chat_legacy = 0b1000
    can_true_friend_code = 0b10000
    can_gift = 0b100000
    can_report_bugs = 0b1000000
    unknown = 0b10000000
    unknown1 = 0b100000000
    unknown2 = 0b1000000000
    can_earn_crowns_offers = 0b10000000000
    can_earn_crowns_button = 0b100000000000
    unknown3 = 0b1000000000000
    unknown4 = 0b10000000000000
    # 5 and 6 are probably not used
    unknown5 = 0b100000000000000
    unknown6 = 0b1000000000000000


class HangingEffectType(Enum):
    any = 0
    ward = 1
    charm = 2
    over_time = 3
    specific = 4


class OutputEffectSelector(Enum):
    all = 0
    matched_select_rank = 1


class CountBasedType(Enum):
    spell_kills = 0
    spell_crits = 1


class Operator(Enum):
    AND = 0
    OR = 1


class RequirementTarget(Enum):
    caster = 0
    target = 1


class MinionType(Enum):
    is_minion = 0
    has_minion = 1
    on_team = 2
    on_other_team = 3
    on_any_team = 4


class StatusEffect(Enum):
    stunned = 0
    confused = 1


class UnlockTriggerState(Enum):
    """State of a guild unlock trigger.

    Derived from MSG_UpdateGuildUnlockTrigger handler at 0x141213a10:
    state == 2 triggers island unlock via FUN_141222630.
    """

    locked = 0
    in_progress = 1
    completed = 2
