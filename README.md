# EndStone ARC Core Plugin

## 概述

EndStone ARC Core 是一个功能完整的 EndStone (Minecraft 基岩版服务器) 插件，为服务器提供全方位的核心功能模块。该插件包含玩家管理、经济系统、领地管理、传送系统、公告系统、清道夫系统、天眼行为审计等丰富功能，是构建现代化 Minecraft 服务器的理想选择。插件体验服：IP：arcclub.top，端口：19132，你可以在这个服务器试用体验本插件。

## 作者信息

- **作者**: DEVILENMO
- **邮箱**: DEVILENMO@gmail.com
- **版本**: 0.0.7.6
- **API 版本**: 0.7+
- **推荐 Python 版本**: 3.13

## ✨ 主要功能

### 🗄️ 数据库管理
- 基于 SQLite 的高性能数据库支持
- 线程安全的数据库连接管理
- 自动创建数据库文件和目录
- 支持复杂查询和事务处理
- **XUID主键系统** - 全面使用XUID作为玩家主键，提升数据一致性和查询性能
- **说明** - 自 v0.0.2.3 起不再支持从 UUID 到 XUID 的自动迁移，请使用已迁移至 XUID 的数据库或旧版本完成迁移后再升级

### 🌍 多语言支持
- 完整的国际化系统
- 动态语言文件加载
- 默认支持中文 (ZH-CN)
- 可扩展其他语言包

### 🧭 主菜单与子命令（`/arc`）
- 已登录玩家打开主菜单时，前几项顺序为：**新手引导 → 传送系统 → 领地系统 → 银行 → 公会 → 每日签到 → 我的信息 → 工具**（含小喇叭与重生）→ …
- **`/arc land`**、**`/arc tp`**、**`/arc bank`**、**`/arc guild`** 分别直接打开 **领地菜单**、**传送菜单**、**银行菜单**、**公会菜单**（需已通过密码登录；若从控制台/命令方块执行，会按 **命令发送者名称** 解析在线玩家，与 `/connecttoserver` 相同机制，便于命令方块代为弹出表单）

### 👤 玩家管理系统
- 密码认证登录系统
- **注册确认密码**（v0.0.3.0）：注册时需输入两次密码，一致方可完成
- **强制登录**（v0.0.3.0）：配置 `FORCE_LOGIN=True` 时，进服强制打开 /arc 登录或注册；关闭登录/注册页且未正确输入密码时会再次强制打开
- 玩家数据持久化存储
- 在线状态实时管理
- 玩家加入/离开消息提示

### 👁️ 天眼系统（Sky Eye，v0.0.7.6）
- **用途**：可选开启的玩家行为审计日志，按自然日写入文本，便于排查与合规留痕
- **配置**（`core_setting.yml`）：**`ENABLE_SKY_EYE`**（`True`/`False`，默认关闭）、**`SKY_EYE_MAX_RETENTION_DAYS`**（按文件名日期保留的天数，默认 **7**；更早日期的日志文件会被自动删除；**`0`** 表示不自动删除旧文件）
- **存储路径**：**`plugins/ARCCore/sky_eye/`**（目录名对应英文 **Sky Eye**）；每日一个文件，文件名 **`YYYYMMDD.txt`**（例如 `20260511.txt`），UTF-8 追加写入
- **记录字段**：时间、行为类型、玩家名、XUID、维度、**坐标**、**主手物品**（`物品IDx数量`，空手为 `empty`）、`detail`（如方块类型、死亡原因、实体类型、进服是否新玩家等）
- **已挂钩行为**：进服 / 离服、方块破坏与放置、对方块交互与无方块交互、与实体交互、玩家死亡（含死因原始字符串）；关闭开关时不写盘

### 💰 银行经济系统
- 完整的货币管理系统，**金钱精确到分**（float 存储，两位小数）
- 玩家余额存储和查询
- **升级转账功能** - 两步式转账流程，先选择玩家再输入金额，支持小数金额
- 富豪榜排行系统
- 管理员金钱操作命令
- 实时余额变动提醒
- **财富榜首富头衔（v0.0.4.0）** - 配置 `RICHEST_TITLE_NAME`（默认「首富」）、传奇稀有度；金钱变动后自动刷新财富榜第一；若首富易主则撤销旧头衔并授予新首富；可在 **OP 面板 → 经济管理 → 经济参数配置** 中修改

### 🏠 领地管理系统
- **三维领地** - 按 min/max X/Y/Z 圈地，按体积计价；粒子显示立方体边界（与「进入领地」时边界粒子一致）
- **创建领地流程** - 菜单「创建新领地」后按提示 **交互四个方块**：水平矩形两角（取 X/Z）→ 最低 Y → 最高 Y，完成后进入 **购买确认面板**（可再次播放边界粒子、用六个整数框修改 min/max X/Y/Z、确认购买）；亦可用 **「手动输入六向坐标」** 或保留 **`/land pos1`、`/land pos2`（同 `/landpos1`/`/landpos2`）、`/land buy`（同 `/landbuy`）** 快捷选点
- **待购面板** - 购买前可随时用 **`/landbuy`（或 `/land buy`）** 重新打开同一面板；`/landbuy` 为打开面板而非直接扣款
- **领地保护机制**（防止破坏/建造/方块互动）
- **免费领地格子系统** - 新玩家可获得免费格子，购买领地时自动减免费用
- **领地授权系统** - 可将领地权限授权给其他玩家
- **子领地系统** - 领地主人可在领地内创建子领地并授权他人；子领地为三维、不可重叠、不可超出父领地；交互时先判子领地权限再判父领地
- **公共领地「允许圈私人领地」** - 公共领地可开启后，玩家可在其内购买私人领地；同一位置优先按私人领地权限判定
- **领地移交功能** - 可将领地转移给其他玩家
- **私人领地上架出售（v0.0.7.4）** - 领地详情中 **「出售领地（上架/改价/下架）」**：主人可设置正数标价并上架；其他玩家 **进入** 该私人领地时（非主人）在原有进入提示与边界粒子后，会收到 **购买表单**（领地名、标价、当前主人、购买/关闭）。购买时扣买家款、过户给买家、`owner_paid_money` 记为成交价，**清空授权列表**；卖家在线会收到成交通知。数据库 `lands` 表新增 **`for_sale`**、**`sale_price`**（旧库启动时自动 `ALTER`）。**公共领地 / 公会领地** 不适用此流程；若向卖家入账失败会尝试 **回滚过户并退款**（极端失败会提示联系管理员）
- **私人领地成交增值税（v0.0.7.6 文档化）** - 配置 **`LAND_SALE_VAT_RATE`**（`core_setting.yml`，默认 `0.1` 即 10%，取值 **0～1**；**`0` 关闭**）。成交时 **买家按标价全额付款**；**卖家实收** = 成交价 − 增值税额。**税基（溢价）** = `max(0, 成交价 − 过户前 owner_paid_money)`；**增值税额** = 税基 × 税率（金额按分四舍五入）。平价或低于买入价成交不产生增值税。卖家在线提示中含成交价、增值税、实收（语言键 **`LAND_SALE_BUY_SUCCESS_SELLER`** 等，见 `ZH-CN.txt`）。**OP 重载配置** 后刷新税率
- **爆炸保护设置** - 可单独控制领地内是否允许爆炸
- **方块互动开放设置** - 可设置领地对所有人开放方块互动（如开箱子、按按钮等）
- **生物保护系统** - 可控制领地内是否允许与生物交互和攻击生物
- **展示框权限设置** - 可禁止领地对展示框/发光展示框及各材质展示架的互动与破坏（默认禁止，防止他人取物）；**关闭展示框权限时**，领地主人、授权玩家、子领地权限持有者及（若开启「公会成员可交互」）同公会成员 **仍可** 操作展示框/架，不受此项拦截
- **领地范围重设（v0.0.7.5+）** - 私人/公会领地在 **我的领地 → 领地详情 →「重设领地范围」**；公共领地在 **OP 领地管理 → 领地详情 →「重设公共领地范围」**。流程与 **新建领地相同**（四角选点或手动改坐标），确认面板显示 **原/新体积与补差价或退差价**：私人领地扩大时优先消耗 **免费领地格** 再按 `LAND_PRICE` 补款，缩小按 `LAND_SELL_REFUND_COEFFICIENT` 退款并调整 `owner_paid_money`；**OP 改私人领地** 不扣款；**公会领地** 仅会长/管理者，扩大消耗 **公会公共贡献点**，缩小退还公共池；**公共领地** 仅 OP、不扣款。确认后更新 `lands` 边界、**重建 chunk 索引**（`land_id` 不变），传送点若超出新范围会 **自动移到新范围中心（Y 取新 min_y）**；**上架出售中** 不可重设；**子领地** 若超出新长方体范围会阻止并提示先调整子领地。文案键见 `dist/ARCCore/ZH-CN.txt` 中 `LAND_RESIZE_*`
- **全局禁用方块（v0.0.6.0）** - 新增 `DISABLED_BLOCKS` 配置；列表内方块对非 OP 玩家禁止放置与交互，OP 跳过检查
- **领地尺寸限制** - 可配置领地最小尺寸，防止创建过小的领地（默认长宽必须都大于5格）
- **领地信息查看功能** - 可查看当前位置的详细领地信息
- **领地边界可视化** - 用粒子效果显示领地边界范围
- **创建领地重叠提示** - 与已有领地重叠时提示与哪些领地重叠
- 领地传送点设置和管理
- 领地重命名功能
- 可配置的领地价格和最小距离
- 智能传送命令生成（自动处理包含空格的玩家名）

