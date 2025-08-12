import base64
from typing import Optional
import zlib


class DeckEncoderDecoder:
    """
    A utility class used to encode decks into tokens, and tokens back into decks. Useful for saving deck builds and reusing them in bots.
    """

    def __init__(self, token: Optional[str] = None, deck: Optional[dict] = None):
        self.deck: Optional[dict] = deck
        self.token: Optional[str] = token
        self._DELIMITER1 = '\\+'
        self._DELIMITER2 = '\\,'
        self._DELIMITER3 = '\\;'

    def _serialize_section(self, section: dict) -> str:
        """
        Serialize a dictionary section into a compact string.
        """
        if not section:
            return "N"
        return self._DELIMITER2.join(f"{key}{self._DELIMITER1}{value}" for key, value in section.items())

    def _deserialize_section(self, section: str) -> dict:
        """
        Deserialize a section back into dictionary format
        """
        if section == "N":
            return {}
        return {key: int(value) for key, value in (item.split(self._DELIMITER1) for item in section.split(self._DELIMITER2))}

    def encode(self) -> str:
        """
        Encode the deck dictionary into a reusable token.
        """
        if not self.deck and not self.token:
            raise ValueError('No deck found.')
        elif self.token and not self.deck:
            return self.token

        for key in ["normal", "tc", "item"]:
            if not key in self.deck:
                raise ValueError(f"Deck is missing {key} section.")

        deck_final = self._DELIMITER3.join([
            self._serialize_section(self.deck['normal']),
            self._serialize_section(self.deck['tc']),
            self._serialize_section(self.deck['item']),
        ])

        compressed = zlib.compress(deck_final.encode())
        self.token = base64.b64encode(compressed).decode()
        return self.token

    def decode(self) -> dict:
        """
        Decode the deck back into its original dictionary format.
        """
        if not self.token:
            raise Exception('No token found.')
        try:
            deck_final = base64.b64decode(self.token.encode("utf-8"))
            deck_final = zlib.decompress(deck_final).decode()
            sections = deck_final.split(self._DELIMITER3)
        except (zlib.error, ValueError, IndexError) as e:
            raise ValueError("Invalid token format or corrupted data.") from e
        self.deck = {
            "normal": self._deserialize_section(sections[0]),
            "tc": self._deserialize_section(sections[1]),
            "item": self._deserialize_section(sections[2]),
        }
        return self.deck


if __name__ == "__main__":
    deck1 = {'normal': {'Colossal': 5, 'Giant': 7, 'Monstrous': 6, 'Potent Trap': 4, 'Strong': 3, 'Vaporize': 1, 'Avenging Fossil': 3, 'Beguile': 3, 'Call of Khrulhu': 3, 'Gambit_Death_02': 9, 'GhostTouchRed_Trainable': 1, 'Mega Pacify': 1, 'Minion Death Seraph': 3, 'Poison': 3, 'Ramp_Death_02': 1, 'Skeletal Pirate - T02 - A': 6, 'Vampire': 1, 'Catalan': 2, 'Tri Blade': 1, 'Tri Trap': 1}, 'tc': {'Frost Beetle TC': 1, 'Frost Giant TC': 3, 'Frozen Armor TC': 1,
                                                                                                                                                                                                                                                                                                                                                                                                               'Legion Shield TC': 1, 'Snow Serpent - T02 - B - TC': 1, 'Steal Ward TC': 2, 'Centaur TC': 1, 'Forest Lord TC': 1, 'Giant Spider TC KR': 2, 'Rebirth TC': 1, 'Regenerate TC': 2, 'Sanctuary TC': 3, 'Satyr TC': 2, 'Seraph - T02 - B - TC': 1, 'Spinysaur TC': 6, 'Spirit Armor TC': 3, 'Sprite Swarm TC KR': 1, 'Unicorn TC': 2, 'Heck Hound TC': 3, 'Steal Charm TC': 1, 'Wild Bolt TC': 2}, 'item': {'Moon Shield': 1, 'Wand-Death-145': 4, 'Shadow Trap - Amulet': 2}}
    # deck1 = {"tc":{"boss": 4}, "normal":{}, "item":{}}
    coder = DeckEncoderDecoder(deck=deck1)
    print("Encoding...")
    token = coder.encode()
    print(len(token.encode()))
    print("Token: \n", token)
    print('Decoding...')
    deck2 = coder.decode()
    print(len(deck2.__str__().encode()))
    print(deck2)
    assert (deck1 == deck2)
