from typing import *

from lark import Transformer

from .combat_api import *

# TODO: bias for auto may be interesting


def get_sprinty_grammar():
    return r"""
            ?start: config
            config: line+
            
            line: round_specifier? move_config [(_pipe move_config)*]? _NEWLINE?
            
            move_config: move (_at target)? [(_and move (_at target)?)*]?

            move: (move_pass | move_willcast | move_draw | (spell enchant? second_enchant?))
            move_pass: _spaced{"pass"}
            move_willcast: _spaced{"willcast"}
            move_draw: _spaced{"draw"} (_open_paren INT _close_paren)?
            move_discard: _spaced{"discard"}

            spell: any_spell | words | string
            enchant: _open_bracket (any_spell | words | string) _close_bracket
            second_enchant: _open_bracket (any_spell | words | string) _close_bracket
            
            target: (target_type | target_select)
            target_type: target_self | target_boss | target_enemy | target_ally | target_aoe | target_spell | target_named
            target_self: _spaced{"self"}
            target_boss: _spaced{"boss"}
            target_enemy: _spaced{"enemy"} (_open_paren INT _close_paren)?
            target_ally: _spaced{"ally"} (_open_paren INT _close_paren)?
            target_aoe: _spaced{"aoe"}
            target_named: words | string
            target_spell: _spaced{"spell"} _open_paren (any_spell | words | string) [(_comma (any_spell | words | string))*]? _close_paren
            target_select: _spaced{"select"} _open_paren target_type [(_comma target_type)*]? _close_paren | target_type [(_comma target_type)*]?
            
            round_specifier: _newlines? "{" expression "}" _newlines?
            
            
            auto: _spaced{"auto"}
            
            any_spell: _spaced{"any"} _less_than spell_type [(_and spell_type)*]? _greater_than
            spell_type: spell_damage | spell_aoe | spell_heal_self | spell_heal_other | spell_heal | spell_blade | spell_charm | spell_ward | spell_trap | spell_enchant | spell_aura | spell_global | spell_polymorph | spell_shadow | spell_shadow_creature | spell_pierce | spell_prism | spell_dispel | spell_inc_damage | spell_out_damage | spell_inc_heal | spell_out_heal | spell_mod_damage | spell_mod_heal | spell_mod_pierce
            spell_damage: _spaced{"damage"}
            spell_aoe: _spaced{"aoe"}
            spell_heal: _spaced{"heal"}
            spell_heal_self: spell_heal _spaced{"self"}
            spell_heal_other: spell_heal _spaced{"other"}
            spell_blade: _spaced{"blade"}
            spell_charm: _spaced{"charm"}
            spell_ward: _spaced{"ward"}
            spell_trap: _spaced{"trap"}
            spell_enchant: _spaced{"enchant"}
            spell_aura: _spaced{"aura"}
            spell_global: _spaced{"global"}
            spell_polymorph: _spaced{"polymorph"}
            spell_shadow: _spaced{"shadow"}
            spell_shadow_creature: _spaced{"shadow_creature"}
            spell_pierce: _spaced{"pierce"}
            spell_prism: _spaced{"prism"}
            spell_dispel: _spaced{"dispel"}
            spell_inc_damage: _spaced{"inc_damage"}
            spell_out_damage: _spaced{"out_damage"}
            spell_inc_heal: _spaced{"inc_heal"}
            spell_out_heal: _spaced{"out_heal"}
            spell_mod_damage: _spaced{"mod_damage"}
            spell_mod_heal: _spaced{"mod_heal"}
            spell_mod_pierce: _spaced{"mod_pierce"}
            
            expression: INT
            
            words: _newlines? word [word*] _newlines?
            word: NAME | ("0".."9")
            string: _newlines? ESCAPED_STRING _newlines?
            
            
            _open_paren: _spaced{"("}
            _close_paren: _spaced{")"}
            _open_bracket: _spaced{"["}
            _close_bracket: _spaced{"]"}
            _less_than: _spaced{"<"}
            _greater_than: _spaced{">"}
            _comma: _spaced{","}
            
            _at: _spaced{"@"}
            _pipe: _spaced{"|"}
            _and: _spaced{"&"}
            CR: "\r"
            LF: "\n"
            _NEWLINE: CR? LF
            _newlines: [_NEWLINE]*
            
            _spaced{tok}: _newlines? tok _newlines?
            
            
            %import common.INT
            %import common.CNAME -> NAME
            %import common.WS_INLINE
            %import common.ESCAPED_STRING
            
            
            %ignore WS_INLINE
        """


