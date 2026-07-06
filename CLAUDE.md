# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EndStone ARC Core (`arc_core`) is a comprehensive plugin for Minecraft Bedrock Edition servers running the [EndStone](https://github.com/EndstoneMC/endstone) framework. It provides economy, land claims, teleportation, guilds, titles, achievements, daily check-in, and more. The plugin is written in Python and distributed as a `.whl` file.

- **Entry point**: `src/endstone_arc_core/__init__.py` exports `ARCCorePlugin`
- **Plugin class**: `src/endstone_arc_core/arc_core_plugin.py` — the main `ARCCorePlugin(Plugin)` class (~674k, contains event handlers, form logic, command handlers)
- **API version**: EndStone 0.7+ (pyproject.toml declares `api_version = "0.10"`)
- **Python**: 3.13+

## Build & Distribution

```bash
# Build the wheel (uses hatchling)
pip install build && python -m build
# Output: dist/endstone_arc_core-<version>-py2.py3-none-any.whl
```

To install into a server: copy the `.whl` into the EndStone server's environment and `pip install` it, then restart the server. The plugin auto-creates `plugins/ARCCore/` with config files and SQLite database on first load.

There are **no tests** in this repository — no test runner, no test files.

## Architecture

### Module Map

| File | Role |
|---|---|
| `arc_core_plugin.py` | Main plugin class: event handlers (`on_player_join`, `on_block_break`, etc.), all form/UI builders (main menu, OP panel, sub-menus), command dispatch, position-check thread, API methods exposed to other plugins |
| `DatabaseManager.py` | Thread-safe SQLite wrapper with table-level routing (for cross-server DB splitting). Provides `execute`, `query_one`, `query_all`, `insert`, `update`, `delete`, `create_table` |
| `Economy.py` | Balance CRUD, transfer logic, richest-player tracking |
| `LandSystem.py` | Land claim creation, overlap detection, chunk-index lookup, protection enforcement, sub-lands, land sales with VAT |
| `TeleportSystem.py` | Home/warp/TPA/random/death/cross-server teleport; `generate_tp_command_to_position()` helper |
| `GuildSystem.py` | Guild CRUD, membership, invites, contribution points, size tiers, join approval |
| `TitleSystem.py` | Title definitions, unlock tracking, equip/unequip, rarity colors |
| `AchievementSystem.py` | Achievement definitions (JSON-based), kill/progress tracking, condition evaluation |
| `achievement_conditions.py` | Condition type definitions (`kill_entity`, `kill_entity_sum`) |
| `LanguageManager.py` | i18n via `key=value` text files (e.g., `ZH-CN.txt`); class-level dict cache |
| `SettingManager.py` | Config via `core_setting.yml` (`KEY=VALUE` format); class-level dict cache |
| `EntityDisplayNameManager.py` | Entity display name lookups from `entity_display_name.txt` |
| `KillRewardConfig.py` | Kill-reward config from `kill_reward.txt` (`minecraft:creeper=10`) |
| `sky_eye_log.py` | Audit logging to `plugins/ARCCore/sky_eye/YYYYMMDD.txt` with retention pruning |
| `arc_error_log.py` | Thread-safe error logging to `error_log.txt` |
| `mc_command_format.py` | Utility: quote player names containing spaces for MC commands |

### Key Design Patterns

1. **Single monolith + satellite modules**: `arc_core_plugin.py` is the hub (~674KB). All event handlers, UI forms, and command logic live there. Satellite modules (`LandSystem`, `GuildSystem`, etc.) encapsulate domain logic and DB access.

2. **Database routing**: `DatabaseManager` supports per-table routing to different SQLite files via `add_route(table_name, db_path)`. This enables cross-server data sharing (e.g., `PLAYER_DATABASE_PATH`, `GUILD_DATABASE_PATH` config keys).

3. **Config files** (in `plugins/ARCCore/`):
   - `core_setting.yml` — `KEY=VALUE` pairs (not real YAML; parsed line-by-line)
   - `ZH-CN.txt` — language strings, same `KEY=VALUE` format
   - `broadcast.txt` — one broadcast message per line, supports `{date}`, `{time}`, `{online_player_number}` placeholders
   - `newbie_welcome.txt` / `newbie_commands.txt` — new-player welcome content and auto-commands (`{player}` placeholder)
   - `kill_reward.txt` — `minecraft:entity_type=money_amount` per line
   - `entity_display_name.txt` — `entity.minecraft.xxx.name=DisplayName`
   - `achievements.json` — achievement definitions

4. **XUID as primary key**: All player data uses Xbox XUID (not UUID or player name). Player names are resolved to XUID via online player list (case-insensitive) or database lookup (`LOWER(TRIM(name))`).

5. **Thread safety**: Database operations use thread-local connections. Position checking runs in a background thread. All file I/O (error log, sky eye) uses `threading.Lock`.

6. **Sensitive operation flow**: Transfers, land creation, guild creation require password verification (SHA-256 hash). Verification is session-scoped (per player login). Unregistered players are prompted to set a password first.

7. **Form-based UI**: All player interaction uses EndStone's `ActionForm`, `ModalForm`, `TextInput`, `Dropdown`, `Label` APIs. Forms are built as methods in `arc_core_plugin.py`.

### Coordinate Handling

All block coordinate calculations use `math.floor()` to handle negative coordinates correctly. The land system uses min/max X/Y/Z bounding boxes with chunk-based spatial indexing.

### Cross-Server Support

Multiple config keys (`PLAYER_DATABASE_PATH`, `PLAYER_ECONOMY_DATABASE_PATH`, `PLAYER_TITLE_DATABASE_PATH`, `GUILD_DATABASE_PATH`) route specific tables to shared SQLite files, enabling data sharing across server instances.

## Configuration

`core_setting.yml` uses a custom `KEY=VALUE` format (not standard YAML). Key settings include:

- `DATABASE_PATH` — main SQLite file (relative to `plugins/ARCCore/`)
- `PLAYER_INIT_MONEY_NUM` — starting balance for new players
- `LAND_PRICE` — cost per block for land claims
- `GUILD_CREATE_COST` — cost to create a guild
- `GUILD_SIZE_SMALL_MAX` / `MEDIUM` / `LARGE` — member caps per tier
- `ENABLE_SKY_EYE` — toggle audit logging
- `DEFAULT_TITLE` — comma-separated titles given to all players on join
- `OP_TITLE` — single title reserved for OPs

## Plugin API

Other EndStone plugins can call methods on the `ARCCorePlugin` instance via `server.get_plugin('arc_core')`:

- **Economy**: `api_get_player_money`, `api_change_player_money`, `api_get_all_money_data`, `api_get_richest_player_money_data`
- **Titles**: `api_unlock_title(player, title_name)`
- **Lands**: `api_if_position_in_land(dimension, (x,y,z))`, `api_get_land_info(land_id)`
- **Guilds**: `api_get_player_guild_info(player_name)`, `api_add_guild_contribution(player_name, points)`, `api_get_player_guild_contribution`, `api_get_guild_total_contribution_by_player`, `api_set_guild_size_tier`
- **Newbie**: `api_get_newbie_guide_text()`

All API methods are thread-safe.

## Language

The primary language is Chinese (ZH-CN). Language strings are in `dist/ARCCore/ZH-CN.txt`. When adding new UI text, add corresponding `KEY=VALUE` entries to the language file and use `self.language_manager.GetText('KEY')` in code.
