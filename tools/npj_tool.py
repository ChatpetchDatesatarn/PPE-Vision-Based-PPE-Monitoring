#!/usr/bin/env python3
"""Read and edit CiRA CORE .npj flow files from the terminal (Python 3.6, standard library only).

A .npj is JSON (Qt QJsonDocument, indented): {"scene_array": [{"name": ..., "data": "<inner JSON as a string>"}]}.
Each scene's "data" is itself a JSON document (connections / nodes / scene_data). Nodes keep their settings under
node["model"]: a JavaScript node in model["data"]["js_code"], an MqttPub/MqttSub node in model["mqtt_pub"] /
model["mqtt_sub"]. This tool parses both layers and serialises them back exactly the way CiRA writes them
(indent=4, sorted keys, UTF-8, trailing newline), so it never edits the escaped strings by hand.

Commands:
  npj_tool.py list   <file.npj>                      show every node: type, id, key settings
  npj_tool.py get-js <file.npj> <node>               print a JavaScript node's js_code to stdout
  npj_tool.py set-js <file.npj> <node> <in.js>       put in.js into a JavaScript node's js_code (writes the file)
  npj_tool.py set    <file.npj> <node> <field> <val> set a field of an MqttPub/MqttSub/AutoRun node (writes the file)
  npj_tool.py del-node <file.npj> <node>             remove a node and every connection touching it (writes the file)

<node> is the node type name (MqttPub, MqttSub, JavaScript) when only one node has it, otherwise the node id
"{uuid}" (braces optional). Writing always backs up to <file>.npj.bak-YYYYMMDD-HHMMSS first.
"""
import json
import os
import shutil
import sys
import time

INDENT = 4
# the sub-dict of node["model"] that holds a node's settings, by node type name
MODEL_KEY = {"MqttPub": "mqtt_pub", "MqttSub": "mqtt_sub", "JavaScript": "data"}
INT_FIELDS = {"port", "qos"}
BOOL_FIELDS = {"is_use_ssl", "is_use_cert", "send_img", "node_enable"}


def dumps(obj):
    """Exactly how CiRA (Qt) writes a JSON document: 4-space indent, sorted keys, raw UTF-8, trailing newline."""
    return json.dumps(obj, indent=INDENT, sort_keys=True, ensure_ascii=False) + "\n"


def load(path):
    with open(path, encoding="utf-8") as f:
        outer = json.load(f)
    scenes = []
    for si, scene in enumerate(outer["scene_array"]):
        scenes.append(json.loads(scene["data"]))
    return outer, scenes


def iter_nodes(scenes):
    """Yield (scene_index, node_index, node) for every node in every scene."""
    for si, inner in enumerate(scenes):
        for ni, node in enumerate(inner.get("nodes", [])):
            yield si, ni, node


def node_type(node):
    return node.get("model", {}).get("name")


def norm_id(s):
    s = s.strip()
    return s if s.startswith("{") else "{" + s + "}"


def find_node(scenes, selector):
    """Return (scene_index, node_index, node) for selector = a node id ({uuid}) or a unique type name."""
    want_id = norm_id(selector)
    by_id = [(si, ni, n) for si, ni, n in iter_nodes(scenes) if n.get("id") == want_id]
    if by_id:
        return by_id[0]
    by_name = [(si, ni, n) for si, ni, n in iter_nodes(scenes) if node_type(n) == selector]
    if not by_name:
        raise SystemExit("node not found: %s (not an id and no node of that type)" % selector)
    if len(by_name) > 1:
        ids = ", ".join(n.get("id", "?") for _, _, n in by_name)
        raise SystemExit("%d nodes of type %s; use the id instead: %s" % (len(by_name), selector, ids))
    return by_name[0]


def write_back(path, outer, scenes):
    """Re-serialise each scene's inner JSON into its "data" string, back up, then write the file."""
    for si, inner in enumerate(scenes):
        outer["scene_array"][si]["data"] = dumps(inner)
    # millisecond suffix so two writes in the same second do not overwrite each other's backup
    now = time.time()
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) + "-%03d" % int((now % 1) * 1000)
    bak = "%s.bak-%s" % (path, stamp)
    shutil.copy2(path, bak)
    # newline="\n": never let Windows text mode turn \n into \r\n (CiRA writes LF)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(dumps(outer))
    return bak