### 🎯 成就系统（v0.0.5.0，数据模型 v0.0.7.1）
- **模块**：`AchievementSystem.py`、`achievement_conditions.py`，与 **OP 面板 → 成就管理** 联动；达成条件后调用头衔解锁并发放在头衔定义中配置的奖励（金钱/物品）
- **可配置的击杀成就**：支持 **单类生物**（`kill_entity`，`target_id` 为 `*` 表示任意生物总击杀）、**多类生物击杀数相加**（`kill_entity_sum`）；击杀统计随事件实时写入 **`player_achievement_stats`**
- **数据（v0.0.7.1）**：同一张表 **`player_achievement_stats`** 中：
  - **进度**：`stat_key` 为 `kill_total`、`kill:minecraft:zombie` 等，`count` 为累计击杀
  - **完成标记**：`stat_key` 为 **`ach_unlock:<unlock_title>`**，`count ≥ 1` 表示该成就已在逻辑上记为完成（与头衔表配合，见下条）；**不再使用**表 **`player_achievement_unlocked`**
  - **判定**：玩家是否算「已完成某成就」= 已有对应 **`ach_unlock:`** 记录 **或** 已在 **`player_title_unlock_time`** 中解锁同名头衔（例如 OP 直发头衔）
  - **升级补全**：插件加载时会对「在统计表或头衔表中出现过的玩家」做一次 **幂等补全**：若无 `ach_unlock:` 但已拥有头衔或当前进度已满足条件，则静默写入完成标记，**避免升级后重复走解锁、重复发奖**
- **定义文件**：**`plugins/ARCCore/achievements.json`**；旧版 SQLite 表 **`achievement_definitions`** 仍可在启动时迁移进 JSON；**`achievement_meta`** 等与 JSON 重复的中间表已移除
- **默认击杀成就包**：OP 可一键写入内置击杀类头衔与条件（与文档/内置表一致）
- **说明**：**`DEFAULT_TITLE`** 仅表示「进服即送解锁」的默认头衔，**不应**列入需成就解锁的头衔；一键应用默认击杀成就后 **不会** 再把这些头衔写入 `DEFAULT_TITLE`（避免进服误送全套解锁）

### 📅 每日签到（v0.0.4.0 起，v0.0.4.2 / v0.0.6.0 增强）
- **可签到条件**：`player_basic_info.last_checkin_date` 与服务器本地日期（YYYY-MM-DD）不同即可在主菜单 **每日签到**
- **连续签到奖励（v0.0.6.0）**：支持按连续签到天数发放递增金钱奖励（可配置步长）
- **前几名签到奖励（v0.0.6.0）**：支持配置每日前 X 名签到玩家的额外金钱与额外物品奖励
- **奖励**：配置存款 + 按权重 **不放回** 随机物品；每日抽取条数在 **`CHECKIN_REWARD_PICK_MIN`～`CHECKIN_REWARD_PICK_MAX`** 之间随机（未配置区间时沿用 `CHECKIN_REWARD_PICK_COUNT`）
- **统计与排行数据（v0.0.4.2）**：`total_checkin_count` 累计签到次数、`last_checkin_at`（ISO8601）记录最近一次签到时刻，用于 **当日签到先后** 与 **累计签到榜** 排序
- **全服广播（v0.0.4.2）**：签到成功后广播完成提示；**今日签到先后**（当日人数 ≤10 时列出全员；>10 时广播「最早前 10」与「最晚前 10」两段）；**累计签到榜前 10**；聊天中 **按行发送**，避免名次挤成一行难读
- **配置**：`CHECKIN_DAILY_MONEY`、`CHECKIN_REWARD_LIST`（JSON 数组，每项 `[物品ID, 数量, 权重]`）；**OP 面板 → 签到配置**（总览 + 存款/条数表单 + 奖励列表管理，见 OP 面板说明）
- **配置键速览（v0.0.6.0）**：
  - `CHECKIN_CONTINUOUS_DAYS_MONEY_INCREMENT`：连续签到金钱递增步长（连续第 N 天在基础金额上额外加 `(N-1)*步长`）
  - `CHECKIN_TOP_RANK_LIMIT`：每日前 X 名签到人数（设为 `0` 即关闭前几名奖励）
  - `CHECKIN_TOP_RANK_BONUS_MONEY_STEP`：前 X 名额外金钱步长（名次越靠前奖励越高）
  - `CHECKIN_TOP_RANK_BONUS_ITEM_COUNT`：前 X 名额外物品条数（每位前 X 名玩家额外获得的条目数）
  - `CHECKIN_REWARD_PICK_MIN` / `CHECKIN_REWARD_PICK_MAX`：每日随机抽取物品奖励条数区间
- **签到公会贡献点（v0.0.7.3）**：`CHECKIN_GUILD_CONTRIBUTION_POINTS`（默认 `10`）— 签到成功时，若玩家 **已加入公会**，则按 `GuildSystem.add_contribution_by_xuid` 同时增加 **私人贡献点** 与 **公会公共贡献点**；未加入公会则跳过（不报错）。设为 `0` 可关闭。可在 **OP 面板 → 签到配置 → 配置存款与随机条数** 表单最后一项编辑，或直接改 `core_setting.yml`

### 💀 击杀生物金钱奖励（v0.0.4.0）
- 独立配置文件 **`kill_reward.txt`**（与 `core_setting.yml` 同级目录），格式：`minecraft:creeper=10`（击杀一个苦力怕获得 10 元）
- 首次击杀某种生物且配置中无该类型时，自动追加 `类型ID=0`，不提示；仅当金额 **> 0** 时提示「击杀了 xx 获得 xx 元」
- 显示名优先通过 **`entity_display_name.txt`** 中 `entity.minecraft.xxx.name` 等键解析（`EntityDisplayNameManager.get_display_name_for_entity_type`）
- **击杀 → 公会贡献点（v0.0.7.5）**：`KILL_REWARD_GUILD_CONTRIB_RATIO`（默认 `0`）— 玩家在已加入公会时，每次成功扣发击杀金钱奖励后按 `floor(reward * ratio)` 额外获得公会贡献点；同步累加 **私人贡献点** 与 **公会公共贡献点**。例如 `kill_reward.txt` 配置 `minecraft:creeper=10` 且比例为 `0.5`，则击杀苦力怕在获得 10 元的同时获得 5 公会贡献点。比例 `0` 或 `floor(reward*ratio) <= 0` 或玩家未加入公会时静默跳过

### 📍 传送系统
- **私人传送点 (Home)** - 玩家可设置多个传送点
- **公共传送点 (Warp)** - 管理员可创建公共传送点
- **跨服传送（v0.0.6.0）** - 数据库维护跨服目标；`/connecttoserver` **无参数**时打开跨服目标 **选择面板**，有参数时按名称执行传送；控制台/命令方块执行时可通过发送者名称解析在线玩家（与下列命令解析方式一致）
- **玩家传送请求 (TPA/TPHERE)** - 玩家间传送请求；**被请求方收到请求时自动弹出表单**（v0.0.4.2），可直接同意或拒绝，不再仅依赖聊天提示
- **死亡回归系统** - 玩家死亡后可传送回死亡地点；**死亡坐标在同一次服务器运行期间保持**（退出游戏不再清空；实际传送成功后仍会清除记录）
- **随机传送系统 (v0.0.1.12新增)** - 随机传送到指定范围内，自动附加缓降（羽落）效果（**30 秒**，v0.0.4.1 起；此前为 10 秒）
- **传送付费系统 (v0.0.1.12新增)** - 每种传送类型可独立配置收费，支持余额检查
- **跨维度传送支持** - 支持在主世界、下界、末地之间自由传送
- **智能维度处理** - 自动使用 `execute in <dimension> run tp` 指令格式
- 传送倒计时提示

### 💴 商店系统
- **ushop插件适配** ，如果你安装了 `ushop` ，弧光核心的主菜单中会有 "商店" 按钮
- **arc_button_shop适配** - 新增对arc_button_shop玩家按钮商店的集成支持，可通过主菜单直接访问按钮商店功能，提升玩家开店体验

### 📈 股票系统
- **up_and_down插件适配** - 新增对up_and_down股票插件的集成支持
- 在主菜单中新增"证券交易所"按钮，玩家可直接访问股票交易功能
- 提供便捷的股票系统入口  - `{date}` - 当前日期 (年-月-日)
  - `{time}` - 当前时间 (小时:分钟)
  - `{online_player_number}` - 当前在线玩家数
- 可配置公告发送间隔
- 从 `broadcast.txt` 文件读取公告内容

### 🧹 清道夫系统 (v0.0.1.2新增)
- 定时自动清理掉落物
- 可配置清理时间间隔
- 清理前10秒倒计时警告
- 清理过程状态提示
- 可通过配置开启/关闭

### 🎊 新人欢迎系统 (v0.0.1.4新增)
- **新玩家自动识别** - 基于数据库记录智能判断新玩家
- **自定义欢迎消息** - 通过 `newbie_welcome.txt` 文件设置欢迎内容
- **自动执行指令** - 通过 `newbie_commands.txt` 文件配置新人自动执行的指令
- **动态玩家名替换** - 指令中的 `{player}` 占位符自动替换为新玩家名称
- **数据库自动初始化** - 新玩家加入时自动创建基础数据和经济账户
- **初始资金设置** - 新玩家自动获得配置中设定的初始金钱
- **UTF-8 编码支持** - 完全支持中文和特殊字符
- **错误处理机制** - 文件读取失败不影响插件正常运行

