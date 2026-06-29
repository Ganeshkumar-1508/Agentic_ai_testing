from harness.db_helpers import build_patch_query


def test_builds_simple_update():
    sql, vals = build_patch_query("test_table", "id", "abc-123", {"name": "foo"}, {"name": "name"})
    assert sql == "UPDATE test_table SET name = $1, updated_at = NOW() WHERE id = $2"
    assert vals == ["foo", "abc-123"]


def test_builds_multiple_fields():
    sql, vals = build_patch_query("test_table", "id", "abc", {"name": "foo", "enabled": True}, {"name": "name", "enabled": "enabled"})
    assert vals[:2] == ["foo", True]
    assert len(vals) == 3  # +1 for id
    assert vals[2] == "abc"


def test_returns_empty_for_no_matches():
    sql, vals = build_patch_query("test_table", "id", "x", {"other": "val"}, {"name": "name"})
    assert sql == ""
    assert vals == []


def test_json_field_serialization():
    sql, vals = build_patch_query("test", "id", "1", {"cfg": {"key": "val"}}, {"cfg": "cfg"}, json_fields=["cfg"])
    assert vals[0] == '{"key": "val"}'


def test_returns_empty_for_empty_req():
    sql, vals = build_patch_query("t", "id", "1", {}, {"x": "x"})
    assert sql == ""
    assert vals == []
