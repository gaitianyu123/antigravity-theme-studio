# Antigravity Theme Studio (WorkBuddy 风格主图主题 + 全界面中文汉化)

![Version](https://img.shields.io/badge/version-v3.2.0-5b6cf9?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078d4?style=flat-square)
![Python](https://img.shields.io/badge/python-3.9%2B-3776ab?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-2f855a?style=flat-square)

一套专为 **Google Antigravity 2.0 桌面客户端** 打造的非侵入式视觉美化与中文汉化套件。
采用 **WorkBuddy 同款主图插画主题体系** + **v3.0 全界面几何语义自适应引擎** + **零黑框单实例伴随守护**，不修改客户端安装包、随客户端版本自动跟随，支持客户端内右上角一键换肤与 100% 无痕还原。

---

## ✨ 核心特性

- **🎨 WorkBuddy 同款 8 套主图主题 + 自定义壁纸导入**
  - 内置 **伙伴（四角童趣手绘插画 + 输入框右上角探头戴耳机小猫）**、**有风（清风绿叶与松林水彩）**、**经典萌企（极简冰白 + 红围巾小企鹅）**、**同行（冰青水波漩涡）**、**涟漪（静谧湖面安睡白猫）**、**浅色**、**深色**、**跟随系统**。
  - 支持在主题中心一键点击 **「+ 自定义主图」** 导入本地任意 JPG/PNG/WebP 壁纸自动生成专属主题。
  - 自动将背景主图编译内嵌为 Data URI，彻底解决 Electron 拦截本地图片路径的问题。
- **🧩 v3.0 全界面几何语义自适应引擎**
  - 按窗口几何区域自动识别全屏遮挡层、左侧边栏、顶栏、输入框胶囊与右侧辅助面板，穿透多层实心白底让主图完整展现，同时保持文字、代码块与弹窗高对比度清晰可读。
  - 不依赖易变的内部混淆类名，**客户端常规更新升级后依然自动适配生效**。
- **🇨🇳 高精度全界面中文汉化（零误翻、可无痕回滚）**
  - 内置 220+ 条 Antigravity 2.0 界面词条与动态正则模板（`i18n/zh-CN.json`），通过 `MutationObserver` 实时追踪弹窗、菜单与设置页。
  - 具备作用域防火墙，自动跳过 `<pre>`、`<code>`、编辑器、终端与正文区，绝不误翻代码与聊天内容。
  - 客户端升级出新功能按钮时，支持一键扫描并导出待补充词条至 `i18n/discovered_new_ui_terms.json`。
- **⚡ 客户端内右上角「🎨 主题」快捷弹窗 + 零弹窗静默守护**
  - 在客户端右上角安全区注入可拖拽的 Shadow DOM 悬浮胶囊，点一下即可在客户端内直接弹出 WorkBuddy 同款主题中心，0.1 秒秒换皮肤。
  - 核心引擎纯 Python 3 标准库实现（内置 RFC6455 WebSocket 客户端），采用 `ctypes` 直接调用 Windows `version.dll` 检测客户端版本，**全程零 CMD/PowerShell 黑框闪烁**，内置系统命名互斥锁严格单实例防多开。
- **🛡️ 100% 非侵入、零破坏**
  - 不改动 `Antigravity.exe` 或 `app.asar` 安装文件，关闭或点击「无痕还原默认」即可瞬间恢复原生界面与原始英文。

---

## 🖼️ 内置主题一览

| 主题 ID | 主题名称 | 模式 | 视觉风格说明 |
| :--- | :--- | :--- | :--- |
| `wb-partner` | **伙伴**（默认） | 浅色 | 四角童趣手绘插画主图 + 柔紫蓝雾面侧边栏 + 输入框右上角探头戴耳机小猫 |
| `wb-breeze` | **有风** | 浅色 | 左上角微风绿叶枝条 + 明亮晴空留白 + 底部晨光松林与野花草坪水彩主图 |
| `wb-penguin` | **经典萌企** | 浅色 | 90% 极简冰白留白 + 右下角红围巾挥手萌企鹅经典吉祥物主图 |
| `wb-companion` | **同行** | 浅色 | 淡冰青蓝流体水波漩涡微纹主图 + 清透海风磨砂侧边栏 |
| `wb-ripple` | **涟漪** | 浅色 | 静谧柔蓝湖面同心涟漪 + 左上轻舟 + 右下蜷缩安睡白猫主图 |
| `wb-light` | **浅色** | 浅色 | WorkBuddy 极简浅色工作台（纯净白画布 + 微灰侧边栏 + 科技蓝高光） |
| `wb-dark` | **深色** | 深色 | WorkBuddy 暗夜炭灰工作台（中性 Zinc 灰黑 + 夜间科技蓝高光） |
| `wb-system` | **跟随系统** | 自动 | 自动跟随 Windows 系统深浅色模式实时无感切换 |

---

## 🚀 快速试用（三步上手）

### 环境要求
- **操作系统**：Windows 10 / 11
- **运行环境**：Python 3.9+（核心引擎零第三方依赖；如需使用桌面图形切换面板与自定义主图导入，执行 `pip install Pillow` 即可）

### 方式一：一键体验（推荐）
1. **下载并解压**本项目到本地任意目录（例如 `D:\antigravity-theme-studio`）。
2. **先看预览（可选）**：直接双击打开 `preview.html`，即可在浏览器中完整预览 8 套主图主题与中/英汉化对照效果。
3. **创建桌面零黑框启动图标**：双击运行 `创建桌面专属图标.bat`，桌面会自动生成 **`Antigravity (WorkBuddy主题+汉化)`** 图标。
4. **启动体验**：
   - 先完全退出当前正在运行的 Antigravity 2.0（右键右下角系统托盘图标选择退出）；
   - 双击桌面的 **`Antigravity (WorkBuddy主题+汉化)`** 图标，客户端即会自动以 **「伙伴」主图 + 全界面中文汉化 + 静默伴随守护** 模式启动！
   - 进入客户端后，点击右上角可拖动的 **「🎨 主题」** 按钮即可随时秒切全部 8 套主题、开关中文汉化或无痕还原。

### 方式二：桌面图形主题中心 / 命令行切换
- **打开桌面主题中心（WorkBuddy 风格面板）**：双击 `启动主题切换器.bat`（支持点击「+ 自定义主图」导入本地壁纸）。
- **命令行极速切换**：
  ```bat
  switch.bat                :: 查看全部可用主题列表
  switch.bat wb-partner     :: 切换为「伙伴」主图主题 + 探头小猫
  switch.bat wb-breeze      :: 切换为「有风」清风森林水彩主图
  switch.bat wb-penguin     :: 切换为「经典萌企」主图
  switch.bat wb-companion   :: 切换为「同行」冰青水波主图
  switch.bat wb-ripple      :: 切换为「涟漪」静谧睡猫主图
  switch.bat wb-dark        :: 切换为「深色」工作台
  switch.bat reset          :: 一键无痕还原原生样式与原英文
  ```

---

## ⚙️ 客户端路径与自定义配置

- 首次运行时，引擎会自动扫描 Windows 常见安装路径与桌面/开始菜单快捷方式定位 `Antigravity.exe`，**通常无需手动配置**。
- 如果你的客户端安装在自定义目录，可手动编辑 `config.json`：
  ```json
  {
    "antigravity_exe": "你的 Antigravity.exe 完整路径",
    "debug_port": 9222,
    "active_theme": "wb-partner",
    "enable_zh_cn": true,
    "auto_follow_client_updates": true,
    "auto_watch_interval_sec": 2.0
  }
  ```
- **自定义词典**：直接编辑 `i18n/zh-CN.json` 并保存，后台守护会自动热更新生效，无需重启客户端。

---

## ❓ 常见问题（FAQ）

<details>
<summary><b>1. 双击启动后主题没有生效怎么办？</b></summary>

Electron 应用默认开启单实例保护：如果启动前 Antigravity 仍在后台托盘运行，新启动指令会被旧进程接管，导致 `--remote-debugging-port=9222` 参数未生效。
**解决方法**：右键 Windows 右下角任务栏托盘里的 Antigravity 图标将其**完全退出**，然后再双击桌面专属图标或 `带主题模式启动Antigravity.bat` 即可 100% 生效。
</details>

<details>
<summary><b>2. Antigravity 客户端自动更新后，这个脚本还能继续用吗？</b></summary>

- **常规版本更新完全支持**：本工具不修改任何安装包文件，且 v3.0 引擎按视觉几何结构自适应换肤、不依赖混淆类名，后台伴随守护会在检测到客户端升级后自动重注主题与中文汉化，并扫描新版新增词条。
- 仅在两种特殊情况下需要关注：① 若大更新改变了 `Antigravity.exe` 安装路径，清空或更新 `config.json` 中的路径即可；② 若官方未来主动禁用 Electron 的 `--remote-debugging-port` 参数，则非侵入热加载方式将受限。
</details>

<details>
<summary><b>3. 如何彻底关闭并恢复客户端原貌？</b></summary>

在客户端右上角「🎨 主题」弹窗中点击 **「无痕还原默认界面」**，或在命令行执行 `switch.bat reset`，即可瞬间移除所有注入样式、主图与汉化；之后用官方原快捷方式启动客户端即完全回归原生状态。
</details>

---

## 📁 目录结构

```text
antigravity-theme-studio/
├── theme_engine.py                   # v3.0 核心引擎（纯标准库 CDP/WS + 几何自适应换肤 + 汉化 + 单实例静默守护）
├── theme_gui.py                      # WorkBuddy 风格桌面主题中心 GUI（支持自定义主图导入）
├── preview.html                      # 浏览器全真模拟预览器（8 套主题 + 中英切换）
├── config.json                       # 配置文件（支持自动探测客户端路径）
├── 启动主题切换器.bat                 # 一键打开桌面主题中心
├── 带主题模式启动Antigravity.bat      # 一键零黑框伴随模式启动客户端
├── 创建桌面专属图标.bat               # 在桌面生成零黑框专属启动快捷方式
├── switch.bat                        # 命令行极速切换工具
├── themes/                           # 8 套主题样式表与 catalog.json 元数据
├── assets/                           # 主图插画、探头小猫 SVG 与缩略图资产
├── i18n/zh-CN.json                   # 220+ 条 Antigravity 2.0 精准中文词典
├── requirements.txt                  # 可选 GUI 依赖声明 (Pillow)
├── .gitignore
├── LICENSE
└── README.md
```

---

## 📄 开源协议与说明

- 本项目基于 [MIT License](LICENSE) 开源，仅用于个人桌面客户端外观学习与视觉定制，不篡改官方安装包与核心逻辑。
- 如觉得好用，欢迎点一个 ⭐ **Star** 支持！