### 🔐 OP状态追踪系统 (v0.0.1.4新增)
- **OP状态持久化** - 在数据库中记录玩家的OP状态
- **离线状态查询** - 即使玩家离线也能查询其OP状态
- **自动状态同步** - 玩家加入时自动检查并更新OP状态
- **数据库自动升级** - 自动为旧数据库添加OP状态字段
- **金钱排行榜隐藏** - 可配置在金钱排行榜中隐藏OP玩家

### 🛡️ 出生点保护
- 可配置的出生点保护范围
- 防止玩家在出生点附近建筑/破坏
- 多维度出生点支持

### ⚙️ OP 管理面板（v0.0.4.0 整理）
- **主菜单顺序**（自上而下）：重载配置 → **工具** → **经济管理** → 领地管理 → 传送管理 → 成就管理 → 签到配置 → 邀请奖励配置 → 头衔管理 → 返回
- **工具**：切换游戏模式、清除掉落物、记录坐标 1/2、调试模式、执行命令（`@p1`/`@p2`、留空重复上次命令）
- **经济管理**（原「金钱管理」）：**增减在线玩家存款**；**经济参数配置** 写入 `PLAYER_INIT_MONEY_NUM`、`HIDE_OP_IN_MONEY_RANKING`、`RICHEST_TITLE_NAME`（与 `core_setting.yml` 玩家经济段一致）
- **领地管理**：管理所有领地、管理脚下领地、重建领地区块映射；**公共领地** 详情内可 **重设公共领地范围**（与玩家重设流程一致，不扣款）（返回统一回到领地管理子菜单）
- **传送管理**：**管理公共传送点**（创建/删除 Warp）；**传送参数配置**（`MAX_PLAYER_HOME_NUM`、随机传送开关/中心/半径、各类传送费用等，与 `core_setting.yml` 传送段一致）
- 邀请奖励配置、**签到配置**（v0.0.4.2：总览展示当前存款/随机条数区间/奖励条目数；**配置存款与随机条数** 弹窗表单，v0.0.7.3 起含 **每日签到公会贡献点**；**配置物品奖励列表** 支持按条目进入编辑/删除与新增）、头衔管理、成就管理
- **重载配置** - 重载 `core_setting`、广播、语言、**entity_display_name.txt**、**kill_reward.txt** 等
- **调试模式**（v0.0.3.0）：开启后，在方块破坏/放置、方块交互、生物攻击、生物交互时向该 OP 发送聊天调试消息（事件类型、目标、维度、位置）

### 🏷️ 头衔系统（v0.0.3.0，表结构 v0.0.7.1）
- **聊天头衔展示** - 远古 QQ 风格：首行 `[头衔]玩家名(年.月.日-时:分)：`，下一行消息内容；`[头衔]玩家名` 加粗并按稀有度上色（MC 格式码 §l、§r、§f/§9/§d/§6/§c），「玩家」前缀可在语言文件中配置（如英文 `Player-`）
- **数据（v0.0.7.1）** - 玩家解锁时间仅存 **`player_title_unlock_time`**（`xuid`、`title`、`unlocked_at`）；已移除仅作历史兼容的 **`player_title_extra`**。若旧库中仍有该表可手动 `DROP TABLE IF EXISTS player_title_extra;`
- **头衔属性** - 每个头衔支持：**稀有度**（普通/稀有/史诗/传奇/神话，对应白/蓝/紫/橙/红）、**头衔介绍**、**解锁时间**（解锁时记录，默认头衔在首次进服或首次获得时记录；已进服但尚未有默认头衔的玩家在下一次进服时补发并记录时间）、**解锁奖励**（金钱 + 物品列表「物品ID 数量」）
- **默认头衔** - 配置 `DEFAULT_TITLE`（逗号分隔），**进服时**为每位玩家写入解锁记录（与成就无关）；默认稀有度为普通，介绍与奖励为空，OP 可在头衔属性管理中修改。
- **OP 专属头衔** - 配置 `OP_TITLE`（单个），仅 OP 拥有；非 OP 进服时若正佩戴该头衔则自动解除
- **头衔管理（玩家）** - 主菜单「我的信息」→「头衔管理」：选择佩戴/不佩戴
- **OP 头衔管理** - OP 面板→「头衔管理」：**头衔属性管理**（编辑各头衔的稀有度、介绍、解锁奖励）、**创建新头衔**（名称 + 稀有度 + 介绍 + 奖励）、**给所有玩家添加头衔**（选择已有头衔，为当前数据库内所有玩家解锁，新人不会自动获得）、**给玩家单独添加头衔**（先输入玩家名，再选择要添加的头衔）；解锁时若玩家在线则发放该头衔的解锁奖励（金钱与物品）
- **API** - `api_unlock_title(player, title: str)` 为玩家解锁头衔并发放解锁奖励（若配置了奖励）
- **解锁头衔自动佩戴（v0.0.4.0）** - 通过 `api_unlock_title` 等途径解锁头衔时，若当前未佩戴任何头衔，则自动佩戴新解锁的头衔

### 🏰 公会系统（v0.0.7.0；v0.0.7.2 拓展规模与贡献点；v0.0.7.3 浏览与入会审批）
- **模块**：`GuildSystem.py`；表 **`guilds`**、**`guild_members`**（每名玩家最多归属一个公会）；**`guild_invites`** 表仍保留，供历史数据或旧版待处理邀请读取，**当前版本的在线邀请不再写入该表**
- **入口**：主菜单 **公会**，或 **`/arc guild`**（需已登录）
- **创建公会**：消耗可配置 **`GUILD_CREATE_COST`**（默认 `100000`）；公会名唯一、可选简介；创建者即为 **会长（owner）**
- **职级**：**会长**、**管理者（manager）**、**成员（member）** — 会长可踢管理者与成员、变更职级、解散公会；管理者可邀请与踢出普通成员；成员可退出
- **在线邀请（v0.0.7.0）**：**仅邀请当前在线且未加入任何公会的玩家** — 邀请方在列表中点选玩家名，被邀请方 **立即弹出接受/拒绝表单**，确认后直接写入成员表，**无需入库待处理邀请**
- **公会规模（v0.0.7.2）**：每个公会有 **小型 / 中型 / 大型** 三档规模等级，新建公会默认 **小型**；各档成员人数上限可在 `core_setting.yml` 中通过 **`GUILD_SIZE_SMALL_MAX`**、**`GUILD_SIZE_MEDIUM_MAX`**、**`GUILD_SIZE_LARGE_MAX`** 配置（默认 10 / 20 / 40）。邀请与接受邀请均会校验当前规模容量，超过上限直接报 **`GUILD_FULL`** 错误
- **公会规模升级（v0.0.7.2）**：会长 / 管理者可在 **我的公会 → 升级公会规模** 中花费 **公会公共贡献点** 升级；升级消耗在 `core_setting.yml` 中通过 **`GUILD_UPGRADE_TO_MEDIUM_COST`**（默认 `10000`）、**`GUILD_UPGRADE_TO_LARGE_COST`**（默认 `100000`）配置；仅可由低向高升级（small→medium / large、medium→large）；OP 在 **OP 面板 → 公会管理** 中可绕开贡献点直接升级或降级规模（降级时若当前人数已超过目标上限会被拒绝，且不会退还任何贡献点）；规模变更后会自动刷新该公会全体在线成员的头顶名（颜色随之变化）
- **公会改名（v0.0.7.2）**：会长可在 **我的公会 → 公会改名** 中输入新公会名（与创建公会一致：自动剥离 §X 颜色码、限长 32、去首尾空白）；新名 **不能与当前公会同名（去色后比较）**，**不能与其它公会重名**；改名费用由 `core_setting.yml` 中 **`GUILD_RENAME_COST`** 配置（默认 `0` 即免费），费用 > 0 时改名失败会自动回滚扣款；改名成功后立即刷新全体在线成员的头顶名
- **公会名颜色与防注入（v0.0.7.2）**：聊天、玩家头顶 `name_tag`、`get_player_name_by_xuid(..., True)` 等展示名中的 `[公会名]` 前缀会按公会规模上色 — **小型 §h / 中型 §s / 大型 §p**（可在语言文件中通过 `GUILD_SIZE_TIER_COLOR_SMALL / MEDIUM / LARGE` 覆盖）。`GuildSystem` 在创建公会、改名、按名查公会、读取公会、列出待处理邀请等所有出口处都会通过正则 **统一剥离 §X 格式码**（含残留的孤立 §），即便玩家在公会名中尝试粘贴 MC 颜色码也会被消除；旧库内若残留过格式码也会在读取时自动清洗。**创建 / 改名表单提交后**：若玩家输入的公会名包含 §X，会先静默剥离再入库，并通过 `GUILD_NAME_COLOR_STRIPPED_HINT` 向玩家发出「颜色码已被自动移除」的提示；若输入仅由颜色码组成，会按 `GUILD_INVALID_NAME` 拒绝并附带同一提示
- **公会贡献点（v0.0.7.2）**：
  - **私人公会贡献点**：保存在 `guild_members.contribution`；玩家通过 **API** 或 **每日签到（v0.0.7.3，见签到章节）** 等途径累加；**退出 / 被踢 / 公会解散** 时该玩家私人贡献点随成员行删除而 **清零**
  - **公共公会贡献点**：保存在 `guilds.total_contribution`；玩家每次获得私人贡献点时同步累加到所在公会公共值；**成员退出/被踢时公共值不会减少**（仅在公会解散时随公会行一并销毁）；当前 UI 中可被「升级公会规模」消耗
  - 玩家加入新公会时私人贡献点从 0 开始；新公会的公共贡献点也从 0 开始
  - **对外插件接口（查询 + 发放）**：**发放**请使用 `api_add_guild_contribution(player_name, points)`（私人与公共同时 +points，在线会提示）；**查询**可使用 `api_get_player_guild_contribution`（私人）、`api_get_guild_total_contribution_by_player`（所在公会公共），或一次性读取 `api_get_player_guild_info`（含两种贡献与规模等）。详见下方「公会系统 API」与示例代码
  - **底层消费接口**：`GuildSystem.consume_guild_contribution(guild_id, points)`（仅扣减公共值，不影响私人值），供领地等系统消耗公共贡献点
