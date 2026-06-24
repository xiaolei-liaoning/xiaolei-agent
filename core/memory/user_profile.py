# core/memory/user_profile.py
"""用户画像 — 结构化存储用户身份、偏好、习惯"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class UserProfile:
    """用户画像 — 持久化为 JSON 文件"""

    def __init__(self, user_id: str, base_dir: str = None):
        self.user_id = user_id
        self._base_dir = base_dir or os.path.expanduser("~/.小雷版小龙虾/profiles")
        self._path = Path(self._base_dir) / f"{user_id}.json"
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("加载用户画像失败: %s", e)
        return {
            "user_id": self.user_id,
            "name": None,
            "facts": [],
            "preferences": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    def save(self) -> None:
        self._data["updated_at"] = datetime.now().isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except OSError as e:
            logger.error("保存用户画像失败: %s", e)

    @property
    def name(self) -> Optional[str]:
        return self._data.get("name")

    @name.setter
    def name(self, value: str):
        self._data["name"] = value
        self.save()

    @property
    def facts(self) -> List[Dict[str, Any]]:
        return self._data.get("facts", [])

    @property
    def preferences(self) -> List[Dict[str, Any]]:
        return self._data.get("preferences", [])

    def add_fact(self, content: str, category: str = "fact") -> bool:
        for f in self._data["facts"]:
            if f["content"] == content:
                return False
        self._data["facts"].append({
            "content": content,
            "category": category,
            "updated_at": datetime.now().isoformat(),
        })
        self.save()
        return True

    def add_preference(self, content: str) -> bool:
        for p in self._data["preferences"]:
            if p["content"] == content:
                return False
        self._data["preferences"].append({
            "content": content,
            "category": "preference",
            "updated_at": datetime.now().isoformat(),
        })
        self.save()
        return True

    def remove_fact(self, content_substring: str) -> bool:
        before = len(self._data["facts"])
        self._data["facts"] = [
            f for f in self._data["facts"]
            if content_substring not in f["content"]
        ]
        if len(self._data["facts"]) < before:
            self.save()
            return True
        return False

    def to_system_prompt_block(self) -> str:
        parts = []
        if self.name:
            parts.append(f"用户姓名: {self.name}")
        if self._data["facts"]:
            facts_str = "\n".join(f"- {f['content']}" for f in self._data["facts"][:20])
            parts.append(f"用户事实:\n{facts_str}")
        if self._data["preferences"]:
            prefs_str = "\n".join(f"- {p['content']}" for p in self._data["preferences"][:10])
            parts.append(f"用户偏好:\n{prefs_str}")
        if not parts:
            return ""
        return "【用户画像】\n" + "\n\n".join(parts)


_profiles: Dict[str, UserProfile] = {}


def get_user_profile(user_id: str) -> UserProfile:
    uid = str(user_id)
    if uid not in _profiles:
        _profiles[uid] = UserProfile(uid)
    return _profiles[uid]
