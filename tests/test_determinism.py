"""MC-T08: the same input gives the same reply - the digests, the
counts and the paths (the numbered output folder is the one mandated
difference between runs) - and verify_record answers match for an
untouched run and differs for a tampered one."""

from helpers import layer_for


def _strip_serial(payload) -> dict:
    """Copy the payload with the output-folder number normalized, so
    two runs compare equal on every deterministic field."""
    import copy
    data = copy.deepcopy(payload)
    serial = data.pop("output_dir", None)
    for key in ("handoff_files",):
        for entry in data.get(key) or []:
            entry["path"] = entry["path"].split("/", 1)[1]
    for entry in data.get("items") or []:
        if isinstance(entry.get("output"), str):
            entry["output"] = entry["output"].split("/", 1)[1]
    if isinstance(data.get("record_path"), str):
        data["record_path"] = data["record_path"].split("/", 1)[1]
    return data, serial


def test_mct08_prepare_is_deterministic(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    one = layer.call("prepare_for_sharing", {"path": "."})
    two = layer.call("prepare_for_sharing", {"path": "."})
    assert one["record_digest"] == two["record_digest"]
    assert one["record_digest"].startswith("sha256:")
    assert one["hidden_kinds"] == two["hidden_kinds"]
    assert one["items"] == two["items"]
    a, serial_a = _strip_serial(one)
    b, serial_b = _strip_serial(two)
    assert a == b
    assert serial_a != serial_b
    assert serial_a == "0001" and serial_b == "0002"


def test_mct08_prepare_of_one_file_is_deterministic(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    one = layer.call("prepare_for_sharing", {"path": "sample.txt"})
    two = layer.call("prepare_for_sharing", {"path": "sample.txt"})
    a, _s = _strip_serial(one)
    b, _t = _strip_serial(two)
    assert a == b
    assert one["record_digest"] == two["record_digest"]


def test_mct08_observe_and_manifest_are_deterministic(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    o1 = layer.call("observe_hidden_text", {"path": "."})
    o2 = layer.call("observe_hidden_text", {"path": "."})
    assert o1 == o2
    l1 = layer.call("create_file_list", {"path": "."})
    l2 = layer.call("create_file_list", {"path": "."})
    assert l1["file_count"] == l2["file_count"]
    assert l1["overall_sha256"] == l2["overall_sha256"]
    a, _s = _strip_serial(l1)
    b, _t = _strip_serial(l2)
    assert a == b


def test_mct08_clean_is_deterministic(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    c1 = layer.call("remove_metadata", {"path": "meta.png"})
    c2 = layer.call("remove_metadata", {"path": "meta.png"})
    assert c1["record_digest"] == c2["record_digest"]
    a, _s = _strip_serial(c1)
    b, _t = _strip_serial(c2)
    assert a == b


def test_mct08_verify_match_and_differs(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    prepared = layer.call("prepare_for_sharing", {"path": "."})
    out_name = prepared["output_dir"]
    verdict = layer.call(
        "verify_record",
        {"record": out_name + "/handoff/gate-receipt.json",
         "against": out_name})
    assert verdict["overall"] == "match"
    assert verdict["reasons"] == []
    # tamper one handoff file
    target = None
    for f in prepared["handoff_files"]:
        if f["path"].endswith("sample.txt.visible.txt"):
            target = out_dir / f["path"]
    assert target is not None
    original = target.read_bytes()
    target.write_bytes(b"tampered\n")
    verdict2 = layer.call(
        "verify_record",
        {"record": out_name + "/handoff/gate-receipt.json",
         "against": out_name})
    assert verdict2["overall"] == "differs"
    assert verdict2["reasons"][0]["reason"] == "output_changed"
    target.write_bytes(original)
    verdict3 = layer.call(
        "verify_record",
        {"record": out_name + "/handoff/gate-receipt.json",
         "against": out_name})
    assert verdict3["overall"] == "match"


def test_mct08_verify_of_the_file_list(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    listed = layer.call("create_file_list", {"path": "."})
    verdict = layer.call(
        "verify_record",
        {"record": listed["record_path"],
         "against": listed["output_dir"] + "/local/staging"})
    assert verdict["overall"] == "match"


def test_mct08_verify_clean_record(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    cleaned = layer.call("remove_metadata", {"path": "meta.png"})
    verdict = layer.call(
        "verify_record",
        {"record": cleaned["record_path"],
         "against": cleaned["output_dir"]})
    assert verdict["overall"] == "match"
