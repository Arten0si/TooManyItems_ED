# TooManyItems – Item Vault for Enshrouded

Browse every item in **Enshrouded** and add any of them to your inventory with one click – in a separate,
game-styled window, while you play.

> Unofficial, free fan tool. Not affiliated with or endorsed by Keen Games.
> Enshrouded and all game assets © Keen Games GmbH.

**Download:** see [Releases](../../releases) (ZIP with `TooManyItems.exe`) – also on Nexus Mods (link will be added after publishing)

## Features

- **3,900+ items** with icons – weapons, armor, spells, food, building blocks, materials, gems…
- **One-click adding** – items appear in your inventory immediately and stack with what you carry.
- **Added the way the game does it** – the app asks the game's own inventory code to create the item
  (like loot), so weapons, armor and backpacks work right away and survive saving and reloading.
- **Full item cards** – rarity, item level, stats, perks, damage/protection types, descriptions – from the game files.
- **Choose the rarity** of loot weapons and armor (only the rarities the game allows) – the game creates exactly that one.
- **Categories with sub-categories** – e.g. Building → Blocks, Crafting stations, Furniture, Lighting…
- **15 languages** (item texts from the game itself, window translated too); follows your game language.
- Search by name, item ID or internal name (works without accents), category and rarity filters, sorting.
- **Nothing is put into the game folder.** No DLL, no file changes – the app runs on its own (e.g. on a second monitor).
- **Safe by design** – if the app is not sure where your inventory is, or the game version is not supported,
  it writes nothing and tells you why.

## Requirements

- Windows 10 / 11, 64-bit
- Enshrouded (Steam)
- Microsoft Edge WebView2 Runtime (included in Windows 11 and most Windows 10 systems)
- Single-player or a world **you host**. It cannot add items on someone else's server.

## Usage

1. Unpack the ZIP anywhere (not into the game folder).
2. Start Enshrouded and load your world.
3. Run `TooManyItems.exe` – the badge turns green: *Connected to game*.
4. Pick an item, set the amount, click **Add to inventory** (or double-click / Enter).

Back up your saves (`%LOCALAPPDATA%\Enshrouded\Saves`) before using it on your main world – just in case.

## How is this different from Creative Mode?

[Creative Mode](https://www.nexusmods.com/enshrouded/mods/146) by Phoenix1355 is an in-game menu (installed as
`dinput8.dll` in the game folder) with flying, creative building, gamepad support, multiplayer and dedicated servers.
If you want all of that – use it, it's great.

TooManyItems is a smaller, different tool:

| | TooManyItems | Creative Mode |
|---|---|---|
| Files in the game folder | none | `dinput8.dll` |
| Where | separate window (second monitor friendly) | menu inside the game |
| Item cards (stats, perks, descriptions) | yes, 15 languages | – |
| Multiplayer / dedicated servers | host only | yes |
| Flying, creative mode | – | yes |

## How it works (technical)

TooManyItems is a Python program (`tmi_core.py`) that attaches to the running `enshrouded.exe` with the standard
Windows API (`OpenProcess`, `ReadProcessMemory`, `WriteProcessMemory`, `VirtualAllocEx`) and installs two small hooks
(machine code in `ce/stub.s` and `ce/stub3.s`):

1. **Inventory hook** – in the loop that scans inventory rows; it records where your inventory rows live and can mark
   a row as changed so the game refreshes it.
2. **Item creation hook** – on the game thread it runs the same inventory transaction the game uses for loot
   (create item → commit), so item instances (weapons, armor, backpacks) are created by the game itself.

The game functions are located by **byte signatures** (several independent methods must agree), so most game patches
do not break the app. If the code does not match, the app refuses to install the hooks instead of risking a crash.

The window (`tmi_gui.py` + `gui/`) is a local web page served only on `127.0.0.1` with a random port and token,
shown with pywebview / WebView2.

### Antivirus

Because it writes into another process's memory (like trainers do), some antivirus programs may flag the `.exe` as a
false positive. The `.exe` is built with PyInstaller from this repository (no UPX packing) – you can read the code and
build it yourself (below).

## Building from source

The repository contains **code only**. The item database and icons are extracted from your own game installation:

```bat
cd tools
kfc-parser.exe unpack -g "C:\...\Enshrouded" -s -f "tkeen::ItemInfo" > ..\unpacked\items_all.jsonl
kfc-parser.exe unpack -g "C:\...\Enshrouded" -o ..\unpacked -f "tkeen::LocaTagCollectionResource"
kfc-parser.exe unpack -g "C:\...\Enshrouded" -s -f "tkeen::Perk" > ..\unpacked\perks_all.jsonl
python build_items_db.py "C:\...\Enshrouded"
python icons_game.py "C:\...\Enshrouded"
python icons_wiki.py pobierz
```

([kfc-parser](https://github.com/Brabb3l/kfc-parser) by Brabb3l.) Then:

- run from source: `start.bat` (Python 3.12+ 64-bit, installs `pywebview` on first start), or
- build the `.exe`: `release\build_exe.bat` (creates a venv with PyInstaller + pywebview, output in `release\dist`).

Comments in the code are in Polish.

## Credits & legal

- **Enshrouded**, item names, texts and graphics © **Keen Games GmbH**. Unofficial fan tool.
- Item icons: game files and [The Official Enshrouded Wiki](https://enshrouded.wiki.gg) – thanks to all contributors.
- Game file formats: [kfc-parser](https://github.com/Brabb3l/kfc-parser) by Brabb3l.
- Fonts: Cinzel and Alegreya Sans (SIL Open Font License).
- Code: [MIT License](LICENSE) – the license covers the app's code only, not game data or graphics.