- **全部公会浏览与入会（v0.0.7.3）**：主菜单 **公会 → 查看全部公会** — 列表按 **规模等级降序、同规模按公共贡献点降序**；支持 **按名称搜索**、分页；点选公会仅 **预览**（名称、简介、规模、人数/上限、公共贡献、入会说明）；**无公会** 玩家可 **申请加入 / 加入**（取决于 **入会审核**）；**已是本会成员** 仅提供 **我的公会** 跳转。会长 / 管理者在 **我的公会 → 入会审核设置** 中开关审核，在 **入会申请** 中处理待审。相关数据表：`guild_join_requests`、`guilds.join_requires_approval`
- **跨服同步**：在 `core_setting.yml` 中配置 **`GUILD_DATABASE_PATH`** 为各服可访问的 **同一 SQLite 文件路径**（留空则使用 `DATABASE_PATH` 主库），与 `PLAYER_DATABASE_PATH` 等跨服库配置方式一致
- **展示名统一**：聊天、玩家头顶 **`name_tag`**、`get_player_name_by_xuid(..., return_with_title=True)` 等为 **`[公会前缀][头衔]玩家名`**：有公会时前缀为带 MC 颜色码的 **`[公会名]`**（与「普通」稀有度头衔同色）；无公会时为 **`§f[无公会]§r`**（白色），再接头衔段与游戏名
- **数据库平滑升级**：插件加载时若旧库 `guilds` / `guild_members` 缺少 `size_tier` / `total_contribution` / `contribution` 列，会自动 `ALTER TABLE` 补齐（默认值：`size_tier='small'`、其余为 `0`），无需手动迁移

### 🔌 插件 API 系统
- **经济系统 API** - 完整的金钱管理接口
- **头衔系统 API**（v0.0.3.0）- `plugin.api_unlock_title(player, title)` 为玩家解锁头衔
- **新手引导 API** - `plugin.api_get_newbie_guide_text()` 返回 `newbie_welcome.txt` 全文（供大模型聊天等插件使用）
- **线程安全设计** - 支持多插件并发调用
- **错误处理机制** - 自动处理异常情况
- **详细文档支持** - 提供完整的使用示例
- **未来扩展计划** - 领地、传送等系统API

## 命令列表

| 命令 | 描述 | 权限 | 用法 |
|------|------|------|------|
| `/arc` | 打开 ARC Core 主菜单 | 默认 | `/arc` |
| `/arc op` | 直接打开 OP 面板（仅 OP） | OP | `/arc op` |
| `/arc land` | 直接打开领地系统菜单 | 默认 | `/arc land` |
| `/arc tp` | 直接打开传送系统菜单 | 默认 | `/arc tp` |
| `/arc bank` | 直接打开银行菜单 | 默认 | `/arc bank` |
| `/arc guild` | 直接打开公会菜单 | 默认 | `/arc guild` |
| `/pos1` | 记录当前坐标为坐标 1（OP 快捷，对应 OP 面板记录坐标 1） | OP | `/pos1` |
| `/pos2` | 记录当前坐标为坐标 2 并打开 OP 面板（OP 快捷） | OP | `/pos2` |
| `/updatespawnpos` | 更新当前维度的出生点位置 | OP | `/updatespawnpos` |
| `/suicide` | 自杀命令 | 默认 | `/suicide` |
| `/spawn` | 传送到出生点 | 默认 | `/spawn` |
| `/land pos1` | 领地选点 1（等价 `/landpos1`，记录当前站立方块坐标） | 默认 | `/land pos1` |
| `/land pos2` | 领地选点 2 并打开待购面板（等价 `/landpos2`） | 默认 | `/land pos2` |
| `/land buy` | 打开待购领地购买面板（等价 `/landbuy`） | 默认 | `/land buy` |
| `/landpos1` | 同上，旧写法保留 | 默认 | `/landpos1` |
| `/landpos2` | 同上，旧写法保留 | 默认 | `/landpos2` |
| `/landbuy` | 同上，旧写法保留 | 默认 | `/landbuy` |
| `/connecttoserver` | 无参数时打开跨服目标列表；有参数时按名称传送 | 默认 | `/connecttoserver` 或 `/connecttoserver <名称>` |

## 📂 文件结构

插件会在 `plugins/ARCCore/` 目录下创建以下文件：

- `core_setting.yml` - 主要配置文件
- `broadcast.txt` - 公告消息文件
- `{语言代码}.txt` - 语言文件 (如 ZH-CN.txt)
- `entity_display_name.txt` - 生物显示名翻译（v0.0.3.1+，死亡播报等）
- `kill_reward.txt` - 击杀生物金钱奖励（v0.0.4.0，每行 `类型ID=金额`）
- `achievements.json` - 成就定义（v0.0.5.0+，击杀条件等与 OP 面板「成就管理」同步）
- SQLite 数据库文件

## ⚙️ 配置文件

### core_setting.yml - 主要配置选项

```yaml
# 基础设置
DEFAULT_LANGUAGE_CODE=ZH-CN          # 默认语言
DATABASE_PATH=ARCCore.db             # 数据库文件路径
PLAYER_INIT_MONEY_NUM=10000          # 玩家初始金钱

# 出生点保护
IF_PROTECT_SPAWN=True                # 是否保护出生点
SPAWN_PROTECT_RANGE=8                # 出生点保护范围

# 领地系统
MIN_LAND_DISTANCE=1                  # 领地最小距离
LAND_PRICE=100                       # 领地价格 (每格)
LAND_SELL_REFUND_COEFFICIENT=0.9     # 领地出售退款系数
LAND_MIN_SIZE=5                      # 领地最小尺寸 (长宽必须都大于此值)
LAND_SALE_VAT_RATE=0.1               # 私人领地上架成交增值税：对 (成交价−过户前owner_paid_money) 的溢价按比例征税，从卖家实收扣除；0=关闭

# 传送系统
MAX_PLAYER_HOME_NUM=5                # 玩家最大家园数量

# 随机传送配置 (v0.0.1.12新增)
ENABLE_RANDOM_TELEPORT=True          # 是否启用随机传送功能
RANDOM_TELEPORT_CENTER_X=0           # 随机传送中心点X坐标
RANDOM_TELEPORT_CENTER_Z=0           # 随机传送中心点Z坐标
RANDOM_TELEPORT_RADIUS=5000          # 随机传送半径 (格)

# 传送收费配置 (v0.0.1.12新增，0表示免费)
TELEPORT_COST_PUBLIC_WARP=0          # 公共传送点费用
TELEPORT_COST_HOME=0                 # 私人传送点费用
TELEPORT_COST_LAND=0                 # 领地传送费用
TELEPORT_COST_DEATH_LOCATION=0       # 死亡地点传送费用
TELEPORT_COST_RANDOM=100             # 随机传送费用
TELEPORT_COST_PLAYER=50              # 玩家互传费用 (TPA/TPHERE)

# 公告系统
BROADCAST_INTERVAL=180               # 公告发送间隔 (秒)

# 清道夫系统
ENABLE_CLEANER=True                  # 是否启用清道夫
CLEANER_INTERVAL=600                 # 清理间隔 (秒)

# 天眼系统（Sky Eye，v0.0.7.6）：玩家行为审计日志 plugins/ARCCore/sky_eye/YYYYMMDD.txt
ENABLE_SKY_EYE=False                 # 是否启用天眼日志
SKY_EYE_MAX_RETENTION_DAYS=7         # 按自然日保留天数，0=不自动删旧文件

# 新人欢迎系统和OP设置（部分项也可在 OP 面板「经济管理」中修改）
HIDE_OP_IN_MONEY_RANKING=True        # 金钱排行榜是否隐藏OP玩家

# 首富头衔（v0.0.4.0，亦可 OP 经济管理）
RICHEST_TITLE_NAME=首富

# 领地系统
DEFAULT_FREE_LAND_BLOCKS=100         # 新玩家默认免费领地格子数

# 公共领地白名单保护生物 (v0.0.2.1，逗号分隔)
PUBLIC_LAND_PROTECTED_ENTITIES=minecraft:villager,minecraft:iron_golem,minecraft:snow_golem

# 强制登录 (v0.0.3.0)：为 true 时进服强制打开 /arc，关闭登录/注册页未正确输入密码时再次强制打开
FORCE_LOGIN=False

# 头衔系统 (v0.0.3.0)：逗号分隔为默认头衔；OP_TITLE 仅一个，仅 OP 拥有。对应头衔的稀有度、介绍、解锁奖励可在 OP 面板→头衔管理→头衔属性管理中编辑，也可创建新头衔
DEFAULT_TITLE=创始玩家, 核心成员, ARC Player
OP_TITLE=管理员

# 公会系统 (v0.0.7.0)：GUILD_DATABASE_PATH 留空则公会数据在 DATABASE_PATH 主库；多服填写同一文件路径可共享公会
GUILD_DATABASE_PATH=
GUILD_CREATE_COST=100000
# 公会规模 (v0.0.7.2)：每个公会有 small / medium / large 三档；下列三个值为各档成员人数上限（含会长）
GUILD_SIZE_SMALL_MAX=10
GUILD_SIZE_MEDIUM_MAX=20
GUILD_SIZE_LARGE_MAX=40
# 公会规模升级所消耗的公会公共贡献点（会长 / 管理者可在「我的公会 → 升级公会规模」中花费）
GUILD_UPGRADE_TO_MEDIUM_COST=10000
GUILD_UPGRADE_TO_LARGE_COST=100000
# 会长改名公会需支付的金钱（0 表示免费）
GUILD_RENAME_COST=0
```

