# 🎬 抖音视频拆解分析系统

一键下载抖音视频 → 本地语音转写 → AI 多维改写分析 → 飞书多维表格导出。

面向短视频创作者 / 运营 / 拆片学习者：**输入一个视频链接或博主主页，自动拆解成可复用的爆款脚本、钩子、结构分析**。

---

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 📥 视频下载 | 单个视频 / 博主主页批量，自动提取音频（yt-dlp） |
| 🎙 本地语音转写 | **faster-whisper 本地模型**，不依赖云端，免费、隐私安全 |
| 🤖 AI 多维分析 | DeepSeek / MiMo 可配置引擎：润色、多版本仿写、总览分析、复刻提示词 |
| 🎬 画面分析 | 可选逐帧画面 AI 解读（勾选才启用，默认关闭省流量） |
| ⚙️ 模块按需生成 | **生成模块勾选控制**：AI 分析 / 润色 / 多版本 / 画面，勾哪个生成哪个 |
| 📊 飞书导出 | 一键导出到飞书多维表格（自动建字段，**含画面帧图**） |
| ⏹ 停止拆解 | 随时终止任务，关闭所有 API 调用 |
| 🔥 流式输出 | 分析过程实时打字机输出，不卡顿 |
| 💾 API 长期保存 | 勾选后 API Key 免重复填写 |

---

## 🖥 系统要求

- **Windows / Linux / macOS**
- **Python 3.10+**
- **推荐 NVIDIA GPU**（可选，有 GPU 转写快数倍；无 GPU 用 CPU 也能跑）
- 内存建议 8GB+

---

## 🚀 快速开始（一步一步，纯手动）

> 以下以 **Windows** 为例（macOS/Linux 把 `venv\Scripts` 换成 `venv/bin`）。

### 💡 最省事方式（Windows 用户推荐）

1. **双击 `install.bat`** → 没装 Python 会自动帮你装，然后自动创建环境、装依赖、装浏览器、下载模型（全自动）
2. **双击 `login.bat`** → 弹出浏览器扫码登录抖音，自动保存登录状态
3. **双击 `start.bat`** → 启动服务

> **可以放任意盘**：整个项目是便携的，venv、模型、浏览器都装在项目文件夹内（`browsers/`），放 C 盘 / D 盘 / E 盘任何位置都能用，移动整个文件夹也不会坏。
>
> 装 Python 需要系统权限，可能会弹出安装提示，点同意即可。若自动安装失败，再手动装 Python（见下方第 1 步）。

下面的手动步骤是它的详细分解，遇到问题可对照排查。

### 第 1 步：安装 Python（3.10 或更高）

1. 打开浏览器访问 **https://www.python.org/downloads/**
2. 点击 **Download Python 3.12.x**
3. 运行安装包，**务必勾选最下方的「Add Python to PATH」**，然后点 Install Now
4. 按键盘 **Win + R** → 输入 `cmd` → 回车（打开命令提示符）
5. 输入 `python --version` 回车，能看到 `Python 3.12.x` 说明安装成功

### 第 2 步：下载本项目

任选一种方式：

**方式 A（命令行）**
```bash
git clone https://github.com/zimu645-dotcom/douyin-analyzer.git
cd douyin-analyzer
```

**方式 B（网页下载 ZIP）**
1. 打开 https://github.com/zimu645-dotcom/douyin-analyzer
2. 点绿色 **Code** 按钮 → **Download ZIP**
3. 解压到任意目录，进入解压后的 `douyin-analyzer` 文件夹

### 第 3 步：创建虚拟环境

在命令提示符里（已 `cd` 到项目目录）：
```bash
python -m venv venv
```

### 第 4 步：激活虚拟环境

```bash
# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

> 激活成功后，命令提示符最前面会出现 `(venv)` 标记。

### 第 5 步：安装依赖

```bash
pip install -r requirements.txt
```

> 需要等待几分钟下载。若下载慢，可先执行 `pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple` 换国内镜像。

### 第 6 步：安装浏览器（抓取博主主页用）

```bash
python -m playwright install chromium
```

> 这一步会下载一个 Chromium 浏览器内核（约 150MB）。只分析单个视频可以跳过，但**批量分析博主主页必须有它**。

### 第 7 步：下载转写模型

```bash
python -c "from faster_whisper.utils import download_model; download_model('Systran/faster-whisper-small', output_dir='models')"
```

> 下载约 460MB，完成后 `models/` 目录里会出现 `model.bin` 等文件。
> 想更高准确率可把 `small` 换成 `medium`（约 1.5GB，转写更准但更慢）。
>
> **国内网络慢？** 先执行 `set HF_ENDPOINT=https://hf-mirror.com`（Windows）或 `export HF_ENDPOINT=https://hf-mirror.com`（macOS/Linux），再用上面的命令即可走国内镜像加速下载。

### 第 7.5 步：登录抖音（必须！否则下载会失败）

```bash
# Windows：双击 login.bat
# 或命令行输入：
python app/douyin_login.py
```

