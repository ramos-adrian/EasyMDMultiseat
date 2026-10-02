#!/usr/bin/env python3
"""
Pure-Python replacement for xgettext/msgmerge/msgfmt (no gettext tools needed).

  tools/i18n.py extract   scan *.py for _("...") -> locale/multiseat-manager.pot,
                          and add missing entries to every locale/<lang>.po
  tools/i18n.py compile   locale/<lang>.po -> locale/<lang>/LC_MESSAGES/multiseat-manager.mo
  tools/i18n.py check     verify placeholders ({name}) match between msgid and msgstr
  tools/i18n.py all       extract + check + compile

To add a language: create locale/<lang>.po (copy the .pot), translate, run `all`.
"""

import ast
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALE = ROOT / "locale"
DOMAIN = "multiseat-manager"
POT = LOCALE / f"{DOMAIN}.pot"
HEADER = (
    "Project-Id-Version: multiseat-manager\n"
    "Language: {lang}\n"
    "MIME-Version: 1.0\n"
    "Content-Type: text/plain; charset=UTF-8\n"
    "Content-Transfer-Encoding: 8bit\n"
)


def extract_messages():
    """Returns {msgid: [refs]} for every _("literal") call in the project's .py files."""
    found = {}
    for py in sorted(ROOT.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_"
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.setdefault(node.args[0].value, []).append(f"{py.name}:{node.lineno}")
    return found


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


def unesc(s):
    return re.sub(r'\\(.)', lambda m: {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(m.group(1), m.group(1)), s)


def read_po(path):
    """Returns {msgid: msgstr} (header excluded)."""
    entries, msgid, msgstr, cur = {}, None, None, None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("msgid "):
            if msgid is not None:
                entries[msgid] = msgstr or ""
            msgid, msgstr, cur = unesc(line[7:-1]), None, "id"
        elif line.startswith("msgstr "):
            msgstr, cur = unesc(line[8:-1]), "str"
        elif line.startswith('"') and cur:
            text = unesc(line[1:-1])
            if cur == "id":
                msgid += text
            else:
                msgstr += text
    if msgid is not None:
        entries[msgid] = msgstr or ""
    entries.pop("", None)
    return entries


def write_po(path, lang, messages, refs):
    out = [f'# {lang or "Template"} translation for {DOMAIN}\nmsgid ""\nmsgstr ""']
    out += [f'"{esc(l)}\\n"' for l in HEADER.format(lang=lang or "").strip().split("\n")]
    for msgid in sorted(refs, key=lambda m: refs[m][0]):
        out.append("")
        out.append("#: " + " ".join(refs[msgid]))
        out.append(f'msgid "{esc(msgid)}"')
        out.append(f'msgstr "{esc(messages.get(msgid, ""))}"')
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def cmd_extract():
    LOCALE.mkdir(exist_ok=True)
    refs = extract_messages()
    write_po(POT, "", {}, refs)
    print(f"{POT.name}: {len(refs)} messages")
    for po in sorted(LOCALE.glob("*.po")):
        lang = po.stem
        old = read_po(po)
        merged = {m: old.get(m, "") for m in refs}
        if lang == "en":  # source language: identity translation
            merged = {m: (old.get(m) or m) for m in refs}
        write_po(po, lang, merged, refs)
        missing = [m for m in refs if not merged[m]]
        print(f"{po.name}: {len(refs) - len(missing)}/{len(refs)} translated")


def placeholders(s):
    return sorted(re.findall(r'\{[A-Za-z_0-9]*\}', s))


def cmd_check():
    bad = 0
    for po in sorted(LOCALE.glob("*.po")):
        for msgid, msgstr in read_po(po).items():
            if msgstr and placeholders(msgid) != placeholders(msgstr):
                print(f"{po.name}: placeholder mismatch\n  {msgid!r}\n  {msgstr!r}")
                bad += 1
    print("placeholders OK" if not bad else f"{bad} problem(s)")
    return bad == 0


def cmd_compile():
    for po in sorted(LOCALE.glob("*.po")):
        lang = po.stem
        entries = {m: s for m, s in read_po(po).items() if s}
        entries[""] = HEADER.format(lang=lang)
        keys = sorted(entries)
        ids = strs = b""
        offsets = []
        for k in keys:
            kb, vb = k.encode("utf-8"), entries[k].encode("utf-8")
            offsets.append((len(ids), len(kb), len(strs), len(vb)))
            ids += kb + b"\0"
            strs += vb + b"\0"
        n = len(keys)
        keystart = 7 * 4 + 16 * n
        valuestart = keystart + len(ids)
        koffsets, voffsets = [], []
        for o1, l1, o2, l2 in offsets:
            koffsets += [l1, o1 + keystart]
            voffsets += [l2, o2 + valuestart]
        data = struct.pack("Iiiiiii", 0x950412de, 0, n, 7 * 4, 7 * 4 + n * 8, 0, 0)
        data += struct.pack(f"{len(koffsets + voffsets)}i", *(koffsets + voffsets)) + ids + strs
        target = LOCALE / lang / "LC_MESSAGES" / f"{DOMAIN}.mo"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        print(f"{target.relative_to(ROOT)}: {n - 1} messages")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "extract":
        cmd_extract()
    elif cmd == "compile":
        cmd_compile()
    elif cmd == "check":
        sys.exit(0 if cmd_check() else 1)
    elif cmd == "all":
        cmd_extract()
        if cmd_check():
            cmd_compile()
    else:
        print(__doc__)
        sys.exit(1)