### broadcast.txt - 公告消息文件

每行一条公告，支持占位符：

```txt
欢迎来到ARC弧光基岩服务器！你可以在聊天框发送/arc命令打开服务器操作菜单
请遵守服务器规则，文明游戏，共建和谐游戏环境！
现在是北京时间{date} {time}，请注意休息，爱护眼睛你我做起。
当前服务器在线人数{online_player_number}，求生者们请互帮互助
```

### newbie_welcome.txt - 新人欢迎消息文件 (v0.0.1.4新增)

新玩家第一次加入服务器时显示的欢迎消息：

```txt
欢迎来到ARC弧光大陆服务器！这里是一个恐怖+种田+模拟生活的多模组服务器，拥有丰富的玩法和特色系统！在聊天框输入/arc命令即可打开服务器操作菜单，进行购物、传送、领地管理等操作。

```

### newbie_commands.txt - 新人自动执行指令文件 (v0.0.1.4新增)

新玩家第一次加入服务器时自动执行的指令，每行一个指令：

```txt
# 新人指令文件
# 每行一个指令，{player} 会被替换为玩家名称
# 示例：
gamemode 0 {player}
# clear {player}
give {player} minecraft:bread 5
give {player} krep:m1911
give {player} krep:acp45 42
```

#### 新人指令文件说明
- **注释支持**: 以 `#` 开头的行为注释，不会执行
- **占位符替换**: `{player}` 会自动替换为新玩家的名称
- **指令格式**: 使用标准的Minecraft指令格式，无需添加 `/` 前缀
- **错误处理**: 单个指令执行失败不会影响其他指令

### 支持的占位符

| 占位符 | 描述 | 示例输出 |
|--------|------|----------|
| `{date}` | 当前日期 | `2024-01-15` |
| `{time}` | 当前时间 | `14:30` |
| `{online_player_number}` | 在线玩家数 | `5` |
| `{player}` | 玩家名称 (仅新人指令文件) | `PlayerName` |

## 安装说明

1. 确保您的服务器运行 EndStone 框架
2. 将插件文件放入服务器的 `plugins` 目录
3. 重启服务器
4. 插件会自动创建必要的配置文件和数据库

## 依赖要求

- EndStone 框架 (API 版本 0.7+)
- Python 3.x
- SQLite3 (通常内置于 Python)

## 🎮 使用指南

### 快速开始
1. 玩家进入服务器后，使用 `/arc` 命令打开主菜单
2. 首次使用需要注册账户并设置密码
3. 登录后可使用各种功能：银行、领地、传送等

### 功能操作指南
- **银行系统**: 在主菜单点击"银行"进行转账、查看余额等
  - **转账操作**: 使用全新的两步式转账流程，先从在线玩家列表中选择目标玩家，再输入转账金额
- **领地系统**: 
  - 推荐：主菜单 **领地 → 创建新领地**，按提示交互四个方块；或使用 **`/land pos1` / `/land pos2`**（或旧写法 `/landpos1`、`/landpos2`）在对角两点定范围，再用 **`/land buy`**（或 `/landbuy`）打开购买面板
  - 领地长宽必须都大于配置的最小尺寸（默认 5 格）；**`/pos1` `/pos2` 为 OP 记录坐标指令，与圈地无关**
  - 新玩家享有免费领地格子，购买时会自动使用免费格子抵扣费用
  - 在领地详情中可设置爆炸保护、方块互动开放、展示框权限等高级选项；**重设领地范围** 与新建圈地流程一致，确认前可预览粒子、改坐标
  - 支持将领地权限授权给其他玩家或完全移交领地
- **传送系统**: 在主菜单的"传送系统"中管理传送点和发送传送请求
- **公告查看**: 定时播放的公告会自动显示当前时间和在线人数
- **新人欢迎系统**: 
  - 编辑 `newbie_welcome.txt` 自定义新玩家欢迎消息
  - 编辑 `newbie_commands.txt` 配置新玩家自动执行的指令
  - 使用 `{player}` 占位符在指令中引用玩家名称
  - 新玩家首次加入时自动获得初始资金和执行欢迎流程

## 🗃️ 数据存储

插件使用 SQLite 数据库存储以下数据：
- **玩家信息**: 用户名、XUID、密码哈希、OP状态、剩余免费领地格子数、邀请人(inviter_xuid)、待领取邀请奖励次数、注册时间
- **经济数据**: 玩家余额、交易记录
- **领地信息**: 领地坐标、拥有者、传送点、共享用户、爆炸保护设置、方块互动开放设置、生物保护设置、展示框权限设置
- **传送点**: 私人传送点、公共传送点坐标信息
- **成就（v0.0.7.1）**: **`player_achievement_stats`** — 击杀进度（`kill_total`、`kill:...`）与完成标记（**`ach_unlock:<unlock_title>`**）；**`achievement_conditions`** 仅用于极旧数据向 JSON 迁移；定义以 **`plugins/ARCCore/achievements.json`** 为准
- **服务器配置**: 出生点坐标、系统设置
- **天眼审计（v0.0.7.6）**：非数据库；开启后写入 **`plugins/ARCCore/sky_eye/*.txt`**（按日），见「天眼系统」

### 🆕 数据库自动升级系统 (v0.0.1.4新增)
- **智能检测**: 自动检测数据库版本并执行必要的升级
- **字段添加**: 为旧数据库自动添加新字段（如is_op字段）
- **向后兼容**: 完全兼容旧版本数据，无需手动迁移
- **安全升级**: 升级过程包含完整的错误处理机制
- **XUID主键系统** (v0.0.1.8 引入): 使用 XUID 作为玩家主键（v0.0.2.3 起不再支持 UUID→XUID 自动迁移）

## 🛠️ 开发信息

### 项目结构
```
EndStone-ARC-CORE/
├── src/endstone_arc_core/
│   ├── __init__.py              # 插件初始化
│   ├── arc_core_plugin.py       # 主插件类
│   ├── sky_eye_log.py           # 天眼系统按日日志与滚动清理（v0.0.7.6+）
│   ├── AchievementSystem.py   # 成就系统（v0.0.5.0+）
│   ├── achievement_conditions.py # 成就条件类型（kill_entity / kill_entity_sum 等）
│   ├── KillRewardConfig.py      # 击杀奖励配置（v0.0.4.0+）
│   ├── EntityDisplayNameManager.py
│   ├── TitleSystem.py
│   ├── GuildSystem.py           # 公会系统（v0.0.7.0+）
│   ├── DatabaseManager.py       # 数据库管理器
│   ├── LanguageManager.py       # 语言管理器
│   └── SettingManager.py        # 设置管理器
├── dist/ARCCore/
│   ├── core_setting.yml         # 配置文件
│   ├── broadcast.txt            # 公告文件
│   ├── entity_display_name.txt
│   ├── kill_reward.txt
│   ├── newbie_welcome.txt       # 新人欢迎消息文件
│   ├── newbie_commands.txt      # 新人自动执行指令文件
│   └── ZH-CN.txt               # 中文语言包
└── pyproject.toml              # 项目配置
```

### 核心技术特性
- **线程安全**: 数据库操作完全线程安全
- **多线程架构**: 位置检测系统使用独立线程，提升60%响应速度
- **事件驱动**: 基于 EndStone 事件系统
- **定时任务**: 使用 Scheduler 实现定时功能
- **模块化设计**: 各功能模块独立，易于维护
- **动态配置**: 支持运行时配置重载
- **精确坐标计算**: 使用 math.floor() 确保负坐标位置计算准确
- **XUID主键系统**: 全面使用XUID作为玩家标识，提升数据一致性和查询性能
- **数据库结构升级**: 支持表结构自动升级（自 v0.0.2.3 起不再提供 UUID→XUID 迁移）
- **统一接口设计**: API和内部功能基于同一套底层接口，提升代码复用性和维护性
- **坐标处理统一**: 所有坐标计算统一使用math.floor()，确保负坐标处理正确
- **可视化领地系统**: 支持粒子效果显示领地边界，提供直观的领地范围展示

### API 兼容性
- **EndStone API**: 0.11+
- **Python**: 3.13+

## 📈 性能特性

- **高效的区块索引**: 领地系统使用区块映射，快速定位
- **内存优化**: 合理的缓存策略，减少数据库查询
- **异步处理**: 耗时操作使用定时任务处理
- **资源清理**: 自动清理过期的传送请求和临时数据

## 🔒 安全特性

- **密码保护**: 玩家密码使用 SHA-256 哈希存储
- **权限系统**: 基于 EndStone 权限系统
- **输入验证**: 所有用户输入都经过严格验证
- **SQL 注入防护**: 使用参数化查询

## 🔌 API 接口

ARC Core 插件提供了丰富的 API 接口供其他插件调用，包括经济系统、头衔系统、领地系统等。

