#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
"""Check local Markdown targets, heading fragments, fences and lesson navigation."""
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def prose(text):
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r'^\s*(`{3,}|~{3,})', line)
        if match:
            marker = match.group(1)[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is None:
            lines.append(line)
    if fence is not None:
        raise ValueError('Unclosed code fence')
    return '\n'.join(lines)


def anchors(text):
    values = set()
    counts = {}
    for title in re.findall(r'^#{1,6}\s+(.+?)\s*#*$', prose(text), flags=re.M):
        title = re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', title)
        slug = re.sub(r'[^\w\-\s]', '', title.lower()).replace(' ', '-')
        number = counts.get(slug, 0)
        counts[slug] = number + 1
        values.add(slug if not number else f'{slug}-{number}')
    return values


def main():
    errors = []
    files = sorted(p for p in ROOT.rglob('*.md') if not any(part in {'.git', '.venv', 'build', 'run', 'models'} for part in p.relative_to(ROOT).parts))
    for file in files:
        try:
            text = file.read_text(encoding='utf-8')
            body = prose(text)
            if '\ufffd' in text:
                errors.append(f'{file.relative_to(ROOT)}: replacement character in UTF-8 text')
            for target in re.findall(r'(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)', body):
                target = target.strip().strip('<>')
                url = urlsplit(target)
                if url.scheme or target.startswith('//'):
                    continue
                dest = (file.parent / unquote(url.path)).resolve() if url.path else file
                if not dest.is_relative_to(ROOT):
                    errors.append(f'{file.relative_to(ROOT)}: link leaves repository: {target}')
                elif not dest.exists():
                    errors.append(f'{file.relative_to(ROOT)}: missing target: {target}')
                elif url.fragment and dest.suffix == '.md' and unquote(url.fragment) not in anchors(dest.read_text(encoding='utf-8')):
                    errors.append(f'{file.relative_to(ROOT)}: missing heading: {target}')
            if file.parent.parent.name == 'docs' and re.match(r'^\d\d-', file.parent.name):
                for required in ['## 这课完成什么', '## 自己完成一次', '## 完成标准', '## 清理与回顾', '上一课', '下一课']:
                    if required not in text:
                        errors.append(f'{file.relative_to(ROOT)}: missing lesson element: {required}')
        except (OSError, ValueError) as error:
            errors.append(f'{file.relative_to(ROOT)}: {error}')
    for error in errors:
        print(error, file=sys.stderr)
    print(f'Checked {len(files)} Markdown files; {len(errors)} errors. External URLs are not fetched.')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
