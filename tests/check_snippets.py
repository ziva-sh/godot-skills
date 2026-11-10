#!/usr/bin/env python3
"""Parse-check every GDScript snippet in skills/ with a real Godot binary.

```gdscript blocks must pass `--check-only` in a project that treats unsafe
method and property access as errors, so a renamed Godot 3 member on a typed
object cannot slip through. ```gdscript-godot3 blocks are deliberate Godot 3
code and must fail `--check-only` with default project settings, which proves
each pitfall is real on the Godot version under test.

Usage: python3 tests/check_snippets.py [--godot /path/to/godot]
"""
import argparse
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap

ROOT = pathlib.Path(__file__).resolve().parent.parent
KINDS = ("gdscript", "gdscript-godot3")
PROJECT = 'config_version=5\n\n[application]\nconfig/name="snippet-check"\n'
STRICT = "\n[debug]\ngdscript/warnings/unsafe_method_access=2\ngdscript/warnings/unsafe_property_access=2\n"


def snippets():
    for md in sorted((ROOT / "skills").rglob("*.md")):
        lines = md.read_text(encoding="utf-8").splitlines(keepends=True)
        start = None
        for number, line in enumerate(lines, 1):
            if not line.lstrip().startswith("```"):
                continue
            if start is not None:
                if label in KINDS:
                    yield md.relative_to(ROOT), start, label, textwrap.dedent("".join(lines[start:number - 1]))
                start = None
                continue
            start, label = number, line.strip()[3:]
            # An unlabeled or misspelled fence would silently skip a GDScript snippet.
            if not label or (label.startswith("gdscript") and label not in KINDS):
                sys.exit(f"{md.relative_to(ROOT)}:{number}: fence label {label!r}; use one of {KINDS} or a non-GDScript language")
        if start is not None:
            sys.exit(f"{md.relative_to(ROOT)}:{start}: code fence is never closed")


def check(godot, project, env, name, code):
    (project / name).write_text(code, encoding="utf-8")
    result = subprocess.run(
        [godot, "--headless", "--path", str(project), "--check-only", "--script", f"res://{name}"],
        capture_output=True, text=True, env=env, timeout=120,
    )
    errors = [l.rstrip() for l in (result.stdout + result.stderr).splitlines() if "ERROR" in l]
    # Godot prints errors without always setting a non-zero exit code, so both are checked.
    return result.returncode == 0 and not errors, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"), help="Godot 4 binary (default: $GODOT or godot)")
    godot = parser.parse_args().godot

    version = subprocess.run([godot, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    print(f"Godot {version}")
    found = list(snippets())
    if not found:
        sys.exit(f"No gdscript snippets found under {ROOT / 'skills'}")

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        # Keep Godot's logs and editor settings out of the user's real config folders.
        env = dict(os.environ, XDG_CONFIG_HOME=f"{tmp}/config", XDG_DATA_HOME=f"{tmp}/data", XDG_CACHE_HOME=f"{tmp}/cache")
        strict = pathlib.Path(tmp, "strict")
        default = pathlib.Path(tmp, "default")
        for project, settings in ((strict, PROJECT + STRICT), (default, PROJECT)):
            project.mkdir()
            (project / "project.godot").write_text(settings, encoding="utf-8")

        for index, (md, line, kind, code) in enumerate(found):
            expect_parse = kind == "gdscript"
            parsed, errors = check(godot, strict if expect_parse else default, env, f"snippet_{index:03d}.gd", code)
            ok = parsed == expect_parse
            failures += not ok
            outcome = "parses" if parsed else "parse error (expected)" if not expect_parse else "parse error"
            print(f"{'PASS' if ok else 'FAIL'} {md}:{line} [{kind}] {outcome}")
            for error in errors:
                print(f"    {error}")

    passing = sum(1 for s in found if s[2] == "gdscript")
    print(f"\n{len(found)} snippets ({passing} gdscript, {len(found) - passing} gdscript-godot3), {failures} failed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
