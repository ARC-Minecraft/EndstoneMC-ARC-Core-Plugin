# -*- coding: utf-8 -*-
"""基岩版客户端字体 Private Use Area 字形（HUD / Toast 图标）。

在 toast 标题等处使用时，由玩家客户端字体渲染为对应图标，
而非普通 Unicode 文字。映射与基岩内置 glyph 一致。
"""

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
    "TOAST_DEFAULT_TITLE": STAR_SOLID,
    "MONEY_ADD_TOAST_TITLE": COIN,
    "MONEY_REDUCE_TOAST_TITLE": COIN,
    "TRANSFER_RECEIVE_TOAST_TITLE": COIN,
    "TRANSFER_SEND_TOAST_TITLE": COIN,
    "TPA_REQUEST_TOAST_TITLE": CAMERA,
    "TPA_RESULT_TOAST_TITLE": CAMERA,
    "LAND_RESULT_TOAST_TITLE": PICKAXE,
    "ACCOUNT_TOAST_TITLE": BOOK,
    "INVITE_TOAST_TITLE": STAR_HOLLOW,
    "GUILD_TOAST_TITLE": STAR_SOLID,
    "HOME_TOAST_TITLE": CRAFTING_TABLE,
    "SMALL_HORN_TOAST_TITLE": AGENT,
}
