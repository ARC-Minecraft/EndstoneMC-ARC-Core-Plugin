# -*- coding: utf-8 -*-
"""基岩版客户端字体 Private Use Area 字形（HUD / Toast 图标）。

在 toast 标题等处使用时，由玩家客户端字体渲染为对应图标，
而非普通 Unicode 文字。映射与基岩内置 glyph 一致。
"""

# 控制器 / 键鼠等（节选）
WINDOWS = "\uE0CD"

# 饥饿 / 护甲 / 金币 / 智能体 / 阅读 / T / 星 / 镐 / 剑 / 工作台 / 熔炉 / 生命 / 相机
HUNGER = "\uE100"
ARMOR = "\uE101"
COIN = "\uE102"
AGENT = "\uE103"
BOOK = "\uE104"
GLYPH_T = "\uE105"
STAR_HOLLOW = "\uE106"
STAR_SOLID = "\uE107"
PICKAXE = "\uE108"
SWORD = "\uE109"
CRAFTING_TABLE = "\uE10A"
FURNACE = "\uE10B"
HEART = "\uE10C"
CAMERA = "\uE10D"

# 语言键 → 场景图标（标题最前；语言文件已含该字形时不再重复添加）
TOAST_TITLE_ICONS = {
    "TOAST_DEFAULT_TITLE": WINDOWS,
    "MONEY_ADD_TOAST_TITLE": COIN,
    "MONEY_REDUCE_TOAST_TITLE": COIN,
    "TRANSFER_RECEIVE_TOAST_TITLE": COIN,
    "TRANSFER_SEND_TOAST_TITLE": COIN,
    "TPA_REQUEST_TOAST_TITLE": AGENT,
    "TPA_RESULT_TOAST_TITLE": AGENT,
    "LAND_RESULT_TOAST_TITLE": PICKAXE,
    "ACCOUNT_TOAST_TITLE": ARMOR,
    "INVITE_TOAST_TITLE": STAR_HOLLOW,
    "GUILD_TOAST_TITLE": SWORD,
    "HOME_TOAST_TITLE": CRAFTING_TABLE,
    "SMALL_HORN_TOAST_TITLE": BOOK,
}

# 用于剥离标题前已有的旧字形，再套用当前映射
KNOWN_TOAST_GLYPHS = (
    WINDOWS,
    HUNGER,
    ARMOR,
    COIN,
    AGENT,
    BOOK,
    GLYPH_T,
    STAR_HOLLOW,
    STAR_SOLID,
    PICKAXE,
    SWORD,
    CRAFTING_TABLE,
    FURNACE,
    HEART,
    CAMERA,
)
