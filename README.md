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

## 🚀 快速开始

### 1️⃣ 克隆项目

```bash
git clone https://github.com/zimu645-dotcom/douyin-analyzer.git
cd douyin-analyzer
```

### 2️⃣ 创建虚拟环境并安装依赖

```bash
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3️⃣ 下载转写模型

转写使用 **faster-whisper 模型**（本地运行，隐私安全）。下载模型文件到 `models/` 目录：

```python
# 方式一：用 Python 自动下载（推荐，small 约 460MB）
python -c "from faster_whisper.utils import download_model; download_model('Systran/faster-whisper-small', output_dir='models')"
```

> 也可以从 [HuggingFace](https://huggingface.co/Systran/faster-whisper-small) 手动下载 `model.bin`、`config.json`、`tokenizer.json`、`vocabulary.json` 放入 `models/` 目录。
>
> 想更高准确率可换 `Systran/faster-whisper-medium`。

### 4️⃣ 初始化 Playwright 浏览器（抓取博主主页用）

```bash
python -m playwright install chromium
```

### 5️⃣ 启动服务

```bash
# Windows：双击 start.bat
# 或命令行：
python app/launcher.py
```

浏览器打开 **http://127.0.0.1:8321**

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
