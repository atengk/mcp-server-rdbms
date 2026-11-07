"""
mcp-server-rdbms: 动态数据脱敏器核心引擎 (Dynamic Data Masker).

@author Ateng
@since 2026-11-07
"""

import fnmatch
import json
import re
from decimal import Decimal
from typing import Any


class DynamicDataMasker:
    """动态数据脱敏器：基于列名匹配与值内容特征嗅探的双模驱动脱敏引擎.

    @author Ateng
    @since 2026-11-07
    """

    # 内置高危凭据列名词素（全掩码为 ******）
    CREDENTIAL_KEYWORDS: frozenset[str] = frozenset({
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "secret_key",
        "private_key",
        "access_key",
        "auth_key",
        "client_secret",
        "credential",
        "salt",
    })

    # 状态/计数列豁免词缀（前缀与后缀）
    EXEMPT_PREFIXES: tuple[str, ...] = ("is_", "has_")
    EXEMPT_SUFFIXES: tuple[str, ...] = (
        "_count",
        "_num",
        "_status",
        "_state",
        "_type",
        "_flag",
        "_time",
        "_at",
        "_date",
    )

    # 内置个人隐私列名词素
    PRIVACY_KEYWORDS: frozenset[str] = frozenset({
        "phone",
        "mobile",
        "tel",
        "id_card",
        "identity_card",
        "id_no",
        "email",
        "bank_card",
        "card_no",
    })

    # 预编译正则特征
    # 1. 中国大陆手机号（11位，前3后4）
    _RE_PHONE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
    # 2. 中国大陆身份证号（18位/15位）
    _RE_ID_CARD_18 = re.compile(r"(?<!\d)([1-9]\d{5})\d{8}(\d{3}[\dXx])(?!\d)")
    _RE_ID_CARD_15 = re.compile(r"(?<!\d)([1-9]\d{5})\d{5}(\d{4})(?!\d)")
    # 3. 电子邮箱
    _RE_EMAIL = re.compile(r"(?i)\b([a-z0-9_.+-])[a-z0-9_.+-]*(@[a-z0-9-]+(?:\.[a-z0-9-]+)+)\b")
    # 4. 银行卡号（16~19位数字）
    _RE_BANK_CARD = re.compile(r"(?<!\d)(\d{4})\d{8,11}(\d{4})(?!\d)")
    # 5. 高危密钥字面量
    _RE_SK = re.compile(r"(?<!\w)(sk-[A-Za-z0-9_-]{12,})(?!\w)")
    _RE_GHP = re.compile(r"(?<!\w)(ghp_[A-Za-z0-9]{16,})(?!\w)")
    _RE_AKIA = re.compile(r"(?<!\w)(AKIA[0-9A-Z]{16})(?!\w)")
    _RE_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
    _RE_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")

    # SQL 语句与日志中常见键值赋值及报错搭配正则
    _RE_SQL_ASSIGN = re.compile(
        r"(?i)\b(password|passwd|pwd|secret|token|api_key|apikey|secret_key|private_key|access_key|auth_key|client_secret|credential|salt)\s*(=|:=|=>)\s*('[^']*'|\"[^\"]*\"|[^\s,;)]+)"
    )
    _RE_JSON_KEY_VAL = re.compile(
        r"(?i)(\"(?:password|passwd|pwd|secret|token|api_key|apikey|secret_key|private_key|access_key|auth_key|client_secret|credential|salt)\")\s*:\s*(\"[^\"]*\"|'[^']*'|[^\s,}]+)"
    )
    _RE_KEYWORD_VAL = re.compile(
        r"(?i)\b(password|passwd|pwd|secret|token)\s+('[^']*'|\"[^\"]*\")"
    )
    _RE_INSERT_STMT = re.compile(
        r"(?i)\bINSERT\s+INTO\s+[^(]+\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
        re.DOTALL,
    )

    def __init__(
        self,
        enabled: bool = True,
        mask_columns: tuple[str, ...] | list[str] = (),
    ) -> None:
        """初始化动态数据脱敏器.

        @param enabled: 是否启用脱敏（默认 True）
        @param mask_columns: 用户显式配置的敏感列模式元组
        """
        self.enabled = enabled
        self.mask_columns: tuple[str, ...] = tuple(
            c.strip() for c in mask_columns if c and c.strip()
        )
        self._custom_assign_res: list[re.Pattern[str]] = []
        self._custom_json_res: list[re.Pattern[str]] = []
        if self.mask_columns:
            for col in self.mask_columns:
                if "*" not in col and "?" not in col:
                    col_esc = re.escape(col)
                    self._custom_assign_res.append(
                        re.compile(
                            rf"(?i)\b({col_esc})\s*(=|:=|=>)\s*('[^']*'|\"[^\"]*\"|[^\s,;)]+)"
                        )
                    )
                    self._custom_json_res.append(
                        re.compile(
                            rf'(?i)("?{col_esc}"?)\s*:\s*("[^"]*"|\'[^\']*\'|[^\s,}}]+)'
                        )
                    )

    @classmethod
    def adaptive_mask_string(cls, val: str) -> str:
        """自适应首尾保留掩码算法.

        @param val: 待脱敏字符串
        @return: 掩码处理后的安全字符串
        """
        length = len(val)
        if length == 0:
            return ""
        if length == 1:
            return "*"
        if length == 2:
            return val[0] + "*"
        if 3 <= length <= 6:
            return val[0] + "*" * (length - 2) + val[-1]
        return val[:2] + "****" + val[-2:]

    def matches_custom_column(self, col_name: str) -> bool:
        """检查列名是否命中用户自定义 mask_columns 配置.

        @param col_name: 待检测列名
        @return: True 为命中自定义配置，False 为未命中
        """
        if not self.mask_columns:
            return False
        col_clean = col_name.strip().lower()
        for pat in self.mask_columns:
            pat_clean = pat.lower()
            if "*" in pat_clean or "?" in pat_clean:
                if fnmatch.fnmatchcase(col_clean, pat_clean):
                    return True
            else:
                if (
                    pat_clean == col_clean
                    or f"_{pat_clean}" in col_clean
                    or f"{pat_clean}_" in col_clean
                ):
                    return True
        return False

    def is_credential_column(self, col_name: str) -> bool:
        """检查列名是否为内置高危凭据列（排查状态/计数词缀与宽泛单字 key）.

        @param col_name: 待检测列名
        @return: True 为凭据列，False 为否
        """
        col_clean = col_name.strip().lower()

        # 检查是否包含状态、计数等豁免词缀
        if any(col_clean.startswith(p) for p in self.EXEMPT_PREFIXES):
            return False
        if any(col_clean.endswith(s) for s in self.EXEMPT_SUFFIXES):
            return False

        # 分词或词素匹配
        # 特别排查：禁用裸词 key（如 key, sort_key, foreign_key, cache_key 等）
        for kw in self.CREDENTIAL_KEYWORDS:
            if kw == col_clean or f"_{kw}" in col_clean or f"{kw}_" in col_clean:
                return True
        return False

    def is_privacy_column(self, col_name: str) -> bool:
        """检查列名是否为内置个人隐私列.

        @param col_name: 待检测列名
        @return: True 为隐私列，False 为否
        """
        col_clean = col_name.strip().lower()

        # 检查是否包含状态、计数等豁免词缀
        if any(col_clean.startswith(p) for p in self.EXEMPT_PREFIXES):
            return False
        if any(col_clean.endswith(s) for s in self.EXEMPT_SUFFIXES):
            return False

        for kw in self.PRIVACY_KEYWORDS:
            if kw == col_clean or f"_{kw}" in col_clean or f"{kw}_" in col_clean:
                return True
        return False

    def mask_text_patterns(self, text_val: str) -> str:
        """对纯文本内容运行正则特征嗅探并执行局部掩码.

        @param text_val: 原始文本字符串
        @return: 经正则脱敏后的文本
        """
        res = text_val

        # 1. PEM 私钥块
        res = self._RE_PEM.sub("-----BEGIN PRIVATE KEY...***", res)
        # 2. Bearer 令牌
        res = self._RE_BEARER.sub("Bearer ***", res)
        # 3. 常见 API Key 前缀字面量
        res = self._RE_SK.sub("sk-***", res)
        res = self._RE_GHP.sub("ghp_***", res)
        res = self._RE_AKIA.sub("AKIA***", res)

        # 4. 电子邮箱
        res = self._RE_EMAIL.sub(r"\1***\2", res)

        # 5. 身份证号（18位 / 15位）
        res = self._RE_ID_CARD_18.sub(r"\1********\2", res)
        res = self._RE_ID_CARD_15.sub(r"\1*****\2", res)

        # 6. 银行卡号（16-19位）
        def _mask_bank(match: re.Match[str]) -> str:
            full = match.group(0)
            return full[:4] + "*" * (len(full) - 8) + full[-4:]

        res = self._RE_BANK_CARD.sub(_mask_bank, res)

        # 7. 手机号（11位）
        res = self._RE_PHONE.sub(r"\1****\2", res)

        return res

    def sanitize_sql_or_error_text(self, text_val: str) -> str:
        """对 SQL 语句或异常错误文本中的敏感字面量执行净化脱敏.

        @param text_val: 待净化的 SQL 语句或错误描述文本
        @return: 净化后的安全文本
        """
        if not self.enabled or not text_val:
            return text_val

        res = text_val

        # 1. 净化通用赋值语句中的凭据字面量 (如 password = '...', secret := '...')
        res = self._RE_SQL_ASSIGN.sub(r"\1 \2 '******'", res)

        # 2. 净化 JSON 文本中的凭据字面量 (如 "password": "...")
        res = self._RE_JSON_KEY_VAL.sub(r'\1: "******"', res)

        # 3. 净化自然语言/错误信息中的凭据搭配 (如 password '...')
        res = self._RE_KEYWORD_VAL.sub(r"\1 '******'", res)

        # 4. 净化 INSERT INTO 语句中按列名位置映射的字面量
        def _mask_insert(match: re.Match[str]) -> str:
            full_match = match.group(0)
            cols_str = match.group(1)
            vals_str = match.group(2)
            cols = [c.strip().strip('`"[]') for c in cols_str.split(",")]
            vals = [v.strip() for v in vals_str.split(",")]
            if len(cols) != len(vals):
                return full_match
            changed = False
            for i, col in enumerate(cols):
                if self.is_credential_column(col) or self.matches_custom_column(col):
                    vals[i] = "'******'"
                    changed = True
            if changed:
                new_vals = ", ".join(vals)
                return full_match.replace(match.group(2), new_vals, 1)
            return full_match

        res = self._RE_INSERT_STMT.sub(_mask_insert, res)

        # 5. 针对用户自定义敏感列预编译正则的 SQL 赋值处理
        if self._custom_assign_res:
            for custom_re in self._custom_assign_res:
                res = custom_re.sub(r"\1 \2 '******'", res)
        if self._custom_json_res:
            for custom_json_re in self._custom_json_res:
                res = custom_json_re.sub(r'\1: "******"', res)

        # 6. 净化文本中内嵌的值内容特征 (手机号、身份证、邮箱、银行卡、API密钥)
        res = self.mask_text_patterns(res)

        return res

    def mask_value(
        self,
        val: Any,
        col_name: str | None = None,
        is_explain: bool = False,
    ) -> tuple[Any, bool]:
        """对单个单元格值执行脱敏.

        @param val: 原始单元格数据
        @param col_name: 所属列名（可选）
        @param is_explain: 是否执行计划模式（该模式下跳过列名脱敏）
        @return: (脱敏后的值, 是否发生脱敏变化)
        """
        if not self.enabled or val is None:
            return val, False

        # 1. 检查是否命中用户显式指定的自定义 mask_columns
        if col_name and not is_explain and self.matches_custom_column(col_name):
            # 自定义列不豁免数值（包含 Decimal），数值直接全掩码
            if isinstance(val, (int, float, Decimal)) and not isinstance(val, bool):
                return "******", True
            if isinstance(val, str):
                # 先尝试正则脱敏，如果正则未改变则采用自适应字符串脱敏
                regex_masked = self.mask_text_patterns(val)
                if regex_masked != val:
                    return regex_masked, True
                return self.adaptive_mask_string(val), True

        # 2. 检查内置高危凭据列名全掩码
        if col_name and not is_explain and self.is_credential_column(col_name):
            return "******", True

        # 3. 检查数值类型（针对手机号、银行卡号与身份证号 BIGINT/NUMERIC 的支持）
        if isinstance(val, int) and not isinstance(val, bool):
            val_str = str(val)
            # 11 位手机号
            if len(val_str) == 11 and val_str.startswith(("13", "14", "15", "16", "17", "18", "19")):
                masked_phone = f"{val_str[:3]}****{val_str[7:]}"
                return masked_phone, True
            # 16~19 位银行卡号
            if 16 <= len(val_str) <= 19:
                masked_card = f"{val_str[:4]}{'*' * (len(val_str) - 8)}{val_str[-4:]}"
                return masked_card, True
            # 18 位身份证号
            if len(val_str) == 18 and val_str[0] in "123456789":
                masked_id = f"{val_str[:6]}********{val_str[-4:]}"
                return masked_id, True
            # 15 位身份证号
            if len(val_str) == 15 and val_str[0] in "123456789":
                masked_id = f"{val_str[:6]}*****{val_str[-4:]}"
                return masked_id, True
            # 短整数默认放行
            return val, False

        # 4. 布尔值与浮点数在内置规则下豁免放行
        if isinstance(val, (bool, float)):
            return val, False

        # 5. 递归处理原生 dict
        if isinstance(val, dict):
            changed = False
            masked_dict: dict[str, Any] = {}
            for k, v in val.items():
                m_v, c = self.mask_value(v, col_name=str(k), is_explain=is_explain)
                masked_dict[k] = m_v
                if c:
                    changed = True
            return masked_dict, changed

        # 6. 递归处理原生 list / tuple / set
        if isinstance(val, (list, tuple, set)):
            changed = False
            masked_list: list[Any] = []
            for item in val:
                m_item, c = self.mask_value(item, col_name=None, is_explain=is_explain)
                masked_list.append(m_item)
                if c:
                    changed = True
            if isinstance(val, tuple):
                return tuple(masked_list), changed
            if isinstance(val, set):
                return set(masked_list), changed
            return masked_list, changed

        # 7. 字符串处理（尝试穿透 JSON 格式字符串，否则执行正则与自适应脱敏）
        if isinstance(val, str):
            clean_str = val.strip()
            # 穿透 JSON 字符串
            if (clean_str.startswith("{") and clean_str.endswith("}")) or (
                clean_str.startswith("[") and clean_str.endswith("]")
            ):
                try:
                    parsed = json.loads(val)
                    masked_parsed, changed = self.mask_value(
                        parsed, col_name=col_name, is_explain=is_explain
                    )
                    if changed:
                        return json.dumps(masked_parsed, ensure_ascii=False), True
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass

            # 运行文本正则特征嗅探
            masked_text = self.mask_text_patterns(val)
            if masked_text != val:
                return masked_text, True

            # 若列名命中隐私列名，但值没有匹配到特种正则（如非标手机号/卡号），自适应兜底
            if col_name and not is_explain and self.is_privacy_column(col_name):
                return self.adaptive_mask_string(val), True

            return val, False

        # 8. 其余对象保持原样
        return val, False

    def mask_row(
        self,
        row: dict[str, Any],
        is_explain: bool = False,
    ) -> tuple[dict[str, Any], list[str]]:
        """对单行字典数据执行脱敏，并返回被脱敏的顶层列名列表.

        @param row: 单行原始字典数据
        @param is_explain: 是否执行计划模式
        @return: (脱敏后的单行字典, 发生脱敏的顶层列名列表)
        """
        if not self.enabled or not row:
            return row, []

        masked_row: dict[str, Any] = {}
        masked_columns: list[str] = []

        for col_name, val in row.items():
            masked_val, changed = self.mask_value(
                val, col_name=col_name, is_explain=is_explain
            )
            masked_row[col_name] = masked_val
            if changed and col_name not in masked_columns:
                masked_columns.append(col_name)

        return masked_row, masked_columns

    def mask_rows(
        self,
        rows: list[dict[str, Any]],
        is_explain: bool = False,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """批量脱敏行数据字典列表，并聚合所有发生脱敏的顶层列名（去重保序）.

        @param rows: 原始行字典列表
        @param is_explain: 是否执行计划模式
        @return: (脱敏后的行字典列表, 全部发生脱敏的顶层列名列表)
        """
        if not self.enabled or not rows:
            return rows, []

        all_masked_columns: list[str] = []
        masked_rows: list[dict[str, Any]] = []

        for row in rows:
            m_row, m_cols = self.mask_row(row, is_explain=is_explain)
            masked_rows.append(m_row)
            for c in m_cols:
                if c not in all_masked_columns:
                    all_masked_columns.append(c)

        return masked_rows, all_masked_columns
