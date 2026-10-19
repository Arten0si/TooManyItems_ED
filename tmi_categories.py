# -*- coding: utf-8 -*-
"""
TooManyItems_ED – podkategorie przedmiotów (np. Budowanie → Bloki, Stanowiska, Meble…).

Gra nie zapisuje zakładek swojego menu budowania w danych przedmiotów (keen::ItemInfo ma tylko
`category`), więc podkategorie liczymy z nazw wewnętrznych (debugName), miejsca w ekwipunku (slot)
i rodzaju amunicji. Reguły sprawdzane po kolei – pierwsza pasująca wygrywa.
Nazwy podkategorii (15 języków) są w gui/i18n.js w grupie `sub` (klucz = kod poniżej).
Po aktualizacji gry: `python tmi_categories.py` pokazuje, ile przedmiotów trafiło do „Pozostałe”.
"""

import re

# Kolejność podkategorii w oknie (kod, …). Podkategoria bez przedmiotów nie jest pokazywana.
ORDER = {
    "BuildTools": ["blocks", "stations", "upgrades", "storage", "furniture", "lighting", "doors", "structures",
                   "walldeco", "trophies", "showcases", "vessels", "plants", "water", "logic", "animals", "npc",
                   "fireworks", "buildtools", "decor", "other"],
    "Equipment": ["head", "chest", "hands", "legs", "feet", "vanity", "shields", "rings", "backpacks", "looks"],
    "Weapons": ["swords", "greatswords", "axes", "greataxes", "maces", "hammers", "daggers", "bows", "staffs",
                "wands", "throwables", "torches", "other"],
    "Consumables": ["meals", "drinks", "rawfood", "potions", "medical", "other"],
    "Materials": ["terrain", "bars", "ores", "wood", "plantmat", "animalmat", "crafted", "magic", "trophymat", "keys", "other"],
    "Ammunition": ["arrows", "spells", "bait", "traps", "other"],
    "Collectibles": ["fossils", "skeletons", "mosaics", "meteorites", "maps", "scrolls", "other"],
    "Tools": ["hatchets", "gliders", "hooks", "keys", "other"],
}


def _has(debug, *words):
    d = debug.lower()
    return any(w in d for w in words)


def _build(d, slot):
    dl = d.lower().lstrip("_")
    if dl.startswith(("block_", "quest_reward_icon_chest")) or slot in ("BlueprintMaterial_Default", "BlueprintMaterial_Roof"):
        return "blocks"
    if "wighead" in dl:
        return "showcases"
    if dl.startswith(("prop_production", "craftingstation", "prop_npc")):
        return "stations"
    if dl.startswith("prop_component"):
        return "upgrades"
    if dl.startswith("prop_storage"):
        return "storage"
    if dl.startswith(("animal_",)):
        return "animals"
    if dl.startswith(("npc_", "npcsummoner")):
        return "npc"
    if dl.startswith("prop_water") or slot == "BlockWater":
        return "water"
    if dl.startswith("prop_logic"):
        return "logic"
    if "seedling" in dl or dl.startswith(("flower_", "empty_flower", "material_")) or slot == "OvergrowthMaterial":
        return "plants"
    if dl.startswith("consumable_toy"):
        return "fireworks"
    if dl.startswith(("tool_", "buildtool")):
        return "buildtools"
    if dl.startswith("prop_collection") or "mannequin" in dl or "weaponstand" in dl:
        return "showcases"
    if dl.startswith("collection_"):
        return "walldeco"
    if dl.startswith("base_") or _has(d, "door", "window", "gate", "hatch"):
        return "doors"
    if _has(d, "illumination", "brazier", "torch", "lantern", "candle", "chandelier", "lamp", "fireplace", "hearth"):
        return "lighting"
    if _has(d, "trophy", "skull", "statue", "totem", "tombstone"):
        return "trophies"
    if _has(d, "banner", "painting", "tapestry", "emblem", "flagpole", "flag_", "wallhang", "sign"):
        return "walldeco"
    if _has(d, "fence", "palisade", "stairs", "ladder", "column", "pole", "support", "banister", "railing",
            "boardwalk", "barricade", "awning", "beam", "pillar", "arc_", "roof", "platform", "bridge"):
        return "structures"
    if _has(d, "table", "chair", "bed", "bench", "stool", "cabinet", "shelf", "cupboard", "sideboard", "throne",
            "wardrobe", "desk", "sofa", "bathroom", "divider", "pillow", "carpet", "rug", "dresser", "seat",
            "drawer"):
        return "furniture"
    if _has(d, "vase", "jug", "bowl", "cup", "_pot", "platter", "bottle", "crate", "basket", "barrel", "vat_",
            "container", "sack", "jar", "kettle", "cauldron", "plate", "mug", "chest", "box"):
        return "vessels"
    if dl.startswith(("prop_decoration", "prop_furniture", "prop_sign", "prop_")):
        return "decor"
    return "other"


