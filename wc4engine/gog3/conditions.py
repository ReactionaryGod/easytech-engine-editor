"""GoG3 buff conditions (config/def_buff.xml).

A condition is either a comparison of two parameters (`comp`) or a logical combination (`and`/`or`/`not`) of other
conditions referenced by id. Conditions you add are written into one marked block at the end of the army
`<conditions>` section, so the original file content stays untouched.
"""
import re
import xml.etree.ElementTree as ET

BEGIN = "<!-- engine-editor begin -->"
END = "<!-- engine-editor end -->"

ARMY_PROPS = {1: "unit class", 2: "in a city area", 3: "at sea", 4: "terrain type", 5: "building type",
              6: "fortification id", 7: "morale id", 8: "unit size", 9: "counter-attack", 10: "unit type",
              11: "unit class (ships excluded)", 12: "has not moved"}
UNIT_CLASSES = {1: "infantry", 2: "armor", 3: "artillery", 4: "navy", 5: "air force"}
COMPARES = ["equal", "not equal", "greater", "less", "greater equal", "less equal"]
OPS = ["comp", "and", "or", "not"]
CUSTOM_BASE = 2001            # first id used for conditions created by the editor


def parse(text):
    """Returns [dict(id, scope, op, compare, desc, params, children, custom)] in file order."""
    custom_ids = set()
    if BEGIN in text and END in text:
        block = text[text.index(BEGIN):text.index(END)]
        custom_ids = {int(m) for m in re.findall(r'<condition id="(\d+)"[^>]*logicaloper', block)}
    root = ET.fromstring(text)
    out = []
    for sec in root.findall("conditions"):
        scope = sec.get("type", "army")
        for c in sec.findall("condition"):
            if c.get("logicaloper") is None:
                continue
            out.append(dict(
                id=int(c.get("id")), scope=scope, op=c.get("logicaloper"), compare=c.get("compare", ""),
                desc=c.get("desc", ""),
                params=[dict(origin=p.get("origin"), proptype=int(p.get("proptype")) if p.get("proptype") else None,
                             value=p.get("value")) for p in c.findall("param")],
                children=[int(x.get("id")) for x in c.findall("condition")], custom=int(c.get("id")) in custom_ids))
    return out


def describe(c, by_id=None, depth=0):
    """English description of a condition."""
    if c["op"] == "comp":
        params = c["params"]
        if len(params) == 2:
            a, b = params
            who = {"self": "the unit", "target": "the target"}.get(a["origin"], a["origin"])
            prop = ARMY_PROPS.get(a["proptype"], "property %s" % a["proptype"])
            val = b["value"]
            if a["proptype"] in (1, 11) and val and all(v.strip().isdigit() for v in val.split(",")):
                val = "/".join(UNIT_CLASSES.get(int(v), v) for v in val.split(","))
            op = {"equal": "is", "not equal": "is not", "greater": "is above", "less": "is below",
                  "greater equal": "is at least", "less equal": "is at most"}.get(c["compare"], c["compare"])
            return "%s: %s %s %s" % (who, prop, op, val)
        return "comparison"
    if not by_id or depth > 3:
        return {"and": "all of", "or": "any of", "not": "none of"}[c["op"]] + " " + ", ".join(map(str, c["children"]))
    word = {"and": " AND ", "or": " OR ", "not": "NOT "}[c["op"]]
    parts = [("(" + describe(by_id[k], by_id, depth + 1) + ")") if k in by_id else "#%d" % k for k in c["children"]]
    return word.join(parts) if c["op"] != "not" else word + " / ".join(parts)


def render(c):
    """XML text for a custom condition dict (id, scope, op, compare, desc, params, children)."""
    desc = c.get("desc", "").replace('"', "&quot;").replace("<", "&lt;")
    lines = []
    if c["op"] == "comp":
        lines.append('    <condition id="%d" logicaloper="comp" compare="%s" desc="%s">' % (c["id"], c["compare"], desc))
        for p in c["params"]:
            if p.get("proptype") is not None:
                lines.append('      <param origin="%s" proptype="%d"/>' % (p["origin"], p["proptype"]))
            else:
                lines.append('      <param origin="%s" value="%s"/>' % (p["origin"], p["value"]))
    else:
        lines.append('    <condition id="%d" logicaloper="%s" desc="%s">' % (c["id"], c["op"], desc))
        for k in c["children"]:
            lines.append('      <condition id="%d"/>' % k)
    lines.append("    </condition>")
    return "\n".join(lines)


def split_block(text):
    """(before, custom conditions, after) around the editor block (creates the insertion point when absent)."""
    if BEGIN in text:
        i, j = text.index(BEGIN), text.index(END) + len(END)
        block = parse_block(text[i:j])
        return text[:i], block, text[j:]
    k = text.index("</conditions>")                    # the first section is type="army"
    return text[:k], [], text[k:]


def parse_block(block):
    wrapped = "<buff><conditions type=\"army\">" + block.replace(BEGIN, "").replace(END, "") + "</conditions></buff>"
    return [c for c in parse(wrapped)]


def with_custom(text, conditions):
    """Return `text` with the editor block replaced by `conditions` (list of condition dicts)."""
    nl = chr(10)
    body = nl.join(render(c) for c in conditions)
    block = BEGIN + ((nl + body) if body else "") + nl + "    " + END
    if BEGIN in text:
        i, j = text.index(BEGIN), text.index(END) + len(END)
        return text[:i] + block + text[j:]
    k = text.index("</conditions>")  # the first section is type="army"
    return text[:k].rstrip(chr(32) + chr(9)) + "    " + block + nl + "  " + text[k:]
