#!/usr/bin/env python3
"""Configure SimpleX 6.5 for YunoHost, preserving certificates and identities."""
import os
import re
import secrets
import sys
from pathlib import Path


def set_options(path, options):
    target = Path(path)
    lines = target.read_text().splitlines(keepends=True)
    sections = {}
    for index, line in enumerate(lines):
        match = re.match(r'^\s*\[([^]]+)\]\s*$', line)
        if match:
            sections.setdefault(match.group(1), []).append(index)

    # Edit from bottom to top to keep original section offsets intact.
    for section, values in sorted(options.items(), key=lambda kv: sections[kv[0]][0], reverse=True):
        start = sections[section][0]
        end = next((i for i in range(start + 1, len(lines))
                    if re.match(r'^\s*\[[^]]+\]\s*$', lines[i])), len(lines))
        chunk = lines[start + 1:end]
        for name, desired in values.items():
            pattern = re.compile(r'^\s*#?\s*' + re.escape(name) + r'\s*[:=]')
            matches = [i for i, line in enumerate(chunk) if pattern.match(line)]
            active = next((i for i in matches if not chunk[i].lstrip().startswith('#')), None)
            if desired is None:
                for i in matches:
                    if not chunk[i].lstrip().startswith('#'):
                        chunk[i] = '# ' + chunk[i]
                continue

            if name.endswith('_password'):
                if active is not None:
                    old = re.split(r'[:=]', chunk[active], maxsplit=1)[-1].strip()
                    if old:
                        desired = old
                if not desired:
                    desired = secrets.token_urlsafe(32)
            replacement = f'{name} = {desired}\n'
            if active is not None:
                chunk[active] = replacement
            elif matches:
                chunk[matches[0]] = replacement
            else:
                chunk.append(replacement)
        lines[start + 1:end] = chunk

    target.write_text(''.join(lines))
    os.chmod(target, 0o640)


if __name__ == '__main__':
    smp_port, xftp_port, web_port, smp_control, xftp_control = sys.argv[1:]
    set_options('/etc/opt/simplex/smp-server.ini', {
        'AUTH': {'control_port_admin_password': '', 'control_port_user_password': ''},
        'TRANSPORT': {'port': smp_port, 'control_port': smp_control},
        'WEB': {'http': web_port, 'https': None, 'cert': None, 'key': None},
        'INFORMATION': {'source_code': 'https://github.com/simplex-chat/simplexmq'},
    })
    set_options('/etc/opt/simplex-xftp/file-server.ini', {
        'AUTH': {'control_port_admin_password': '', 'control_port_user_password': ''},
        'TRANSPORT': {'port': xftp_port, 'control_port': xftp_control},
        'WEB': {'http': None, 'https': None, 'cert': None, 'key': None},
    })
    print('Configured SMP/XFTP protocol and control ports, plus SMP HTTP information page')