def _equip(d, slot):
    if slot == "BodyPart_Beard" or d.startswith("Icon_"):
        return "looks"
    if "vanity" in d.lower():
        return "vanity"
    return {"Armour_Head": "head", "Armour_UpperBody": "chest", "Armour_Arms": "hands",
            "Armour_LowerBody": "legs", "Armour_Feet": "feet", "Shield": "shields",
            "Armour_Ring": "rings", "Backpack": "backpacks"}.get(slot, "other")


WEAPON_RULES = [("greatsword", "greatswords"), ("greataxe", "greataxes"), ("sword", "swords"), ("axe", "axes"),
                ("mace", "maces"), ("hammer", "hammers"), ("dagger", "daggers"), ("bow", "bows"),
                ("staff", "staffs"), ("wand", "wands")]


def _weapon(d, slot):
    dl = d.lower()
    if "torch" in dl:
        return "torches"
    if "grenade" in dl or "bomb" in dl or "throwable" in dl or dl.lstrip("_").startswith("consumable"):
        return "throwables"
    for w, sub in WEAPON_RULES:
        if w in dl:
            return sub
    return {"RangeWeapon": "bows", "MidRangeWeapon": "wands"}.get(slot, "other")


def _consumable(d, slot):
    dl = d.lower()
    if "potion" in dl or "flask" in dl or "scroll" in dl or "resistance" in dl:
        return "potions"
    if "bandage" in dl or "repairkit" in dl:
        return "medical"
    if "hydration" in dl or "tea" in dl or "water" in dl or "juice" in dl or "beer" in dl or "wine" in dl:
        return "drinks"
    if "_raw" in dl or "raw_" in dl:
        return "rawfood"
    if dl.lstrip("_").startswith("food"):
        return "meals"
    return "other"