class TreeToConfig(Transformer):
    def spell(self, items, enchant: bool = False):
        if type(items[0]) is not str:
            if enchant:
                return TemplateSpell(items[0], optional=True)
            return TemplateSpell(items[0])
        else:
            name: str = items[0]
            if name.startswith("\""):
                return NamedSpell(name[1:-1], True)
            return NamedSpell(name, False)

    def enchant(self, items):
        return self.spell(items, enchant=True)

    def second_enchant(self, items):
        return self.spell(items, enchant=True)
    
    def move_pass(self, items):
        return NamedSpell("pass")

    def move_willcast(self, items):
        return NamedSpell("willcast")

    def move_draw(self, items):
        if len(items) > 0:
            return DrawSpell(items[0])
        return DrawSpell()

    def move_discard(self, items):
        return NamedSpell("discard")

    def move(self, items):
        return Move(*items)

    def move_config(self, items):
        movestargets = {}
        move_count = 0
        for i, item in enumerate(items):
            if type(item) is Move:
                move_count += 1
                if i + 1 < len(items) and type(items[i + 1]) is not Move:
                    target_data = items[i + 1]
                    if type(target_data) is not TargetType:
                        t, n = target_data
                        if type(n) is str and n.startswith("\""):
                            movestargets[item] = TargetData(t, n[1:-1], is_literal=True)
                            #return MoveConfig(items[0], TargetData(t, n[1:-1], is_literal=True))
                        elif type(n) is list:
                            for index, target in enumerate(n):
                                if type(target) is tuple and len(target) > 1 and type(target[1]) is str and target[1].startswith("\""):
                                    n[index] = TargetData(target[0], target[1][1:-1], is_literal=True)
                                elif type(target) is tuple:
                                    n[index] = TargetData(target[0], target[1])
                                elif isinstance(target, Spell):
                                    pass
                                else:
                                    n[index] = TargetData(target)
                            movestargets[item] = TargetData(t, n)
                        else:
                            movestargets[item] = TargetData(t, n)
                    else:
                        movestargets[item] = TargetData(target_data, None)
                else:
                    movestargets[item] = None
            #return MoveConfig(items[0], TargetData(t, n))
        if move_count < 2:
            move, target = (list(movestargets.keys())[0], list(movestargets.values())[0])
            return MoveConfig(move, target)
        moves = [x for x in movestargets.keys()]
        targets = [x for x in movestargets.values()]
        return MoveConfig(moves, targets)
        #elif len(items) > 1: 
            #return MoveConfig(items[0], TargetData(items[1]))
        #return MoveConfig(items[0])

    def line(self, items):
        if type(items[0]) is int:
            return PriorityLine(items[1:], items[0])
        return PriorityLine(items)

    def config(self, items):
        return CombatConfig(items)

    def target_self(self, _):
        return TargetType.type_self

    def target_spell(self, items):
        if type(items) is list and len(items) > 1:
            new_items = []
            for item in items:
                item = [item]
                new_items.append(self.spell(item))
            return TargetType.type_spell, new_items
        return TargetType.type_spell, self.spell(items)

    def target_boss(self, _):
        return TargetType.type_boss

    def target_enemy(self, items):
        if len(items) > 0:
            return TargetType.type_enemy, items[0]
        return TargetType.type_enemy

    def target_ally(self, items):
        if len(items) > 0:
            return TargetType.type_ally, items[0]
        return TargetType.type_ally

    def target_aoe(self, _):
        return TargetType.type_aoe

    def target_named(self, items):
        return TargetType.type_named, items[0]

    def target_type(self, items):
        return items[0]

    def target(self, items):
        return items[0]

    def target_select(self, items):
        return TargetType.type_select, items

    def any_spell(self, items):
        return items

    def spell_type(self, items):
        return items[0]

    def spell_damage(self, _):
        return SpellType.type_damage

    def spell_aoe(self, _):
        return SpellType.type_aoe

    def spell_heal_self(self, _):
        return SpellType.type_heal_self

    def spell_heal_other(self, _):
        return SpellType.type_heal_other

    def spell_heal(self, _):
        return SpellType.type_heal

    def spell_blade(self, _):
        return SpellType.type_blade
    
    def spell_charm(self, _):
        return SpellType.type_charm

    def spell_ward(self, _):
        return SpellType.type_ward

    def spell_trap(self, _):
        return SpellType.type_trap

    def spell_enchant(self, _):
        return SpellType.type_enchant

    def expression(self, items):
        return items[0]

    def round_specifier(self, items):
        return items[0]
    
    def spell_aura(self, _):
        return SpellType.type_aura
    
    def spell_global(self, _):
        return SpellType.type_global
    
    def spell_polymorph(self, _):
        return SpellType.type_polymorph
    
    def spell_shadow(self, _):
        return SpellType.type_shadow
    
    def spell_shadow_creature(self, _):
        return SpellType.type_shadow_creature
    
    def spell_pierce(self, _):
        return SpellType.type_pierce
    
    def spell_prism(self, _):
        return SpellType.type_prism
    
    def spell_dispel(self, _):
        return SpellType.type_dispel
    
    def spell_inc_damage(self, _):
        return SpellType.type_inc_damage
    
    def spell_out_damage(self, _):
        return SpellType.type_out_damage
    
    def spell_inc_heal(self, _):
        return SpellType.type_inc_heal
    
    def spell_out_heal(self, _):
        return SpellType.type_out_heal
    
    def spell_mod_damage(self, _):
        return SpellType.type_mod_damage
    
    def spell_mod_heal(self, _):
        return SpellType.type_mod_heal
    
    def spell_mod_pierce(self, _):
        return SpellType.type_mod_pierce

    INT = int

    def word(self, s):
        s, = s
        return s

    def words(self, items) -> str:
        res = ""
        for i in items:
            res += f" {i}"
        return res[1:]

    def string(self, items) -> str:
        res: str = items[0]
        res = res.encode("latin1").decode("unicode_escape")
        return res