### 💰 经济系统 API

**统一接口设计**：所有API函数都基于统一的底层`*_by_name`系列函数实现，确保与插件内部功能使用相同的数据处理逻辑，提高一致性和可维护性。

#### 1. 获取所有玩家金钱数据
```python
def api_get_all_money_data(self) -> dict
```
- **功能**: 获取所有玩家的金钱数据
- **返回值**: `dict` - 键为玩家名称，值为金钱数量
- **示例**:
```python
arc_plugin = server.get_plugin('ARCCore')
money_data = arc_plugin.api_get_all_money_data()
# 返回: {'PlayerA': 10000, 'PlayerB': 5000, ...}
```

#### 2. 获取单个玩家金钱
```python
def api_get_player_money(self, player_name: str) -> float
```
- **功能**: 获取指定玩家的金钱数量（支持小数，精确到分）
- **参数**: `player_name` (str) - 玩家名称
- **返回值**: `float` - 玩家金钱数量，玩家不存在时返回 0.0
- **示例**:
```python
money = arc_plugin.api_get_player_money('PlayerName')
```

#### 3. 获取最富有玩家信息
```python
def api_get_richest_player_money_data(self) -> list
```
- **功能**: 获取服务器中最富有玩家的信息
- **返回值**: `list` - [玩家名称, 金钱数量]，无数据时返回 ['', 0]
- **示例**:
```python
richest = arc_plugin.api_get_richest_player_money_data()
# 返回: ['RichPlayer', 999999]
```

#### 4. 获取最贫穷玩家信息
```python
def api_get_poorest_player_money_data(self) -> list
```
- **功能**: 获取服务器中最贫穷玩家的信息
- **返回值**: `list` - [玩家名称, 金钱数量]，无数据时返回 ['', 0]
- **示例**:
```python
poorest = arc_plugin.api_get_poorest_player_money_data()
# 返回: ['PoorPlayer', 100]
```

#### 5. 修改玩家金钱
```python
def api_change_player_money(self, player_name: str, money_to_change: float) -> bool
```
- **功能**: 增加或减少指定玩家的金钱（支持小数，精确到分）
- **参数**: 
  - `player_name` (str) - 玩家名称
  - `money_to_change` (float) - 要改变的金钱数量（正数为增加，负数为减少）
- **返回值**: `bool` - 是否操作成功
- **注意事项**:
  - 如果玩家在线，会自动发送金钱变动提示消息
  - 变动数量经四舍五入到分后为 0 时视为无效，返回 False
- **示例**:
```python
# 给玩家增加 1000 金钱
arc_plugin.api_change_player_money('PlayerName', 1000)

# 从玩家扣除 500 金钱
arc_plugin.api_change_player_money('PlayerName', -500)
```

### 🏷️ 头衔系统 API

#### 为玩家解锁头衔
```python
def api_unlock_title(self, player: Player, title: str) -> bool
```
- **功能**：为指定玩家解锁头衔，若该头衔在头衔定义中配置了解锁奖励（金钱、物品），且玩家在线，则自动发放奖励
- **参数**：
  - `player` (Player) - EndStone 玩家对象
  - `title` (str) - 头衔名称（须已在头衔定义中存在，如默认头衔或 OP 创建的头衔）
- **返回值**：`bool` - 是否解锁成功（头衔名无效或已解锁等情况可能返回 False）
- **示例**：
```python
arc_plugin = server.get_plugin('ARCCore')
# 玩家完成某成就后解锁头衔
arc_plugin.api_unlock_title(player, '成就达人')
```

#### 获取新手引导文本
```python
def api_get_newbie_guide_text(self) -> str
```
- **功能**：返回 `plugins/ARCCore/newbie_welcome.txt` 的全文（与主菜单「新手引导」一致），供聊天机器人等插件作为系统提示或知识库
- **返回值**：`str` - 成功为去首尾空白后的文本；文件不存在或读取失败时返回空字符串 `""`
- **示例**：
```python
arc_plugin = server.get_plugin('ARCCore')
guide = arc_plugin.api_get_newbie_guide_text()
```

### 🏠 领地系统 API

#### 1. 判断位置是否在领地内
```python
def api_if_position_in_land(self, dimension: str, position: tuple) -> int | None
```
- **功能**：判断给定维度与坐标是否处于某块领地内
- **参数**：
  - `dimension` (str) - 维度名称（如 `Overworld`）
  - `position` (tuple) - 坐标元组 (x, y, z)，内部会按 x、z、y 取整后查询
- **返回值**：`int | None` - 不在任何领地内返回 `None`，否则返回该领地的 `land_id`
- **示例**：
```python
land_id = arc_plugin.api_if_position_in_land('Overworld', (100, 64, -200))
if land_id is not None:
    # 该位置在领地 land_id 内
    pass
```

#### 2. 获取领地信息
```python
def api_get_land_info(self, land_id: int) -> dict
```
- **功能**：根据领地 ID 获取领地详细信息
- **参数**：`land_id` (int) - 领地 ID
- **返回值**：`dict` - 领地信息字典，不存在则返回空字典 `{}`。常见键包括：
  - `land_name` - 领地名称
  - `dimension` - 维度
  - `min_x`, `max_x`, `min_y`, `max_y`, `min_z`, `max_z` - 范围
  - `tp_x`, `tp_y`, `tp_z` - 传送点坐标
  - `shared_users` - 授权用户 XUID 列表
  - `owner_xuid` - 拥有者键（如 `Player_<xuid>`、`GUILD_<id>`、公共领地键）
  - `for_sale`（**v0.0.7.4+**）- 是否上架出售（bool）
  - `sale_price`（**v0.0.7.4+**）- 上架标价（float，未上架为 `0`）
  - `allow_explosion`, `allow_public_interact`, `allow_actor_interaction`, `allow_actor_damage`, `allow_frame`, `allow_non_public_land` - 各类开关
  - `owner_paid_money` - 购买时支付金额（出售过户后会更新为成交价）
  - **私人领地上架成交**：卖家实收 = 成交价 − 增值税（见 **`LAND_SALE_VAT_RATE`**，对相对 `owner_paid_money` 的溢价计税）
- **示例**：
```python
info = arc_plugin.api_get_land_info(land_id)
if info:
    owner = info.get('owner_xuid')
    name = info.get('land_name')
```

### 🏰 公会系统 API（v0.0.7.3）

#### 1. 获取玩家公会信息
```python
def api_get_player_guild_info(self, player_name: str) -> dict
```
- **功能**：获取玩家当前公会信息（含规模、容量、公会公共/玩家私人贡献点等）
- **参数**：`player_name` (str) - 玩家名称
- **返回值**：`dict`，玩家不存在或未加入公会时返回 `{}`，常见键：
  - `guild_id` (int)
  - `name` (str) - 公会名
  - `role` (str) - `'owner' | 'manager' | 'member'`
  - `size_tier` (str) - `'small' | 'medium' | 'large'`
  - `capacity` (int) - 当前规模上限
  - `member_count` (int) - 当前成员数（含会长）
  - `total_contribution` (int) - 公会公共贡献点
  - `personal_contribution` (int) - 玩家私人公会贡献点
  - `motto` (str) - 公会简介
  - `owner_xuid` (str) - 会长 XUID
  - `join_requires_approval` (bool) - **v0.0.7.3+** 新成员入会是否需要会长/管理者审批（`False` 表示未满时可从「全部公会」直加）
- **示例**：
```python
# 第二个参数请与服务器实际加载的插件 id 一致（entry-points 名一般为 arc_core）
arc_plugin = server.get_plugin('arc_core')
info = arc_plugin.api_get_player_guild_info('PlayerName')
if info:
    print(info['name'], info['size_tier'], info['total_contribution'], info.get('join_requires_approval'))
```

#### 2. 给玩家增加公会贡献点
```python
def api_add_guild_contribution(self, player_name: str, points: int) -> dict
```
- **功能**：给玩家增加公会贡献点 — 玩家私人贡献点和所在公会的公共贡献点 **同时各 +points**
- **参数**：
  - `player_name` (str) - 玩家名称
  - `points` (int) - 必须为正整数；零或负数返回失败
- **返回值**：`dict`
  ```python
  {
      'ok': bool,                       # 是否成功
      'error': Optional[str],           # 失败时为错误码（如 'GUILD_NOT_IN_GUILD'）
      'personal_contribution': int,     # 增加后的玩家私人贡献点
      'guild_total_contribution': int,  # 增加后的公会公共贡献点
      'guild_id': int                   # 玩家所在公会 id；无公会时为 0
  }
  ```
- **常见错误码**：
  - `GUILD_INVALID_PLAYER` - 找不到玩家
  - `GUILD_NOT_IN_GUILD` - 玩家未加入任何公会
  - `GUILD_CONTRIB_INVALID_POINTS` - 点数 ≤ 0 或非整数
  - `GUILD_DB_ERROR` - 数据库写入失败
- **行为说明**：
  - 玩家在线时会自动收到聊天提示（语言键 `GUILD_CONTRIB_ADDED_HINT`）
  - 玩家退出 / 被踢 / 公会解散时，私人贡献点随成员行被删除而清零；公会公共贡献点不会因此减少
- **示例**（小游戏插件结算时调用）：
```python
result = arc_plugin.api_add_guild_contribution('PlayerName', 50)
if result['ok']:
    pass  # 玩家已获得 50 点贡献，公会公共贡献也 +50
else:
    print('add contribution failed:', result['error'])
```

#### 查询 + 发放（整合示例，v0.0.7.3）