def cmd_list(path):
    _, scenes = load(path)
    for si, ni, node in iter_nodes(scenes):
        t = node_type(node)
        nid = node.get("id", "?")
        model = node.get("model", {})
        extra = ""
        if t in ("MqttPub", "MqttSub"):
            m = model.get(MODEL_KEY[t], {})
            extra = "host=%s port=%s qos=%s topic=%s" % (m.get("host"), m.get("port"), m.get("qos"), m.get("topic"))
        elif t == "JavaScript":
            code = model.get("data", {}).get("js_code", "")
            extra = "js_code: %d chars, %d lines" % (len(code), code.count("\n") + 1 if code else 0)
        print("scene %d  %-11s %s  %s" % (si, t, nid, extra))


def cmd_get_js(path, selector):
    _, scenes = load(path)
    _, _, node = find_node(scenes, selector)
    if node_type(node) != "JavaScript":
        raise SystemExit("node %s is %s, not JavaScript" % (selector, node_type(node)))
    sys.stdout.write(node["model"]["data"]["js_code"])


def cmd_set_js(path, selector, js_path):
    outer, scenes = load(path)
    si, ni, node = find_node(scenes, selector)
    if node_type(node) != "JavaScript":
        raise SystemExit("node %s is %s, not JavaScript" % (selector, node_type(node)))
    with open(js_path, encoding="utf-8") as f:
        code = f.read()
    scenes[si]["nodes"][ni]["model"]["data"]["js_code"] = code
    bak = write_back(path, outer, scenes)
    print("set js_code of %s (%s) from %s (%d chars); backup %s" % (
        selector, node.get("id"), js_path, len(code), bak))


def cast(field, value):
    if field in INT_FIELDS:
        return int(value)
    if field in BOOL_FIELDS:
        if value.lower() in ("true", "1", "yes"):
            return True
        if value.lower() in ("false", "0", "no"):
            return False
        raise SystemExit("field %s needs a boolean (true/false), got %r" % (field, value))
    return value


def cmd_set(path, selector, field, value):
    outer, scenes = load(path)
    si, ni, node = find_node(scenes, selector)
    t = node_type(node)
    if t in ("MqttPub", "MqttSub"):
        # settings live in a sub-dict of model (mqtt_pub / mqtt_sub)
        m = scenes[si]["nodes"][ni]["model"][MODEL_KEY[t]]
    elif t == "AutoRun":
        # AutoRun keeps its flags (e.g. node_enable = auto-fire on load) directly in model
        m = scenes[si]["nodes"][ni]["model"]
    else:
        raise SystemExit("set only supports MqttPub / MqttSub / AutoRun nodes, not %s" % t)
    if field not in m:
        raise SystemExit("field %s not in %s; fields: %s" % (field, t, ", ".join(sorted(m))))
    old = m[field]
    m[field] = cast(field, value)
    bak = write_back(path, outer, scenes)
    print("%s (%s) %s: %r -> %r; backup %s" % (t, node.get("id"), field, old, m[field], bak))


def cmd_del_node(path, selector):
    outer, scenes = load(path)
    si, ni, node = find_node(scenes, selector)
    nid = node.get("id")
    inner = scenes[si]
    before_n = len(inner["nodes"])
    inner["nodes"] = [n for n in inner["nodes"] if n.get("id") != nid]
    conns = inner.get("connections", [])
    before_c = len(conns)
    inner["connections"] = [c for c in conns if c.get("in_id") != nid and c.get("out_id") != nid]
    bak = write_back(path, outer, scenes)
    print("removed node %s (%s) from scene %d: nodes %d->%d, connections %d->%d; backup %s" % (
        selector, nid, si, before_n, len(inner["nodes"]), before_c, len(inner["connections"]), bak))


def main(argv):
    if len(argv) < 3:
        sys.stderr.write(__doc__)
        return 2
    cmd, path = argv[1], argv[2]
    if cmd == "list":
        cmd_list(path)
    elif cmd == "get-js":
        cmd_get_js(path, argv[3])
    elif cmd == "set-js":
        cmd_set_js(path, argv[3], argv[4])
    elif cmd == "set":
        cmd_set(path, argv[3], argv[4], argv[5])
    elif cmd == "del-node":
        cmd_del_node(path, argv[3])
    else:
        raise SystemExit("unknown command: %s" % cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
