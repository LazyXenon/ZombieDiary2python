# Zombie Diary 2 · 萌僵尸大战2 — Python 复刻

![主菜单](docs/preview/01_menu.png)

《Zombie Diary 2》（中文名《萌僵尸大战2》）的 Python / pygame 单机复刻。代码按原版数据表与反编译结果重建，854×480，桌面运行。

---

## 免责声明

**本项目不是官方作品，与 EZJOY LIMITED 及任何其他原作权利方没有隶属、授权、赞助或合作关系。**

1. 本项目是个人技术学习用的非商业复刻，不主张对原作的任何知识产权。
2. 游戏名称、角色、美术、UI、动画、音乐、音效、剧情文本的权利归原作权利人所有。据公开商店资料与 APK 元数据，原作由 **EZJOY LIMITED** 发布，包名根命名空间为 `com.ezjoy.feelingtouch`，原生库为 `libezjoygame.so`。本仓库不授权任何第三方使用这些素材。
3. 国行 APK 走中国移动游戏渠道签名与计费（详见[国内发行渠道](#国内发行渠道)）。渠道发行关系不等于著作权转让或授权。
4. 不得把本仓库及其中的贴图、音频、字体用于商业用途、付费分发、应用商店上架、广告变现或二次销售。
5. 权利人可以提 Issue 要求删除，相关资源或整个仓库会立即下架。
6. 本仓库不包含、也不提供原版 APK，不提供任何绕过正版或 DRM 的手段。
7. 代码按现状提供，不附带任何担保。使用前自行评估，遵守所在地法律。
8. 代码由 DeepSeek V4.1 Flash、MiniMax 3.1 Flash、HY4 Std（混元）、Kimi K3.1 Pro 协作生成，经过人工审查与测试，仍可能有缺陷。

> 只做学习研究，不碰商业分发。素材归原作权利人，侵权即删。

---

## 目录

- [免责声明](#免责声明)
- [原作背景](#原作背景)
- [国内发行渠道](#国内发行渠道)
- [版权归属](#版权归属)
- [当前版本](#当前版本)
- [截图](#截图)
- [功能](#功能)
- [运行环境](#运行环境)
- [安装与运行](#安装与运行)
- [在 VS Code / CodeBuddy 里运行](#在-vs-code--codebuddy-里运行)
- [操作](#操作)
- [项目结构](#项目结构)
- [验证](#验证)
- [已知问题](#已知问题)
- [资料来源](#资料来源)

---

## 原作背景

| 时间 | 事件 |
|---|---|
| 约 2012 | EZJOY 推出《Zombie Diary（萌僵尸大战）》，横版萌系僵尸射击 |
| 2013 年底 – 2014 年初 | 续作《Zombie Diary 2》上线 App Store，随后登陆 Google Play / Amazon Appstore |
| 2014 | 版本更新加入 minigun、火焰喷射器、更多关卡、Game Center 成就、iCloud 存档 |
| 2014 – 2015 | 部分市场把商店标题更新为 *Zombie Diary 2: Evolution* |
| 约 2016 – 2017 | EZJOY 新品节奏放缓，部分商店页面下架或迁移；未见公开的收购或解散公告 |

原版是横版站桩射击：左右移动、按住开火、刷僵尸波次。20 多把可升级武器，角色解锁与三条独立升级线，机甲和飞行武器作为消耗品召唤，任务类型包括击杀、限时、距离、护送、守卫、收集。

**关于开发商 EZJOY**：公开商店记录里的主体名是 EZJOY LIMITED，商店署名常见 EZJOY / EZJOY LIMITED；多指向香港注册主体，开发团队与深圳有关联，活跃期约 2011–2017。原版 About / 法务文本出现 `Copyright © EZJOY LIMITED. All Rights Reserved.`。成立日期、创始人、注册编号、当前公司状态没有可核验的权威登记材料，这里不写死。

> 维基百科没有《Zombie Diary》或 EZJOY 的专门条目。上表按商店元数据、APK 字符串与第三方归档整理；咪咕公司的沿革以工商登记与官方公告为准，工商细节以香港公司注册处、中国版权保护中心的登记为准。

---

## 国内发行渠道

国行包是 `com.ezjoy.feelingtouch.zombiediary2China`（`versionName=8.8`、`versionCode=888`）。这个 APK 走的是**中国移动游戏渠道**，当时叫「中国移动游戏基地」/「和游戏」，后来随中国移动基地公司化整合进入咪咕文化 / 咪咕游戏体系。

本地 APK 里能直接读到的证据：

| 证据 | 值 |
|---|---|
| 签名证书主体 | `CN=MGame, O=CNMobile, OU=MGame, L=Nanjing, ST=JS, C=CN` |
| 签发者 | `CN=CMCA Code Signing CA, O=CMCA, C=CN` |
| 有效期 | 2013-07-29 → 2015-07-29 |
| 签名文件 | `META-INF/MGame.RSA` / `MGame.SF` |
| 计费资源 | `assets/mmiap/`，75 个文件 |
| 代码标识 | `Lcom/chinaMobile/MobileAgent;`、`SmsPayCMCC_GC` / `SmsPayCMCC_MM`、`CMCC_GC` / `CMCC_MM` |

`CNMobile` 是中国移动，`L=Nanjing, ST=JS` 对应设在南京的游戏基地，`mmiap` 是中国移动应用内计费。

**能确认的**：EZJOY 是原作开发/版权方；这份具体国行 APK 由中国移动游戏渠道签名、接入其计费 SDK 并发行。
**不能确认的**：没有找到正式授权公告能证明「某家公司独家代理《萌僵尸大战2》」。EZJOY 与中国移动之间是独家代理、联合运营还是渠道分发，签约公司工商全称，「咪咕文化科技有限公司」（2014 年成立）是不是这份 2013 年签名包的直接合同主体，都没查到。公司沿革不等于当年的代理合同。

要法律意义上的代理商，去查 2013–2015 年游戏媒体通稿、咪咕游戏公告、国家版权局软件著作权登记或当年的渠道协议。本 README 只写 APK 能验证的部分。

---

## 版权归属

| 内容 | 权利方 |
|---|---|
| 游戏整体、名称、角色、美术、UI、动画、音乐音效、剧情 | EZJOY LIMITED（据商店与 APK 版权串） |
| 本仓库的 Python 代码 | 本项目作者 |
| 本仓库内的素材文件 | 不属于本项目，仅为研究目的随代码附带 |

---

## 当前版本

这个文件夹就是最终版代码：79 个 Python 文件、约 3.16 万行，资源 21 MB，数据 408 KB。没有把测试脚本、探针、截图工具放进仓库。

最后一次回归在 2026-11-06：`compileall` 通过、76 个测试脚本全通过、133 关逻辑全部跑通、地图稳态与原版参考帧逐像素一致率约 92.7%。`t_all_levels.py` 测的是关卡逻辑能否走完，不等于「玩家用初始装备一定能打通」。

---

## 截图

以下截图由本仓库当前代码无头渲染，`SDL_VIDEODRIVER=dummy`，854×480。

| | |
|---|---|
| **主菜单**<br>![主菜单](docs/preview/01_menu.png) | **世界地图**<br>![地图](docs/preview/02_map.png) |
| **战斗（第 1 关）**<br>![战斗](docs/preview/03_battle.png) | **军火库 · 武器**<br>![武器](docs/preview/04_shop_gun.png) |
| **军火库 · 机甲**<br>![机甲](docs/preview/05_shop_mech.png) | **军火库 · 角色**<br>![角色](docs/preview/06_shop_soldier.png) |

---

## 功能

- 主菜单 → 世界地图 → 关卡选择 → 战斗 → 结算 → 关卡推进
- 士兵移动、开火、朝向；13+ 僵尸类型；Boss；击杀 / 限时 / 距离 / 护送 / 守卫 / 收集任务
- 30+ 把武器，含近战、泡泡、激光、声波、火箭、榴弹、闪电等特效；升级 4 级并按等级换皮肤
- 8 台机甲，属性运行时读 `weapon/mech_N.xml`；`mech_7` 是自动炮塔，不变身
- 治疗、护盾、力量、速度、空袭、飞行武器
- 军火库四个页签，金币 / 钻石双货币
- 本地 JSON 存档：金币、钻石、关卡进度、武器等级、角色等级、机甲数量、每日任务、成就
- 签到、每日任务、成就、老虎机、僵尸商店、设置、暂停、复活、结算
- 键盘与触屏操作，全键盘导航，按键反馈，按角色区分的音效

与原版的差别：原版是移动端触屏，这里在桌面跑；原版联机、内购、广告相关功能没做（服务器早已下线）；本地缺几张原版贴图，相关位置用系统字体替代。

---

## 运行环境

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10/11（开发与验证平台）。Linux / macOS 理论上可跑，未完整验证 |
| Python | 3.12（实测 3.12.10） |
| pygame | 2.6.1（SDL 2.28.4） |
| 内存 | 512 MB 以上可用 |
| 磁盘 | 约 25 MB |
| 显示 | 854×480 窗口，可切全屏 |
| 字体 | 系统 `Microsoft YaHei`（微软雅黑）。非 Windows 需自备中文字体，否则中文可能显示成方块 |

运行游戏只需要 pygame。`numpy` 是离线像素比对脚本用，不是运行依赖。

---

## 安装与运行

```bash
git clone <仓库地址> ZombieDiary2python
cd ZombieDiary2python
```

Windows：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install pygame==2.6.1
python main.py
```

Linux / macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pygame==2.6.1
python3 main.py
```

首次启动会在项目相邻的 `save_data\` 目录生成 `save.json`，删掉它就重置存档。游戏目录里不留运行时文件。

无头运行（截图 / 自动化）：

```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python main.py
```

PowerShell：

```bash
$env:SDL_VIDEODRIVER="dummy"; $env:SDL_AUDIODRIVER="dummy"; python main.py
```

---

## 在 VS Code / CodeBuddy 里运行

仓库自带 `.vscode/launch.json`，克隆后不用改配置就能跑。

1. 建虚拟环境并装依赖（仓库根目录）：

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install pygame==2.6.1
   ```

2. 打开 `main.py`，按 `F5`，或者点右上角运行按钮。下拉框里有三个配置：

   | 配置 | 作用 |
   |---|---|
   | `运行游戏 (Run game)` | 直接开游戏窗口 |
   | `运行游戏 (无头 / 截图 headless)` | 不开窗口，渲染一张主菜单截图到 `docs/preview/01_menu.png` |
   | `运行游戏 (调试当前文件 debug current file)` | 只跑当前打开的 `.py` |

`.vscode/settings.json` 里把解释器指到 `${workspaceFolder}/.venv/Scripts/python.exe`，所以解释器跟着项目走，不依赖全局环境。

> **没装虚拟环境也能跑**：删掉 `.vscode/settings.json` 里的 `python.defaultInterpreterPath` 一行，VS Code 会用当前选中的全局解释器。

### 弹窗 `command 'python.execInTerminal-icon' not found`

这个弹窗不是本仓库的问题，是 Python 扩展没激活成功：右上角那个「运行」按钮由 `ms-python.python` 提供，扩展激活失败时命令就没注册，VS Code 只能弹这个错。

查扩展宿主日志（`帮助 → 打开日志文件夹 → window1/exthost/exthost.log`），如果看到：

```text
Activating extension ms-python.python failed due to an error:
TypeError: Cannot read properties of undefined (reading 'onDidChangeEnvironment')
```

说明依赖 `ms-python.vscode-python-envs` 的扩展安装残缺（`dist/extension.js` 缺失）。重装即可：

```bash
code --uninstall-extension ms-python.vscode-python-envs
code --install-extension ms-python.vscode-python-envs
```

装完重启 VS Code。CodeBuddy CN 同理，把 `code` 换成它的 CLI 路径。

---

## 操作

| 按键 | 功能 |
|---|---|
| `A` / `D` | 左 / 右移动 |
| `Space` | 开火 |
| `1` `2` `3` `4` | 切换四个武器槽 |
| `Shift` | 顺序换枪 |
| `Q` `E` `R` | 使用三个技能道具 |
| `X` | 装备 / 使用机甲 |
| `↑` `↓` `←` `→` | 界面导航 |
| `Enter` | 确认 |
| `Esc` | 返回 / 暂停 |

鼠标可直接点界面按钮；左下角虚拟摇杆移动、右下角开火键射击。设置页能切「键盘模式」「隐藏虚拟按键」并改键位。

---

## 项目结构

```
.
├── main.py                  # 入口
├── app/                     # 场景、输入、弹窗、常量
│   ├── core.py              # App 主体、场景切换、渲染
│   ├── input.py             # 键鼠分发
│   ├── scene_map.py         # 世界地图
│   ├── scene_shop.py        # 军火库
│   ├── scene_battle.py      # 战斗场景与 HUD
│   ├── dialogs.py           # 弹窗装配
│   └── constants.py         # 全局常量
├── engine/                  # 资源、节点树、骨骼、字体、音频、反馈
├── game/                    # 战斗、武器、机甲、商店、存档、弹窗（50+ 模块）
├── assets/
│   ├── images/              # 图片资源
│   └── raw/                 # 原版数据表 XML + 音频
├── data/                    # 节点树、资源名映射、静态表
├── docs/preview/            # README 截图
├── .gitignore
└── README.md
```

数值从 `assets/raw/**/*.xml` 读，不硬编码：武器、僵尸、机甲、商店价格、133 关配置都在里面。界面几何和交互逻辑按反编译 `libezjoygame.so` 的伪代码对齐，包括 `SoldierShopLayer::onClickEquipButton`、`MechShopLayer::onBuyMech` / `onEquipMech`、`Soldier::onChange2Mech`、`CallMechAbility::onMechGetup`、`WeaponEffect::onStartFire`、`TimeCounter::updateTime`。

---

## 验证

在游戏目录内：

```bash
python -m compileall -q game app engine main.py
```

批量回归脚本没有放进这个仓库（放在本地工作区 `D:\Code\mz2_work`），所以 clone 之后跑不了 `run_all_tests.py`。当前这份代码最后一次跑的结果是 76/76 通过、133 关逻辑全通。要在仓库内自建回归，把 `t_all_levels.py` 之类脚本拷进来再跑：

```bash
python t_all_levels.py
```

注释用 `#` 单行，不用三引号块注释。

---

## 已知问题

角色页：

1. 当前装备角色的按钮仍可能被注册成购买热区，点击可能重复扣费。
2. 「升级」按钮只在角色未装备时显示。
3. 属性条用当前装备角色的等级，却显示预览角色的数值表。

机甲页：

1. 属性条仍用 `mech_actors.xml` 的旧档位，没和战斗侧的 `weapon/mech_N.xml` 同步。
2. 属性条标签贴图复用了角色页的「生命/速度/装甲」，与机甲三属性顺序不一致。
3. 「购买」「使用/装备」「再买一台」三个按钮的语义有互相兼任。
4. `mech_7` 是炮塔不变身，商店页仍按普通机甲展示。

其他：

1. `game/battle.py` 超过 2000 行，没拆。
2. 存档是明文 JSON，无 schema 版本号，无校验。
3. 部分界面还没和模拟器实拍逐像素对齐。
4. 非 Windows 平台要自己配中文字体。

---

## 资料来源

- 原作：EZJOY LIMITED — *Zombie Diary 2 / 萌僵尸大战2*
- 引擎：cocos2d-x 2.1.4（原版）、pygame 2.6.1（本复刻）
- 代码生成：DeepSeek V4.1 Flash、MiniMax 3.1 Flash、HY4 Std（混元）、Kimi K3.1 Pro
- 依据：App Store / Google Play 公开元数据、国行 APK 内字符串与签名证书、`libezjoygame.so` 反编译伪代码

核验入口：

- [Google Play 搜索](https://play.google.com/store/search?q=Zombie%20Diary%202&c=apps)
- [App Store 搜索](https://apps.apple.com/us/search?term=Zombie%20Diary%202)
- [APKPure 搜索](https://apkpure.com/search?q=zombiediary2)
- 香港公司注册处：<https://www.cr.gov.hk>
- 中国版权保护中心：<https://www.ccopyright.com.cn>

---

**Zombie Diary 2 · Python Revival**

用 Python 记住一款已经停服的老游戏。
