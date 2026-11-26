"""Skill tree: discovery, validation, search and installation.

A skill is a directory containing SKILL.md with YAML front matter. The tree is
made explicit by `parents` (or by directory nesting), so both the agent and the
user can see which skill owns which capability instead of guessing from one
giant prompt.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
REFERENCE_RE = re.compile(r"(?:^|[\s(])(references/[A-Za-z0-9_./\-]+)")
H1_RE = re.compile(r"^#\s+(.+)$", re.M)


# --------------------------------------------------------------- tiny YAML
def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(v) for v in _split_inline(inner)]
    if value.startswith("{") and value.endswith("}"):
        out = {}
        for part in _split_inline(value[1:-1]):
            key, _, val = part.partition(":")
            out[key.strip().strip('"').strip("'")] = _parse_scalar(val)
        return out
    if value in ("true", "True", "yes", "on"):
        return True
    if value in ("false", "False", "no", "off"):
        return False
    if value in ("null", "None", "~"):
        return None
    if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _split_inline(text: str) -> list[str]:
    parts, buf, quote = [], [], ""
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _mini_yaml(text: str) -> dict:
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append((indent, raw.strip()))

    def parse_block(idx: int, indent: int) -> tuple[Any, int]:
        if idx >= len(lines):
            return {}, idx
        is_list = lines[idx][1].startswith("- ")
        container: Any = [] if is_list else {}
        while idx < len(lines):
            cur_indent, content = lines[idx]
            if cur_indent != indent:
                break
            if is_list:
                if not content.startswith("- "):
                    break
                item = content[2:].strip()
                if ":" in item and not item.startswith(("http://", "https://")):
                    key, _, rest = item.partition(":")
                    child: dict = {key.strip(): _parse_scalar(rest)}
                    idx += 1
                    if idx < len(lines) and lines[idx][0] > indent:
                        nested, idx = parse_block(idx, lines[idx][0])
                        if isinstance(nested, dict):
                            child.update(nested)
                    container.append(child)
                else:
                    container.append(_parse_scalar(item))
                    idx += 1
            else:
                if ":" not in content:
                    idx += 1
                    continue
                key, _, rest = content.partition(":")
                key = key.strip()
                if rest.strip() == "":
                    idx += 1
                    if idx < len(lines) and lines[idx][0] > indent:
                        nested, idx = parse_block(idx, lines[idx][0])
                        container[key] = nested
                    else:
                        container[key] = {}
                else:
                    container[key] = _parse_scalar(rest)
                    idx += 1
        return container, idx

    data, _ = parse_block(0, lines[0][0] if lines else 0)
    return data if isinstance(data, dict) else {}


def parse_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw = match.group(1)
    try:
        import yaml  # type: ignore
        meta = yaml.safe_load(raw) or {}
        if not isinstance(meta, dict):
            meta = {}
    except Exception:
        meta = _mini_yaml(raw)
    return meta, text[match.end():]


# --------------------------------------------------------------- discovery
def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return [str(value)]


def _first_paragraph(body: str) -> str:
    for block in re.split(r"\n\s*\n", body):
        clean = " ".join(block.strip().split())
        if clean and not clean.startswith("#"):
            return clean[:400]
    return ""


def scan_skill_tree(root: str | Path) -> list[dict]:
    root = Path(root).expanduser()
    nodes: list[dict] = []
    if not root.exists():
        return nodes
    for skill_md in sorted(root.rglob("SKILL.md")):
        rel_dir = skill_md.parent.relative_to(root)
        if any(part.startswith(".") for part in rel_dir.parts):
            continue
        try:
            text = skill_md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        meta, body = parse_frontmatter(text)
        metadata = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
        hermes_meta = metadata.get("hermes") if isinstance(metadata.get("hermes"), dict) else {}
        name = str(meta.get("name") or skill_md.parent.name)
        parents = _as_list(meta.get("parents") or meta.get("parent"))
        if not parents and len(rel_dir.parts) > 1:
            parent_dir = skill_md.parent.parent
            if (parent_dir / "SKILL.md").exists():
                parents = [parent_dir.name]
        title_match = H1_RE.search(body)
        title = title_match.group(1).strip() if title_match else name
        description = str(meta.get("description") or _first_paragraph(body))
        tags = _as_list(meta.get("tags")) + _as_list(hermes_meta.get("tags"))
        capabilities = _as_list(meta.get("capabilities"))
        references = []
        ref_dir = skill_md.parent / "references"
        if ref_dir.is_dir():
            references = sorted(str(p.relative_to(skill_md.parent))
                                for p in ref_dir.rglob("*") if p.is_file())
        bins = []
        bin_dir = skill_md.parent / "bin"
        if bin_dir.is_dir():
            bins = sorted(p.name for p in bin_dir.iterdir() if p.is_file())
        declared_refs = sorted(set(REFERENCE_RE.findall(body)))
        missing_refs = [r for r in declared_refs if not (skill_md.parent / r).exists()]
        health: list[dict] = []
        if not meta.get("name"):
            health.append({"level": "warn", "message": "front matter has no name"})
        if not description:
            health.append({"level": "warn",
                           "message": "no description (agent cannot choose this skill)"})
        if missing_refs:
            health.append({"level": "error",
                           "message": "missing referenced files: " + ", ".join(missing_refs)})
        line_count = len(body.splitlines())
        if line_count > 450:
            health.append({"level": "warn",
                           "message": f"SKILL.md is {line_count} lines; split into references/"})
        if len(body) > 30000:
            health.append({"level": "warn", "message": "SKILL.md is very large (>30 KB)"})
        digest = hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:16]
        nodes.append({
            "path": str(rel_dir).replace(os.sep, "/"),
            "dir": str(skill_md.parent),
            "file": str(skill_md),
            "name": name,
            "title": title,
            "description": description,
            "parent": parents[0] if parents else None,
            "parents": parents,
            "tags": sorted(set(tags)),
            "capabilities": capabilities,
            "platforms": _as_list(meta.get("platforms")),
            "version": str(meta.get("version") or ""),
            "references": references,
            "declared_references": declared_refs,
            "missing_references": missing_refs,
            "bin": bins,
            "lines": line_count,
            "size": len(text),
            "mtime": skill_md.stat().st_mtime,
            "hash": digest,
            "health": health,
        })
    names: dict[str, int] = {}
    for node in nodes:
        names[node["name"]] = names.get(node["name"], 0) + 1
    by_name = {n["name"]: n for n in nodes}
    for node in nodes:
        if names.get(node["name"], 0) > 1:
            node["health"].append({"level": "error",
                                   "message": f"duplicate skill name: {node['name']}"})
        for parent in node["parents"]:
            if parent and parent not in by_name:
                node["health"].append({"level": "error",
                                       "message": f"parent skill not found: {parent}"})
        if node["parent"] and node["parent"] in by_name:
            parent = by_name[node["parent"]]
            try:
                parent_meta = parse_frontmatter(
                    Path(parent["file"]).read_text(encoding="utf-8", errors="ignore"))[0]
            except OSError:
                parent_meta = {}
            if node["name"] not in _as_list(parent_meta.get("children")):
                node["health"].append({
                    "level": "info",
                    "message": f"parent {node['parent']} does not list this skill in children"})
    return nodes


def _load_declared(root: Path) -> dict:
    for name in ("tree.yaml", "tree.yml"):
        path = root / name
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
            try:
                import yaml  # type: ignore
                data = yaml.safe_load(text) or {}
            except Exception:
                data = _mini_yaml(text)
            return data if isinstance(data, dict) else {}
        except OSError:
            return {}
    return {}


def tree_payload(root: str | Path) -> dict:
    root = Path(root).expanduser()
    nodes = scan_skill_tree(root)
    declared = _load_declared(root)
    by_name = {n["name"]: n for n in nodes}
    children: dict[str, list[str]] = {n["name"]: [] for n in nodes}
    roots: list[str] = []
    for node in nodes:
        parent = node.get("parent")
        if parent and parent in children:
            children[parent].append(node["name"])
        else:
            roots.append(node["name"])

    def build(name: str) -> dict:
        node = by_name[name]
        return {
            "name": name,
            "title": node["title"],
            "description": node["description"],
            "path": node["path"],
            "tags": node["tags"],
            "capabilities": node["capabilities"],
            "platforms": node["platforms"],
            "health": node["health"],
            "lines": node["lines"],
            "references": node["references"],
            "bin": node["bin"],
            "children": [build(c) for c in sorted(children.get(name, []))],
        }

    issues = [{"skill": n["name"], **h} for n in nodes for h in n["health"]]
    summary = {
        "skills": len(nodes),
        "errors": sum(1 for i in issues if i.get("level") == "error"),
        "warnings": sum(1 for i in issues if i.get("level") == "warn"),
        "info": sum(1 for i in issues if i.get("level") == "info"),
        "roots": len(roots),
        "references": sum(len(n["references"]) for n in nodes),
        "bins": sum(len(n["bin"]) for n in nodes),
    }
    return {
        "root": str(root),
        "generated_at": time.time(),
        "declared": declared,
        "summary": summary,
        "tree": [build(name) for name in sorted(roots)],
        "flat": [{k: n[k] for k in ("name", "title", "description", "path", "parent",
                                    "tags", "capabilities", "platforms", "health",
                                    "lines", "references", "bin", "version")}
                 for n in sorted(nodes, key=lambda x: x["path"])],
        "issues": issues,
    }


def validate_tree(root: str | Path) -> dict:
    payload = tree_payload(root)
    declared = payload.get("declared") or {}
    expected = declared.get("skills") or declared.get("order") or []
    found = {n["name"] for n in payload["flat"]}
    missing = [name for name in _as_list(expected) if name not in found]
    issues = list(payload["issues"])
    for name in missing:
        issues.append({"skill": name, "level": "error",
                       "message": "declared in tree.yaml but no SKILL.md found"})
    errors = [i for i in issues if i.get("level") == "error"]
    warnings = [i for i in issues if i.get("level") == "warn"]
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "summary": payload["summary"], "root": payload["root"]}


def search_skills(root: str | Path, query: str, limit: int = 20) -> list[dict]:
    from .recipes import similarity
    payload = tree_payload(root)
    scored = []
    for node in payload["flat"]:
        hay = " ".join(filter(None, [node["name"], node["title"], node["description"],
                                     " ".join(node["tags"]),
                                     " ".join(node["capabilities"])]))
        score = similarity(query, hay)
        if query.lower() in hay.lower():
            score = max(score, 0.9)
        if score > 0.15:
            scored.append((score, node))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for score, node in scored[:limit]:
        item = dict(node)
        item["score"] = round(score, 3)
        out.append(item)
    return out


def skill_context_lines(root: str | Path, query: str = "", limit: int = 8) -> list[str]:
    payload = tree_payload(root)
    nodes = payload["flat"]
    if query:
        ranked = search_skills(root, query, limit=limit)
    else:
        ranked = sorted(nodes, key=lambda n: (len(n["path"].split("/")), n["name"]))[:limit]
    return [f"{n['name']}: {n['description'][:140]}" for n in ranked]


def install_skills(root: str | Path, hermes_home: str | Path) -> dict:
    root = Path(root).expanduser()
    target = Path(hermes_home).expanduser() / "skills"
    target.mkdir(parents=True, exist_ok=True)
    installed = []
    for node in scan_skill_tree(root):
        dest = target / node["name"]
        shutil.copytree(node["dir"], dest, dirs_exist_ok=True)
        installed.append({"name": node["name"], "dest": str(dest)})
    return {"ok": True, "target": str(target), "installed": installed}


# ---------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    import argparse
    from .config import load_config, skills_root

    parser = argparse.ArgumentParser(
        prog="mia-skill",
        description="Mia skill tree: list, tree, search, validate, install.")
    parser.add_argument("--root", help="skills directory (default: <repo>/skills)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("list", help="flat list of skills")
    sub.add_parser("tree", help="nested tree")
    sub.add_parser("validate", help="fail on tree errors")
    p_search = sub.add_parser("search", help="search skills")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=20)
    p_install = sub.add_parser("install", help="copy skills into a Hermes home")
    p_install.add_argument("hermes_home")
    sub.add_parser("doctor", help="tree health summary")
    raw = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in raw
    args = parser.parse_args([a for a in raw if a != "--json"])
    args.json = as_json or args.json

    cfg = load_config()
    root = Path(args.root).expanduser() if args.root else skills_root(cfg)
    cmd = args.cmd or "tree"
    if cmd == "list":
        payload = tree_payload(root)
        if args.json:
            print(json.dumps(payload["flat"], ensure_ascii=False, indent=2))
        else:
            for n in payload["flat"]:
                parent = f" (parent: {n['parent']})" if n.get("parent") else ""
                print(f"{n['name']:<24} {n['description'][:90]}{parent}")
        return 0
    if cmd == "search":
        results = search_skills(root, args.query, limit=args.limit)
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            for r in results:
                print(f"{r['score']:.2f}  {r['name']:<24} {r['description'][:90]}")
        return 0
    if cmd == "install":
        result = install_skills(root, args.hermes_home)
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json
              else f"installed {len(result['installed'])} skill(s) into {result['target']}")
        return 0
    if cmd in ("validate", "doctor"):
        report = validate_tree(root)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"root: {report['root']}")
            for key, value in report["summary"].items():
                print(f"  {key}: {value}")
            for issue in report["errors"] + report["warnings"]:
                print(f"  [{issue['level']}] {issue['skill']}: {issue['message']}")
            print("OK" if report["ok"] else "FAILED")
        return 0 if report["ok"] or cmd == "doctor" else 1
    payload = tree_payload(root)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        def walk(node: dict, depth: int = 0) -> None:
            print("  " * depth + f"▸ {node['name']} — {node['description'][:80]}")
            for child in node["children"]:
                walk(child, depth + 1)
        for node in payload["tree"]:
            walk(node)
        s = payload["summary"]
        print(f"\n{s['skills']} skills · {s['references']} references · "
              f"{s['errors']} errors · {s['warnings']} warnings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