第三方插件在完成任务、小游戏结算等场景下，只需 **玩家游戏名** 即可查询或发放贡献点：

```python
def on_minigame_reward(self, player_name: str):
    arc = self.server.get_plugin('arc_core')
    if arc is None:
        return
    personal = arc.api_get_player_guild_contribution(player_name)
    guild_pool = arc.api_get_guild_total_contribution_by_player(player_name)
    info = arc.api_get_player_guild_info(player_name)
    if not info:
        return  # 未加入公会则无法通过 API 累加贡献点
    result = arc.api_add_guild_contribution(player_name, 25)
    if result['ok']:
        self.logger.info(
            'guild contrib +25: personal %s -> %s, guild total %s',
            personal,
            result['personal_contribution'],
            result['guild_total_contribution'],
        )
```

#### 3. 获取玩家私人公会贡献点
```python
def api_get_player_guild_contribution(self, player_name: str) -> int
```
- **功能**：获取玩家当前私人公会贡献点（玩家未加入公会或不存在时返回 0）

#### 4. 获取玩家所在公会的公共贡献点
```python
def api_get_guild_total_contribution_by_player(self, player_name: str) -> int
```
- **功能**：获取玩家所在公会的公共贡献点（玩家未加入公会时返回 0）

#### 5. 设置公会规模等级
```python
def api_set_guild_size_tier(self, guild_name: str, tier: str) -> bool
```
- **功能**：设置指定公会的规模等级（`'small' / 'medium' / 'large'`）
- **参数**：
  - `guild_name` (str) - 公会名（精确匹配）
  - `tier` (str) - 目标规模等级
- **返回值**：`bool`
- **限制**：若目标规模上限低于当前成员数，返回 `False`（拒绝降级）；公会不存在或参数非法也返回 `False`

### 🔧 API 使用示例

#### 完整的插件集成示例
```python
from endstone.plugin import Plugin

class MyPlugin(Plugin):
    def on_enable(self):
        # 获取 ARC Core 插件实例
        self.arc_core = self.server.get_plugin('arc_core')
        
        if self.arc_core is None:
            self.logger.error("ARC Core plugin not found!")
            return
    
    def give_reward_to_player(self, player_name: str, amount: int):
        """给玩家发放奖励金钱"""
        try:
            # 检查玩家当前金钱
            current_money = self.arc_core.api_get_player_money(player_name)
            self.logger.info(f"Player {player_name} current money: {current_money}")
            
            # 增加金钱
            self.arc_core.api_change_player_money(player_name, amount)
            
            # 获取更新后的金钱
            new_money = self.arc_core.api_get_player_money(player_name)
            self.logger.info(f"Player {player_name} new money: {new_money}")
            
        except Exception as e:
            self.logger.error(f"Failed to give reward: {e}")
```

### 📋 API 注意事项

1. **插件依赖**: 确保您的插件在 `plugin.yml` 中声明了对本插件的依赖
2. **错误处理**: 所有 API 调用都应该包含适当的错误处理
3. **线程安全**: 所有 API 方法都是线程安全的，可以在任何线程中调用
4. **性能考虑**: 频繁调用 `api_get_all_money_data()` 可能影响性能，建议缓存结果
5. **玩家存在性**: API 会自动处理不存在的玩家，但建议在调用前验证玩家是否存在

### 🚀 未来 API 计划

- **领地系统 API**: 查询、创建、管理领地的接口
- **传送系统 API**: 程序化传送点管理
- **权限系统 API**: 玩家权限查询和管理
- **数据统计 API**: 服务器统计数据接口

## 📄 许可证

本项目采用开源许可证，详见 LICENSE 文件。

## 🤝 支持与反馈

- **作者邮箱**: DEVILENMO@gmail.com
- **问题反馈**: 请详细描述问题和复现步骤
- **功能建议**: 欢迎提供改进建议

## 📋 近期更新日志

### v0.0.7.6（当前版本）

- ✅ **私人领地上架成交 · 增值税说明**：补充 **`LAND_SALE_VAT_RATE`**（默认 `0.1`）文档与 `core_setting.yml` 示例。逻辑：**税基** = 成交价相对过户前 **`owner_paid_money`** 的溢价（负或零则无税）；**卖家实收** = 成交价 − 税额；买家始终支付全额标价。详见上文「领地管理系统 → 私人领地成交增值税」
- ✅ **天眼系统（Sky Eye）**：新增模块 **`sky_eye_log.py`**；配置 **`ENABLE_SKY_EYE`**、**`SKY_EYE_MAX_RETENTION_DAYS`**（默认 `7`，`0` 表示不删旧文件）。日志目录 **`plugins/ARCCore/sky_eye/`**，按日文件 **`YYYYMMDD.txt`**，记录进离服、破坏/放置、方块与空气交互、实体交互、死亡（含坐标与主手物品）；启动与跨日时按保留天数滚动删除过期日文件。详见上文「天眼系统」

### v0.0.7.5

- ✅ **击杀 → 公会贡献点联动**：新增配置 **`KILL_REWARD_GUILD_CONTRIB_RATIO`**（默认 `0`）；玩家击杀生物成功获得金钱奖励后，按 `floor(reward * ratio)` 同步累加 **私人贡献点** 与 **公会公共贡献点**（仅当玩家已加入公会且换算结果 > 0 时生效）。例如 `kill_reward.txt` 中 `minecraft:creeper=10`、比例 `0.5`，则击杀苦力怕在获得 10 元的同时获得 5 公会贡献点。OP **重载配置** 会同步刷新该比例；语言键 **`KILL_REWARD_GUILD_CONTRIB_HINT`** 见 `dist/ARCCore/ZH-CN.txt`
- ✅ **领地范围重设**：交互圈地或坐标表单定义新长方体，按体积差 **补款/退款**（规则见上文「领地管理系统」）；`LandSystem` 提供 **`update_land_bounds`** 与 chunk 索引更新；**`check_land_availability`** 支持 **`exclude_land_ids`** 排除自身以免与旧范围误判重叠
- ✅ **展示框/展示架权限**：`allow_frame` 为关闭时，**主人、授权、子领地权限、同公会成员（若开启公会成员方块交互）** 仍可操作展示框与各材质展示架，不再误拦领地主人

### v0.0.7.4

- ✅ **私人领地上架出售**：数据库 `lands` 增加 **`for_sale`**、**`sale_price`**；`LandSystem` 提供上架/下架与 **购买过户**（校验仍为原主人且标价一致）。**领地详情** 增加 **「出售领地（上架/改价/下架）」** 入口；**非主人进入** 已上架的私人领地时弹出 **ActionForm**，可查看信息并 **购买**（扣款 → 过户 → 卖家入账；失败路径含退款与过户回滚尝试）。文案见 **`dist/ARCCore/ZH-CN.txt`** 中 `LAND_SALE_*` 键
- ✅ **API**：`api_get_land_info` 返回值文档补充 **`for_sale`**、**`sale_price`**

### v0.0.7.3

- ✅ **每日签到公会贡献点**：新增配置 **`CHECKIN_GUILD_CONTRIBUTION_POINTS`**（默认 `10`）；签到成功且玩家已加入公会时，私人贡献点与公会公共贡献点同时增加该数值；未加入公会则跳过。OP **签到配置 → 配置存款与随机条数** 表单增加对应编辑项
- ✅ **公会 API 说明与示例**：已提供 **`api_add_guild_contribution`**（发放）、**`api_get_player_guild_contribution`** / **`api_get_guild_total_contribution_by_player`**（查询）、**`api_get_player_guild_info`**（综合信息）；**`api_get_player_guild_info`** 返回值增加 **`join_requires_approval`**。README「公会系统 API」补充 **查询 + 发放整合示例**
- ✅ **全部公会浏览与入会**：**查看全部公会**（排序、搜索、分页）；公会页为 **信息预览 + 申请/加入**（本会成员仅 **我的公会** 入口）；审核开关在 **我的公会 → 入会审核设置**，审批在 **入会申请**；数据表 **`guild_join_requests`**、**`guilds.join_requires_approval`**

### v0.0.7.2

- ✅ **公会规模**：公会新增 `size_tier`（`small / medium / large`）字段，新建公会默认 **小型**；服主可在 `core_setting.yml` 中通过 **`GUILD_SIZE_SMALL_MAX`**、**`GUILD_SIZE_MEDIUM_MAX`**、**`GUILD_SIZE_LARGE_MAX`**（默认 10 / 20 / 40）调整各档人数上限；邀请与接受邀请会校验当前规模容量并在已满时返回 `GUILD_FULL`
- ✅ **公会规模升级（消耗公共贡献点）**：会长 / 管理者可在 **我的公会 → 升级公会规模** 中花费公共贡献点升级；消耗在 `core_setting.yml` 中通过 **`GUILD_UPGRADE_TO_MEDIUM_COST`**（默认 `10000`）、**`GUILD_UPGRADE_TO_LARGE_COST`**（默认 `100000`）配置；仅允许由低向高升级（small→medium / large、medium→large），不退还、不可降级
- ✅ **OP 公会管理面板**：在 OP 面板新增「公会管理」入口，可查看所有公会列表（规模、人数、公共贡献点）并 **直接调整任意公会规模**（绕开贡献点消耗，可升可降）；降级时若当前人数超过目标上限会被拒绝
- ✅ **公会名颜色与防注入**：展示名中的 `[公会名]` 前缀按规模上色（默认 **小型 §h / 中型 §s / 大型 §p**，可由语言文件覆盖）；所有公会名读写出口都通过正则统一剥离 `§X` 格式码与残留孤立 §，避免玩家在公会名中粘贴颜色码污染聊天与头顶名
- ✅ **公会改名（会长）**：会长可在 **我的公会 → 公会改名** 中输入新名（自动去色、限长 32、不可与当前同名或与其它公会重名）；改名费用由 `GUILD_RENAME_COST` 配置（默认 `0` 免费），费用 > 0 时操作失败自动回滚扣款；成功后刷新全体在线成员头顶名
- ✅ **公会贡献点**：`guilds.total_contribution`（公会公共贡献点）+ `guild_members.contribution`（玩家私人贡献点）；提供 API：
  - `api_add_guild_contribution(player_name, points)`：玩家私人 +points，所在公会公共 +points
  - `api_get_player_guild_contribution(player_name)`、`api_get_guild_total_contribution_by_player(player_name)`、`api_get_player_guild_info(player_name)`、`api_set_guild_size_tier(guild_name, tier)`
  - 玩家退出 / 被踢 / 公会解散时其私人贡献点随成员行删除而清零；公会公共贡献点不会因成员退出而减少
