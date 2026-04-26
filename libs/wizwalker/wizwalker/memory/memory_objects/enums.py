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
    set_heal_percent = 113
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
    modify_incoming_damage = 22
    modify_incoming_damage_flat = 119
    maximum_incoming_damage = 23
    modify_incoming_heal = 24
    modify_incoming_heal_flat = 118
    modify_incoming_damage_type = 25
    modify_incoming_armor_piercing = 26
    modify_outgoing_damage = 27
    modify_outgoing_damage_flat = 121
    modify_outgoing_heal = 28
    modify_outgoing_heal_flat = 120
    modify_outgoing_damage_type = 29
    modify_outgoing_armor_piercing = 30
    modify_outgoing_steal_health = 31
    modify_incoming_steal_health = 32
    bounce_next = 33
    bounce_previous = 34
    bounce_back = 35
    bounce_all = 36
    absorb_damage = 37
    absorb_heal = 38
    modify_accuracy = 39
    dispel = 40
    confusion = 41
    cloaked_charm = 42
    cloaked_ward = 43
    stun_resist = 44
    clue = 111
    pip_conversion = 45
    crit_boost = 46
    crit_block = 47
    polymorph = 48
    delay_cast = 49
    modify_card_cloak = 50
    modify_card_damage = 51
    modify_card_accuracy = 53
    modify_card_mutation = 54
    modify_card_rank = 55
    modify_card_armor_piercing = 56
    summon_creature = 65
    teleport_player = 66
    stun = 67
    dampen = 68
    reshuffle = 69
    mind_control = 70
    modify_pips = 71
    modify_power_pips = 72
    modify_shadow_pips = 73
    modify_hate = 74
    damage_over_time = 75
    heal_over_time = 76
    modify_power_pip_chance = 77
    modify_rank = 78
    stun_block = 79
    reveal_cloak = 80
    instant_kill = 81
    afterlife = 82
    deferred_damage = 83
    damage_per_total_pip_power = 84
    modify_card_heal = 52
    modify_card_charm = 57
    modify_card_ward = 58
    modify_card_outgoing_damage = 59
    modify_card_outgoing_accuracy = 60
    modify_card_outgoing_heal = 61
    modify_card_outgoing_armor_piercing = 62
    modify_card_incoming_damage = 63
    modify_card_absorb_damage = 64
    cloaked_ward_no_remove = 86
    add_combat_trigger_list = 87
    remove_combat_trigger_list = 88
    backlash_damage = 89
    modify_backlash = 90
    intercept = 91
    shadow_self = 92
    shadow_creature = 93
    modify_shadow_creature_level = 94
    select_shadow_creature_attack_target = 95
    shadow_decrement_turn = 96
    crit_boost_school_specific = 97
    spawn_creature = 98
    un_polymorph = 99
    power_pip_conversion = 100
    protect_card_beneficial = 101
    protect_card_harmful = 102
    protect_beneficial = 103
    protect_harmful = 104
    divide_damage = 105
    collect_essence = 106
    kill_creature = 107
    dispel_block = 108
    confusion_block = 109
    modify_pip_round_rate = 110
    max_health_damage = 112
    untargetable = 114
    make_targetable = 115
    force_targetable = 116
    remove_stun_block = 117
    exit_combat = 122
    suspend_pips = 123
    resume_pips = 124
    auto_pass = 125
    stop_auto_pass = 126
    vanish = 127
    stop_vanish = 128
    max_health_heal = 129
    heal_by_ward = 130
    taunt = 131
    pacify = 132
    remove_target_restriction = 133
    convert_hanging_effect = 134
    add_spell_to_deck = 135
    add_spell_to_hand = 136
    modify_incoming_damage_over_time = 137
    modify_incoming_heal_over_time = 138
    modify_card_damage_by_rank = 139
    push_converted_charm = 140
    steal_converted_charm = 141
    push_converted_ward = 142
    steal_converted_ward = 143
    push_converted_over_time = 144
    steal_converted_over_time = 145
    remove_converted_charm = 146
    remove_converted_ward = 147
    remove_converted_over_time = 148
    modify_over_time_duration = 149
    modify_school_pips = 150
    shadow_pact = 151


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
