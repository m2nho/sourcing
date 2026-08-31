"""설치 프로그램의 순수 로직. 실제 설치는 Windows에서 돌지만 이 부분은 어디서나 검증된다."""

import pytest

from installer.setup import (
    codex_config_block,
    merge_codex_config,
    to_toml_path,
)


def test_windows_path_uses_forward_slashes():
    # TOML에서 역슬래시는 이스케이프 문자라 그대로 쓰면 깨진다
    assert to_toml_path(r"C:\Users\me\sourcing") == "C:/Users/me/sourcing"


def test_forward_slash_path_is_left_alone():
    assert to_toml_path("C:/Users/me/sourcing") == "C:/Users/me/sourcing"


def test_config_block_points_at_the_install_dir():
    block = codex_config_block(r"C:\Users\me\sourcing")
    assert "[mcp_servers.sourcing]" in block
    assert 'command = "uv"' in block
    assert '"C:/Users/me/sourcing"' in block
    assert "sourcing-mcp" in block


def test_merge_into_empty_config_adds_the_block():
    merged = merge_codex_config("", r"C:\Users\me\sourcing")
    assert merged is not None
    assert "[mcp_servers.sourcing]" in merged


def test_merge_preserves_other_servers():
    existing = '[mcp_servers.other]\ncommand = "node"\nargs = ["server.js"]\n'
    merged = merge_codex_config(existing, r"C:\Users\me\sourcing")
    assert merged is not None
    assert "[mcp_servers.other]" in merged
    assert 'command = "node"' in merged
    assert "[mcp_servers.sourcing]" in merged


def test_merge_preserves_unrelated_settings():
    existing = 'model = "gpt-5"\napproval_policy = "on-request"\n'
    merged = merge_codex_config(existing, r"C:\Users\me\sourcing")
    assert merged is not None
    assert 'model = "gpt-5"' in merged
    assert 'approval_policy = "on-request"' in merged


def test_merge_returns_none_when_already_registered():
    existing = codex_config_block(r"C:\Users\me\sourcing")
    assert merge_codex_config(existing, r"C:\Users\me\sourcing") is None


def test_merge_detects_existing_entry_even_with_different_path():
    # 이미 등록돼 있으면 경로가 달라도 덮어쓰지 않는다 - 사용자 설정이 우선이다
    existing = codex_config_block(r"D:\elsewhere")
    assert merge_codex_config(existing, r"C:\Users\me\sourcing") is None


def test_merge_refuses_to_touch_a_broken_config():
    # 망가진 TOML을 덮어쓰면 사용자의 다른 설정을 잃는다. 손대지 않는다.
    with pytest.raises(ValueError):
        merge_codex_config("[[[ this is not toml", r"C:\Users\me\sourcing")


def test_merged_config_is_valid_toml():
    import tomllib

    merged = merge_codex_config('model = "gpt-5"\n', r"C:\Users\me\sourcing")
    parsed = tomllib.loads(merged)
    assert parsed["mcp_servers"]["sourcing"]["command"] == "uv"
    assert "C:/Users/me/sourcing" in parsed["mcp_servers"]["sourcing"]["args"]
