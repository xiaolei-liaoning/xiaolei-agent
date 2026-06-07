"""
SchemaValidator — 轻量 JSON Schema 校验器

支持：
  - type 校验 (string/number/integer/boolean/array/object)
  - required fields
  - nested properties
  - enum
  - array items type + minItems/maxItems
  - minimum/maximum (数字范围)
  - minLength/maxLength (字符串长度)
  - pattern (正则)

不依赖 jsonschema 等外部库，自实现。
"""

import re
from typing import Any, Dict, List, Tuple


class SchemaValidator:
    """轻量 JSON Schema 校验器"""

    TYPE_MAP: Dict[str, Any] = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    def validate(self, instance: Any, schema: Dict) -> Tuple[bool, List[str]]:
        """校验实例是否符合 schema，返回 (通过?, 错误列表)"""
        errors: List[str] = []
        self._validate(instance, schema, errors, "$")
        return (len(errors) == 0), errors

    def _validate(self, value: Any, schema: Dict, errors: List[str], path: str) -> None:
        """递归校验入口"""
        # ── type 校验 ──
        if "type" in schema:
            expected = self.TYPE_MAP.get(schema["type"])
            if expected and not isinstance(value, expected):
                # number 对 int 宽松接纳
                if not (schema["type"] == "number" and isinstance(value, int)):
                    errors.append(
                        f"{path}: 期望 {schema['type']}，实际 {type(value).__name__}"
                    )

        # ── enum 校验 ──
        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: 值不在允许范围内 {schema['enum']}")

        # ── 按类型递归校验 ──
        if isinstance(value, dict):
            self._validate_object(value, schema, errors, path)
        elif isinstance(value, list):
            self._validate_array(value, schema, errors, path)
        elif isinstance(value, str):
            self._validate_string(value, schema, errors, path)
        elif isinstance(value, (int, float)):
            self._validate_number(value, schema, errors, path)

    def _validate_object(self, obj: Dict, schema: Dict, errors: List[str], path: str) -> None:
        """object 类型深度校验"""
        props = schema.get("properties", {})
        required = schema.get("required", [])

        # 检查必填字段
        for field in required:
            if field not in obj:
                errors.append(f"{path}.{field}: 缺少必填字段")

        # 递归校验每个属性
        for key, field_schema in props.items():
            if key in obj:
                self._validate(obj[key], field_schema, errors, f"{path}.{key}")

    def _validate_array(self, arr: List, schema: Dict, errors: List[str], path: str) -> None:
        """array 类型校验"""
        # minItems
        if "minItems" in schema and len(arr) < schema["minItems"]:
            errors.append(
                f"{path}: 最少 {schema['minItems']} 项，实际 {len(arr)} 项"
            )
        # maxItems
        if "maxItems" in schema and len(arr) > schema["maxItems"]:
            errors.append(
                f"{path}: 最多 {schema['maxItems']} 项，实际 {len(arr)} 项"
            )
        # items type
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(arr):
                self._validate(item, item_schema, errors, f"{path}[{i}]")

    def _validate_string(self, s: str, schema: Dict, errors: List[str], path: str) -> None:
        """string 类型校验"""
        # minLength
        if "minLength" in schema and len(s) < schema["minLength"]:
            errors.append(
                f"{path}: 最短 {schema['minLength']} 字符，实际 {len(s)} 字符"
            )
        # maxLength
        if "maxLength" in schema and len(s) > schema["maxLength"]:
            errors.append(
                f"{path}: 最长 {schema['maxLength']} 字符，实际 {len(s)} 字符"
            )
        # pattern
        if "pattern" in schema:
            if not re.match(schema["pattern"], s):
                errors.append(f"{path}: 不匹配正则 {schema['pattern']}")

    def _validate_number(self, n: float, schema: Dict, errors: List[str], path: str) -> None:
        """number/integer 类型校验"""
        # minimum
        if "minimum" in schema and n < schema["minimum"]:
            errors.append(f"{path}: {n} 小于最小值 {schema['minimum']}")
        # maximum
        if "maximum" in schema and n > schema["maximum"]:
            errors.append(f"{path}: {n} 大于最大值 {schema['maximum']}")

    def build_prompt_hint(self, schema: Dict) -> str:
        """将 JSON Schema 转为 LLM 友好的输出格式指令"""
        props = schema.get("properties", {})
        required = schema.get("required", [])

        lines = ["请只输出一个 JSON 对象，不要额外文字，不要 markdown 代码块。"]

        for name, prop in props.items():
            req = "必填" if name in required else "可选"
            desc = prop.get("description", prop.get("type", "未知"))
            lines.append(f"  - {name}（{req}）：{desc}")

        lines.append("直接输出 JSON：")
        return "\n".join(lines)