def _material(d, slot):
    dl = d.lower()
    if slot == "TerrainMaterial" or dl.startswith("build_terrainmaterial"):
        return "terrain"
    if dl.startswith("key_"):
        return "keys"
    if "trophy" in dl or _has(d, "cyclopseye", "felltalon", "vorgoth", "monstrousribs", "corruptedboar"):
        return "trophymat"
    if re.search(r"_bars?$|_ingot", dl):
        return "bars"
    if _has(d, "ore_", "_ore", "metal", "scrap", "nugget", "gem", "crystal", "amber", "amethyst", "pearl",
            "sulfur", "salt", "coal", "charcoal", "stone", "flint", "clay", "sand", "glass", "_dust", "diamond",
            "aquamarine", "lapis", "obsidian", "marble", "nitrate", "vitriol"):
        return "ores"
    if _has(d, "wood", "log", "plank", "twig", "bark", "resin", "stick"):
        return "wood"
    if _has(d, "essence", "spark", "shroud", "fog", "archaic", "core", "rune", "ectoplasm", "glowdirt", "magic",
            "infusion", "fellmist", "glow_dust", "goo", "mauveine"):
        return "magic"
    if _has(d, "fur", "leather", "pelt", "hide", "bone", "teeth", "tooth", "claw", "feather", "meat", "fat",
            "gland", "critter", "wool", "egg", "horn", "scale", "chitin", "shell", "silk", "fish", "lizard",
            "bristle", "blood", "bug_", "poison", "sting", "tusk", "wax"):
        return "animalmat"
    if _has(d, "fibre", "fiber", "flax", "flower", "herb", "leaves", "leaf", "berry", "mushroom", "seed",
            "grain", "wheat", "corn", "straw", "plant", "indigo", "moss", "root", "nut", "fruit", "cotton",
            "aloe", "chamomile", "lily", "gentian", "coffee", "rice", "rooibos", "saffron", "wolfsbane"):
        return "plantmat"
    if _has(d, "nail", "fabric", "cloth", "rope", "brick", "linen", "ointment", "pastry", "dough", "flour",
            "dye", "paste", "glue", "oil", "paper", "string", "thread", "powder", "base", "antiseptic",
            "broth", "padding", "tar", "books", "skewer", "sawblade"):
        return "crafted"
    return "other"


def _ammo(d, slot):
    dl = d.lower()
    if "trap" in dl:
        return "traps"
    return {"Arrow": "arrows", "Spell": "spells", "FishingBait": "bait"}.get(slot, "other")


def _collect(d, slot):
    dl = d.lower()
    for w, sub in (("fossil", "fossils"), ("skeleton", "skeletons"), ("mosaic", "mosaics"),
                   ("meteorite", "meteorites"), ("map", "maps"), ("scroll", "scrolls"), ("lore", "scrolls")):
        if w in dl:
            return sub
    return "other"


def _tool(d, slot):
    dl = d.lower()
    if slot == "Glider" or "glider" in dl:
        return "gliders"
    if slot == "HookShot" or "grappl" in dl:
        return "hooks"
    if dl.startswith(("key_", "lockpick")):
        return "keys"
    if "axe" in dl:
        return "hatchets"
    return "other"


RULES = {"BuildTools": _build, "Equipment": _equip, "Weapons": _weapon, "Consumables": _consumable,
         "Materials": _material, "Ammunition": _ammo, "Collectibles": _collect, "Tools": _tool}


def subcategory(item):
    """Kod podkategorii albo None (kategoria bez podziału, np. Kolory, Waluta)."""
    fn = RULES.get(item.get("cat"))
    if not fn:
        return None
    return fn(item.get("debug") or "", item.get("slot"))


if __name__ == "__main__":                     # raport: ile w każdej podkategorii + przykłady „other”
    import collections
    import json
    import os
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    db = json.load(open(os.path.join(here, "items_db.json"), encoding="utf-8"))
    hid = re.compile(r"deprecated|depricated|^zz?_|(^|_)test(_|$)|debug|^ability_", re.I)
    items = [i for i in db["items"] if i["cat"] not in ("Blueprints", "Customization") and i["names"]
             and not i.get("obsolete") and not hid.search(i["debug"])]
    lang = sys.argv[1] if len(sys.argv) > 1 else "Pl_Pl"
    for cat, order in ORDER.items():
        xs = [i for i in items if i["cat"] == cat]
        c = collections.Counter(subcategory(i) for i in xs)
        print(f"\n== {cat} ({len(xs)}): " + ", ".join(f"{k} {c[k]}" for k in order if c[k]))
        bad = [k for k in c if k not in order]
        if bad:
            print("   !!! brak w ORDER:", bad)
        for sub in ("other", "decor"):
            ex = [i for i in xs if subcategory(i) == sub][:25]
            if ex:
                print(f"   {sub}: " + "; ".join(f"{i['names'].get(lang) or i['debug']}" for i in ex))
