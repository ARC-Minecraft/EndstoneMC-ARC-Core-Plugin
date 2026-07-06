# -*- coding: utf-8 -*-
"""Minecraft 基岩版指令字符串中与玩家名相关的格式化。"""


def format_mc_command_player_name(raw_player_name: str) -> str:
    """
    将玩家名格式化为指令中的一个参数。
    名称中含空格时须用双引号包裹，否则会被解析为多个参数。
    """
    name = str(raw_player_name or "")
    if " " in name:
        return f'"{name}"'
    return name
