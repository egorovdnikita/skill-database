#!/usr/bin/env python3
"""Общие версии навыков. Облачный Claude обновляется отдельно через UI."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
_skill_name = re.search(r'^name:\s*[\'"]?([a-z0-9-]+)[\'"]?\s*$',
                        (ROOT / 'SKILL.md').read_text().split('---', 2)[1], re.M)
if not _skill_name:
    raise RuntimeError('Не найдено имя навыка в SKILL.md.')
FILES = {_skill_name.group(1): 'SKILL.md'}
HOME = Path.home()
PRIVATE = HOME / '.local/share/shared-agent-skills'
STATE = PRIVATE / 'state.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def choose(base, canonical, mirror):
    """Вернуть новые байты; отклонить расходящиеся правки до записи."""
    if canonical == mirror:
        return canonical
    if base is None:
        raise RuntimeError('Нет общей базы версий: сначала сравните файлы и выполните init.')
    a, b = digest(canonical), digest(mirror)
    if a != base and b != base:
        raise RuntimeError('Обе стороны изменились: требуется сравнение и объединение правок.')
    return mirror if a == base else canonical


def git(*args):
    r = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError('git ' + args[0] + ' завершился с ошибкой: ' + r.stderr.strip())
    return r.stdout.strip()


def mirror_for(name):
    matches = []
    for p in (HOME / '.claude/skills/synced').glob('*/*/SKILL.md'):
        front = p.read_text().split('---', 2)
        if len(front) == 3 and re.search(r'^name:\s*[\'"]?' + name + r'[\'"]?\s*$', front[1], re.M):
            matches.append(p)
    if len(matches) != 1:
        raise RuntimeError(f'{name}: ожидался один synced-источник, найдено {len(matches)}.')
    return matches[0]


def validate(name, data):
    text = data.decode('utf-8')
    front = text.split('---', 2)
    if len(front) != 3 or not re.search(r'^name:\s*[\'"]?' + name + r'[\'"]?\s*$', front[1], re.M):
        raise RuntimeError(f'{name}: неверное имя или заголовок навыка.')
    # Это дополнительный фильтр; он не заменяет проверку приватности агентом.
    patterns = [r'gh[pousr]_[A-Za-z0-9]{20,}', r'sk-(?:ant-)?[A-Za-z0-9_-]{20,}',
                r'-----BEGIN .*PRIVATE KEY-----', r'[\w.+-]+@(?!(?:example\.com)\b)[\w.-]+\.[A-Za-z]{2,}']
    if any(re.search(p, text) for p in patterns):
        raise RuntimeError(f'{name}: возможный секрет или персональная почта; публикация остановлена.')


def write_state(state):
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, indent=2) + '\n')
    os.replace(tmp, STATE)


def fetch():
    git('fetch', 'origin', 'main')
    local, remote = git('rev-parse', 'HEAD'), git('rev-parse', 'origin/main')
    if local != remote:
        if git('status', '--porcelain'):
            raise RuntimeError('GitHub изменился при наличии локальных правок. Сначала объедините их.')
        git('merge', '--ff-only', 'origin/main')


def commit_skills(message):
    # Не захватываем чужой индекс и посторонние файлы.
    staged = git('diff', '--cached', '--name-only').splitlines()
    if any(p not in FILES.values() for p in staged):
        raise RuntimeError('В индексе есть посторонние файлы; автоматический коммит остановлен.')
    for name, path in FILES.items():
        validate(name, (ROOT / path).read_bytes())
    git('add', '--', *FILES.values())
    if git('diff', '--cached', '--name-only'):
        git('-c', 'user.name=Никита Егоров', '-c', 'user.email=egorov.d.nikita@mail.ru',
            'commit', '-m', message)
    # Повторяем push и после предыдущей сетевой ошибки, даже без нового коммита.
    git('push', 'origin', 'HEAD:main')


def export(name, directory):
    source = (ROOT / FILES[name]).read_bytes()
    validate(name, source)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    output = directory / (name + '.skill')
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('SKILL.md', source)
        z.writestr('references/sync-base.json', json.dumps({'sha256': digest(source), 'skill': name}))
        context = PRIVATE / 'database-private-context.md'
        if name == 'database' and context.exists():
            z.writestr('references/private-context.md', context.read_bytes())
    output.chmod(0o600)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'status', 'sync', 'publish-cloud', 'export'])
    parser.add_argument('name', nargs='?', choices=list(FILES))
    parser.add_argument('--output', type=Path, default=PRIVATE / 'exports')
    args = parser.parse_args()
    if args.command == 'status':
        state = json.loads(STATE.read_text()) if STATE.exists() else {}
        for name, path in FILES.items():
            canonical, mirror = (ROOT / path).read_bytes(), mirror_for(name).read_bytes()
            try:
                choose(state.get(name), canonical, mirror)
                print(name + ': ' + ('версии совпадают' if canonical == mirror else 'есть изменение'))
            except RuntimeError:
                print(name + ': конфликт или нет базы версий')
        return
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (PRIVATE / 'sync.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(STATE.read_text()) if STATE.exists() else {}
        if args.command == 'export':
            if not args.name:
                parser.error('export требует имя навыка')
            print(export(args.name, args.output))
            return
        if args.command == 'init':
            for name, path in FILES.items():
                data = (ROOT / path).read_bytes()
                if data != mirror_for(name).read_bytes():
                    raise RuntimeError(f'{name}: init не перезаписывает разные файлы.')
                state[name] = digest(data)
            write_state(state)
            print('База версий сохранена.')
            return
        fetch()
        plans = {}
        for name, path in FILES.items():
            canonical = (ROOT / path).read_bytes()
            mirror_path = mirror_for(name)
            mirror = mirror_path.read_bytes()
            if args.command == 'publish-cloud':
                base_path = mirror_path.parent / 'references/sync-base.json'
                if canonical == mirror:
                    plans[name] = canonical
                    continue
                if not base_path.exists():
                    raise RuntimeError(f'{name}: нет версии-основания облачного пакета. Сначала обновите пакет из GitHub.')
                base = json.loads(base_path.read_text())['sha256']
            else:
                base = state.get(name)
            plans[name] = choose(base, canonical, mirror)
            validate(name, plans[name])
        # Все конфликты и проверки выполняются до первой записи.
        for name, data in plans.items():
            (ROOT / FILES[name]).write_bytes(data)
        commit_skills('Синхронизировать общие инструкции навыков')
        for name, data in plans.items():
            mirror_for(name).write_bytes(data)
            state[name] = digest(data)
        write_state(state)
        for name in FILES:
            export(name, args.output)
        print('Локальные файлы и GitHub синхронизированы. Claude Chat обновляется отдельно через интерфейс.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print('Синхронизация остановлена: ' + str(error), file=sys.stderr)
        sys.exit(1)
