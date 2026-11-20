# -*- coding: utf-8 -*-
"""应用配置（config.json）：改写引擎 + 视觉模型
可被前端设置面板修改，持久化到 app_output/config.json
"""
import os, json

from _paths import BASE, OUTPUT_DIR
CONFIG_FILE = os.path.join(OUTPUT_DIR, "config.json")

DEFAULT_CONFIG = {
    "rewrite": {
        "primary": {
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com/chat/completions",
            "model": "deepseek-v4-flash",
            "key": "",          # API Key（面板直接输入，不预填默认值）
        },
        "fallback": {
            "provider": "mimo",
            "base_url": "https://api.xiaomimimo.com/v1/chat/completions",
            "model": "mimo-v2.6-flash",
            "key": "",
        },
    },
    "vision": {
        "provider": "mimo",
        "base_url": "https://api.xiaomimimo.com/v1/chat/completions",
        "model": "mimo-v2.6-flash",
        "key": "",
        "fps": 1,             # 每秒抽帧数（0.1～10）：1=每秒1帧，0.333=每3秒1帧
        "enabled": True,
    },
    "asr": {
        "engine": "cloud",        # 转写引擎：cloud = 硅基流动云端（SenseVoiceSmall）
        "base_url": "https://api.siliconflow.cn/v1/audio/transcriptions",
        "model": "FunAudioLLM/SenseVoiceSmall",
        "key": "",                # 硅基流动 API Key（cloud.siliconflow.cn 获取）
    },
    "feishu": {
        "app_id": "",               # 飞书应用 App ID
        "app_secret": "",           # 飞书应用 App Secret
        "app_token": "",            # 多维表格 app_token（从URL获取）
        "table_id": "",             # 数据表 table_id（从URL获取）
        "auto_export": False,       # 分析完成后自动导出到飞书
    },
    "remember_key": False,          # 勾选「长期保存」才持久保存 API Key；不勾选任务完成后自动清除
}


def load_config():
    """读取配置（不存在则用默认）"""
    try:
        if os.path.exists(CONFIG_FILE):
            cfg = json.load(open(CONFIG_FILE, encoding="utf-8"))
            # 合并默认（保证结构完整）
            merged = json.loads(json.dumps(DEFAULT_CONFIG))
            for k, v in cfg.items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k].update(v)
                else:
                    merged[k] = v
            return merged
    except Exception:
        pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg):
    """保存配置"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return True


def get_config_public():
    """脱敏后的配置（key 不显示实际内容，也不回显默认值）"""
    cfg = load_config()
    # 深拷贝，把 key 内容抹掉
    import copy
    pub = copy.deepcopy(cfg)

    def _hide(eng):
        if isinstance(eng, dict):
            if eng.get("key"):
                eng["key"] = "已配置(隐藏)"
            if eng.get("key_file"):
                eng["key_file"] = "已配置(隐藏)"

    # rewrite 是子引擎字典（primary/fallback），vision/asr 是单引擎，分别处理
    for eng in (pub.get("rewrite", {}) or {}).values():
        _hide(eng)
    _hide(pub.get("vision", {}))
    _hide(pub.get("asr", {}))
    return pub