- ✅ **公会菜单展示**：主菜单「公会」、「我的公会」、成员列表、「邀请在线玩家」均新增 **规模 / 人数 / 公会贡献点 / 我的贡献点** 行；成员列表每行附带该成员的私人贡献点
- ✅ **数据库平滑升级**：旧库自动 `ALTER TABLE` 补齐 `size_tier`（默认 `small`）、`total_contribution`（默认 `0`）、`contribution`（默认 `0`），无需手动迁移

### v0.0.7.1

- 🔧 **成就存储整理**：完成状态写入 **`player_achievement_stats`** 的 **`ach_unlock:<unlock_title>`**（`count ≥ 1`），与击杀计数共用一表；**移除** **`player_achievement_unlocked`**、**`achievement_meta`**
- 🔧 **升级补全**：启动时对已有统计或头衔记录的玩家 **幂等补全** `ach_unlock:`（已解锁头衔或进度已达标则静默标记），避免重复发解锁奖励
- 🔧 **头衔表**：移除冗余 **`player_title_extra`**，解锁时间仅以 **`player_title_unlock_time`** 为准

### v0.0.7.0

- ✅ **公会系统**：创建公会（可配置 **`GUILD_CREATE_COST`**，默认十万）、会长/管理者/成员职级、踢人、会长变更职级、解散与退出；**`GUILD_DATABASE_PATH`** 与主库分离时可多服共享同一公会库
- ✅ **在线邀请**：管理者与会长在 **未入公会的在线玩家** 列表中点选对象，对方 **弹窗接受/拒绝**，确认后直接入会；**新邀请不再写入 `guild_invites`**（表仍保留兼容历史待处理记录）
- ✅ **展示名**：聊天、头顶名、`get_player_name_by_xuid(..., True)` 统一为 **`[公会或[无公会]][头衔]名字`**（无公会前缀白色，有公会前缀为普通稀有度色）
- ✅ **入口**：主菜单 **公会**、**`/arc guild`**

### v0.0.6.0

- ✅ **跨服传送**：`/connecttoserver` 支持按名称匹配已配置目标并传送；**无参数时打开跨服选择面板**（从面板关闭返回主菜单）；控制台/命令方块可通过发送者名解析玩家
- ✅ **圈地与指令**：**`/land pos1` / `pos2` / `buy`** 与旧 **`/landpos1`、`/landpos2`、`/landbuy`** 等价；**交互式四点点地** + **购买面板**（粒子预览、六向坐标修改、`/landbuy` 再次打开）；`/landbuy` 为打开面板确认购买而非直接扣款
- ✅ **`/arc` 快捷子命令**：**`/arc land`**、**`/arc tp`**、**`/arc bank`** 直达对应菜单；主菜单前几项顺序为 **新手引导 → 传送 → 领地 → 银行 → 每日签到**；**小喇叭与重生（/suicide）** 收纳在 **「工具」** 子菜单
- ✅ **死亡回归**：死亡记录坐标在**同一次服务器进程内**不随退出游戏清除（关服重开仍会清空内存记录）
- ✅ **方块禁用**：新增 `DISABLED_BLOCKS` 配置，对配置列表中的方块进行全局禁放置/禁交互（非 OP 生效，OP 直接跳过检查）
- ✅ **每日签到增强**：新增连续签到奖励与前 X 名签到奖励（额外金钱/额外物品），并支持在配置中调整相关参数

### v0.0.5.0

- ✅ **成就系统**：新增成就统计、达成记录与 `achievements.json` 配置；OP 面板 **成就管理** 中维护成就与条件
- ✅ **可配置的击杀成就**：按生物类型（及可选多类型击杀数相加）与达成数量配置解锁头衔；玩家击杀对应单位累计达标后解锁并发放奖励
- ✅ **默认击杀成就包**：支持一键写入内置击杀类头衔定义与成就条件，便于与文档/内置表对齐
- 🔧 **默认头衔**：一键应用默认击杀成就时不再将击杀头衔合并进 `DEFAULT_TITLE`，避免与「进服即送解锁」语义冲突

### v0.0.4.2

- ✅ **每日签到机制**
  - 数据库字段：`total_checkin_count`（累计次数）、`last_checkin_at`（最近一次签到时间，用于当日排序）
  - 随机物品条数：支持每日在 `CHECKIN_REWARD_PICK_MIN`～`CHECKIN_REWARD_PICK_MAX` 之间随机；未配置区间时仍可读旧项 `CHECKIN_REWARD_PICK_COUNT`
  - 签到成功后全服广播：完成提示 + **今日签到先后**（人数少时列全员；人数多时拆成「最早前 10」「最晚前 10」）+ **累计签到榜前 10**
- ✅ **签到排行榜展示**：聊天侧将标题与各名次 **分行广播**，语言文件中名次分隔改为换行，避免一长串顿号连在一起
- ✅ **OP 签到管理页**：入口总览当前存款、随机条数区间、奖励池条目数；**存款与随机条数** 使用弹窗表单一次保存；**物品奖励列表** 为编号列表，可逐条进入 **编辑 / 删除（含确认）** 或 **新增** 条目，无需手改 JSON
- ✅ **玩家间传送请求**：TPA / TPHERE 发起后，目标玩家 **自动收到 Modal 弹窗**，可一键同意或拒绝（仍保留聊天提示与菜单内「处理待处理请求」）

### v0.0.4.1

- 🔧 **随机传送缓降时长**：随机传送落地后给予的缓降（羽落）效果由 **10 秒** 调整为 **30 秒**（`/effect ... slow_falling`）。

- 🐛 **按玩家名解析 XUID（跨版本 / 插件导致名称大小写不一致）**
  - **现象**：与其它版本或第三方插件混用后，运行时传入的玩家名可能被规范为**全小写**（或带首尾空白），而数据库 `player_basic_info.name` 中仍为进服时写入的原始大小写；原先用 `name = ?` 做精确匹配时，SQLite 对英文**区分大小写**，会查不到行，导致 `get_player_xuid_by_name` 返回空，进而经济扣款、对外 API 加减款、传送扣费等依赖「名字 → XUID」的路径失败（例如错误码 `BANK15` / `BANK16`）。
  - **修复**：优先在**在线玩家列表**中按「去空白 + 大小写不敏感」匹配名称得到 XUID；否则对数据库使用 `LOWER(TRIM(name))` 与参数做同等规范化后再匹配；`get_offline_player_op_status` 等与「按名查库」相关的逻辑已统一走上述解析。

### v0.0.4.0

- ✅ **成就系统**
  - 新模块 `AchievementSystem.py`：击杀/破坏统计、成就条件表、达成记录；OP 面板「成就管理」可配置条件并联动头衔解锁与奖励（**可配置击杀单位与默认击杀成就包等完整说明见 v0.0.5.0**）
- ✅ **财富榜首富头衔**
  - 配置 `RICHEST_TITLE_NAME`；金钱变动后刷新财富榜第一；首富易主时撤销旧头衔并授予新首富；离线玩家通过 xuid 写入解锁记录
- ✅ **头衔体验**
  - 解锁头衔时若当前未佩戴任何头衔，自动佩戴新头衔；`PlayerDeathEvent` 与 `ActorDeathEvent` 分离为独立事件处理函数，避免原方法名冲突
- ✅ **每日签到**
  - `last_checkin_date`、存款与加权随机物品；主菜单「每日签到」；OP「签到配置」
- ✅ **击杀生物金钱奖励**
  - `kill_reward.txt`；未配置类型自动追加 `=0`；金额大于 0 才提示；显示名与 `entity_display_name.txt` 联动
- ✅ **OP 面板重构**
  - 入口顺序：重载配置 → 工具 → 经济管理 → 领地管理 → 传送管理 → 成就管理 → 签到配置 → 邀请奖励 → 头衔管理
  - 传送管理：公共 Warp 管理 + 传送参数表单（原传送菜单内 OP 管理入口已移至此处）
  - 领地管理、工具二级菜单；经济管理含在线加减款与经济参数（初始存款、排行榜隐藏 OP、首富头衔名）
- ✅ **配置与重载**
  - OP 重载时同步 `entity_display_name.txt`、`kill_reward.txt`

### 计划中的功能
- 🔄 更多语言包支持
- 🔄 数据备份和恢复
- 🔄 领地系统 API 扩展
- 🔄 传送系统 API 扩展

---

*ARC Core 是一个功能完整、性能优异的 EndStone 插件，为服务器管理者提供了一站式的解决方案。*