会弹出 Chrome 窗口打开抖音，用 **抖音 APP 扫码登录**（或账号密码）。登录后**关闭窗口**，登录状态自动保存（`cookies.txt` + `chrome_profile/`）。之后下载视频、抓取博主主页都需要它。以后不用重复登录（cookie 有效期内）。

### 第 8 步：启动服务

```bash
# Windows：直接双击 start.bat
# 或命令行输入：
python app/launcher.py
```

看到 `启动服务: http://127.0.0.1:8321` 即成功。

### 第 9 步：打开网页使用

浏览器访问 **http://127.0.0.1:8321**，按下方「使用指南」操作。

---

## 🧭 第一次使用必看（配置 API Key）

1. 网页右上角点 **「⚙️ 模型配置」**
2. 在「改写引擎」/「视觉模型」里填入你的 **API Key**（DeepSeek 或 MiMo，任选）
   - 没有 key？去 [DeepSeek 开放平台](https://platform.deepseek.com) 或 [小米 MiMo](https://platform.mimo.ai) 注册获取
3. 点 **「💾 保存配置」**
4. 之后就能正常分析视频了

> ⚠️ **没填 API Key 也能用**：转写（音频→文字）是本地免费的；只有 AI 改写分析、画面分析需要 API Key。

---

## 🧭 使用指南

### 分析单个视频

1. 切换到「单个视频链接」
2. 粘贴抖音视频链接（`https://www.douyin.com/video/xxx`）
3. **勾选需要的生成模块**（不勾选则不生成、不调用 AI）
4. 点击「🚀 开始拆解」

### 批量分析博主主页

1. 切换到「博主主页批量」
2. 粘贴博主主页链接（`https://www.douyin.com/user/xxx`）
3. 设置提取数量
4. 点击「🚀 开始拆解」
5. 自动：**并行下载音频 → 逐个转写 → 按顺序 AI 分析**，顶部显示 `第 2/5 个`

### 生成模块说明

| 模块 | 作用 |
|------|------|
| ☑ AI 分析 | 视频总览（总结/场景/结构）+ 值得学习 |
| ☑ 润色改写 | 逐段润色转写文本 |
| ☑ 多版本仿写 | 口播版 / 变体版 / 原结构复刻版 / 开头钩子 |
| ☑ 画面分析 | 逐帧画面 AI 解读（需勾选，下载视频） |

> 默认全部不勾选（只转写原文）。勾选才调用对应 AI，省 token 更快速。

### 导出到飞书

分析完成后，点击报告区的「导出到飞书」即可自动写入多维表格（自动创建字段 + 上传画面帧图）。

---

## ⚙️ 配置说明

### API Key 配置

点右上角「⚙️ 模型配置」：

| 引擎 | 默认模型 | 用途 |
|------|----------|------|
| 主引擎 | DeepSeek（deepseek-v4-flash） | AI 改写分析 |
| 兜底 | MiMo（mimo-v2.5） | 主引擎失败自动切换 |
| 视觉 | MiMo（mimo-v2.5） | 画面分析 |

- 填写 **API Key** 并保存
- 勾选 **「长期保存 API Key」** → 下次免填，不勾选 → 任务完成后自动清除

> ⚠️ 没有配置 API Key 时，本地转写仍可用，但 AI 分析模块会明确提示「未配置 API Key」。

### 飞书多维表格配置

1. 在 [飞书开放平台](https://open.feishu.cn) 创建应用，获取 **App ID / App Secret**
2. 开通权限并**发布新版本**：
   - `bitable:app`（查看多维表格）
   - `base:record:create`（创建记录）
   - `base:table:read`（读取字段）
   - `base:table:update`（自动建字段）
   - `drive:drive`（上传画面帧图）
3. 在多维表格中添加该应用，权限选 **「可编辑」**
4. 在配置面板填入：多维表格 Token + 数据表 ID（从表格 URL 提取）
5. 点「🔗 测试连接」验证

---

## ❓ 常见问题

### 导出飞书报 403 Forbidden？
权限未生效。检查：① 权限是否开通；② **是否发布了新版本**（权限变更必须发布）；③ 多维表格中添加应用是否选了「可编辑」。

### 关闭网页后服务会自动停止？
是的（设计如此）。打开网页服务保持运行，关闭网页约 3 秒后自动停止。重新使用需再次启动。

### 视频没有语音（纯音乐/静音）？
自动识别并跳过 AI 分析，不浪费 API。

### 如何换 AI 模型？
配置面板「模型名」下拉可直接切换（预置 DeepSeek / MiMo 常用模型）。

---

## 📄 目录结构

```
├── app/                  # 核心应用
│   ├── server.py         # FastAPI 后端
│   ├── worker.py         # 分析任务 Worker
│   ├── services.py       # 下载/转写/改写核心逻辑
│   ├── vision_analyzer.py# 画面分析
│   ├── feishu_client.py  # 飞书 API 客户端
│   ├── feishu_export.py  # 飞书导出
│   └── static/           # 前端页面
├── models/               # 转写模型（自行下载）
├── requirements.txt      # Python 依赖
└── start.bat             # Windows 启动脚本
```

## 📝 License

仅供学习交流使用。
