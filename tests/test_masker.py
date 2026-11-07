"""
mcp-server-rdbms: 动态数据脱敏器单元测试.

@author Ateng
@since 2026-11-07
"""

from decimal import Decimal

from atengk_mcp_server_rdbms.core.masker import DynamicDataMasker


def test_credential_columns_full_mask():
    """测试高危凭据列名全掩码为 ******."""
    masker = DynamicDataMasker()
    row = {
        "password": "plain_password_123",
        "passwd": "hash$123456",
        "pwd": "mypassword",
        "secret": "my_jwt_secret",
        "token": "bearer_abc123",
        "api_key": "custom_api_key",
        "apikey": "another_key",
        "secret_key": "sec_key",
        "private_key": "priv_key",
        "access_key": "acc_key",
        "auth_key": "auth_key",
        "client_secret": "c_sec",
        "credential": "cred",
        "salt": "random_salt",
    }
    masked, cols = masker.mask_row(row)
    for col_name in row:
        assert masked[col_name] == "******"
        assert col_name in cols


def test_status_and_count_columns_exemption():
    """测试具有状态、计数等后缀的衍生列免受凭据全掩码误杀."""
    masker = DynamicDataMasker()
    row = {
        "token_count": 42,
        "is_password_reset": True,
        "has_token": False,
        "password_status": 1,
        "token_num": 5,
        "secret_type": "rsa",
        "phone_type": "mobile",
        "password_flag": 0,
        "token_time": "2026-11-07T12:00:00",
        "password_updated_at": "2026-11-07",
    }
    masked, cols = masker.mask_row(row)
    assert masked == row
    assert cols == []


def test_no_wide_single_word_key():
    """测试常规包含 key 的业务列不被当作凭据列全掩码."""
    masker = DynamicDataMasker()
    row = {
        "sort_key": "asc",
        "partition_key": "p1",
        "cache_key": "user:1001",
        "foreign_key": "fk_id",
        "key": "idx_name",
    }
    masked, cols = masker.mask_row(row)
    assert masked == row
    assert cols == []


def test_privacy_columns_and_value_patterns():
    """测试个人隐私列及值内容特征正则局部保留脱敏."""
    masker = DynamicDataMasker()
    row = {
        "phone": "13812345678",
        "mobile": "15900001111",
        "tel": "18888889999",
        "id_card": "110101199003072345",
        "id_card_15": "110101900307234",
        "email": "zhangsan@example.com",
        "bank_card": "6222021234567890",
        "bigint_phone": 13912345678,
    }
    masked, cols = masker.mask_row(row)
    assert masked["phone"] == "138****5678"
    assert masked["mobile"] == "159****1111"
    assert masked["tel"] == "188****9999"
    assert masked["id_card"] == "110101********2345"
    assert masked["id_card_15"] == "110101*****7234"
    assert masked["email"] == "z***@example.com"
    assert masked["bank_card"] == "6222********7890"
    assert masked["bigint_phone"] == "139****5678"
    assert len(cols) == len(row)


def test_column_alias_bypass_protection():
    """测试使用 SELECT col AS col1 别名重命名时仍能通过值特征正则嗅探并脱敏."""
    masker = DynamicDataMasker()
    row = {
        "col1": "13800138000",
        "col2": "admin@sub.company.org",
        "col3": "sk-proj-1234567890abcdefg",
        "col4": "Bearer secret_jwt_token_123",
        "col5": "ghp_1234567890abcdefghij",
    }
    masked, cols = masker.mask_row(row)
    assert masked["col1"] == "138****8000"
    assert masked["col2"] == "a***@sub.company.org"
    assert masked["col3"] == "sk-***"
    assert masked["col4"] == "Bearer ***"
    assert masked["col5"] == "ghp_***"
    assert set(cols) == {"col1", "col2", "col3", "col4", "col5"}


def test_standard_types_exemption_in_default_rules():
    """测试内置规则下普通短整数、浮点数、布尔值与空值免于误脱敏."""
    masker = DynamicDataMasker()
    row = {
        "id": 101,
        "score": 98.5,
        "ratio": Decimal("0.75"),
        "is_active": True,
        "remark": None,
    }
    masked, cols = masker.mask_row(row)
    assert masked == row
    assert cols == []


def test_custom_mask_columns():
    """测试用户自定义 mask_columns，包含通配符匹配、数值强制掩码与自适应字符串掩码."""
    row = {
        "salary_base": 28500.50,
        "salary_bonus": Decimal("5000.00"),
        "real_name_1": "张",
        "real_name_2": "李四",
        "real_name_3": "王小二",
        "home_address": "北京市海淀区中关村南大街1号",
    }
    masker = DynamicDataMasker(mask_columns=("salary_*", "*name*", "home_address"))
    masked, cols = masker.mask_row(row)

    # 数值类型在自定义列中不豁免，直接掩码为 ******
    assert masked["salary_base"] == "******"
    assert masked["salary_bonus"] == "******"

    # 自适应字符串脱敏
    assert masked["real_name_1"] == "*"
    assert masked["real_name_2"] == "李*"
    assert masked["real_name_3"] == "王*二"
    assert masked["home_address"] == "北京****1号"
    assert set(cols) == {"salary_base", "salary_bonus", "real_name_1", "real_name_2", "real_name_3", "home_address"}


def test_nested_containers_and_json_string_masking():
    """测试嵌套字典、列表及 JSON 字符串穿透脱敏."""
    masker = DynamicDataMasker()
    row = {
        "user_profile": {
            "name": "alice",
            "phone": "13800138000",
            "auth": {"password": "pwd"},
        },
        "contacts": [
            {"email": "contact@example.com"},
            "13911112222",
        ],
        "json_text": '{"token": "xyz", "phone": "13700001111", "status": "ok"}',
    }
    masked, cols = masker.mask_row(row)
    assert masked["user_profile"]["phone"] == "138****8000"
    assert masked["user_profile"]["auth"]["password"] == "******"
    assert masked["contacts"][0]["email"] == "c***@example.com"
    assert masked["contacts"][1] == "139****2222"

    import json
    parsed_json = json.loads(masked["json_text"])
    assert parsed_json["token"] == "******"
    assert parsed_json["phone"] == "137****1111"
    assert parsed_json["status"] == "ok"

    assert set(cols) == {"user_profile", "contacts", "json_text"}


def test_explain_mode_skips_column_name_masking():
    """测试 explain 模式跳过列名脱敏，防止把 MySQL EXPLAIN key 索引列误掩码."""
    masker = DynamicDataMasker()
    row = {
        "id": 1,
        "select_type": "SIMPLE",
        "table": "users",
        "type": "const",
        "possible_keys": "PRIMARY",
        "key": "PRIMARY",
        "key_len": "4",
        "ref": "const",
        "rows": 1,
        "Extra": "",
    }
    # 在 explain 模式下执行
    masked, cols = masker.mask_row(row, is_explain=True)
    assert masked["key"] == "PRIMARY"
    assert cols == []


def test_mask_disabled():
    """测试 mask_enabled=False 时原样返回不脱敏."""
    masker = DynamicDataMasker(enabled=False)
    row = {
        "password": "secret_password",
        "phone": "13800138000",
    }
    masked, cols = masker.mask_row(row)
    assert masked == row
    assert cols == []
