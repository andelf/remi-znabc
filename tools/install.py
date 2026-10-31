import argparse
from datetime import datetime
from pathlib import Path
import re
import shutil


def enable_schema(original):
    if re.search(r'^\s*-?\s*schema:\s*[\"\']?znabc[\"\']?\s*(?:#.*)?$', original, re.MULTILINE):
        return original
    if re.search(r'^[ \t]*[\"\']?schema_list/@next[\"\']?\s*:', original, re.MULTILINE):
        raise ValueError('default.custom.yaml 已使用 schema_list/@next；请使用 --no-enable，再在现有方案列表加入 schema: znabc。')
    addition = '  "schema_list/@next":\n    schema: znabc\n'
    if not original.strip():
        return 'patch:\n' + addition
    lines = original.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if re.match(r'^patch:\s*(?:#.*)?$', line.rstrip('\r\n')):
            end = index + 1
            while end < len(lines) and (not lines[end].strip() or lines[end].startswith((' ', '\t', '#'))):
                end += 1
            indent = '  '
            for nested in lines[index + 1:end]:
                match = re.match(r'^( +)\S', nested)
                if match and not nested.lstrip().startswith('#'):
                    indent = match[1]
                    break
            insertion = indent + '"schema_list/@next":\n' + indent + '  schema: znabc\n'
            if end and not lines[end - 1].endswith('\n'):
                lines[end - 1] += '\n'
            return ''.join(lines[:end]) + insertion + ''.join(lines[end:])
        if re.match(r'^patch:\s*\{\s*\}\s*(?:#.*)?$', line.rstrip('\r\n')):
            lines[index] = 'patch:\n' + addition
            return ''.join(lines)
        if re.match(r'^patch:', line):
            raise ValueError('default.custom.yaml 的 patch 使用内联或复杂格式；请使用 --no-enable，再手动加入 schema: znabc。')
    return original.rstrip('\r\n') + '\npatch:\n' + addition


def install(source, destination, enable=True, dry_run=False):
    if not (source / 'znabc_data/manifest.json').is_file():
        raise ValueError('缺少生成的词库；源码项目请先运行 tools/build_data.py，或使用完整安装包。')
    files = sorted(path for path in source.rglob('*') if path.is_file())
    planned = []
    for path in files:
        relative = path.relative_to(source)
        target = destination / relative
        data = path.read_bytes()
        if not target.exists() or target.read_bytes() != data:
            planned.append((target, data))
    if enable:
        custom = destination / 'default.custom.yaml'
        original = custom.read_text(encoding='utf-8-sig') if custom.exists() else ''
        updated = enable_schema(original)
        if updated != original:
            planned.append((custom, updated.encode('utf-8')))
    backup = destination / '.znabc-backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    for target, data in planned:
        if dry_run:
            continue
        if target.exists():
            saved = backup / target.relative_to(destination)
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.znabc.tmp')
        temporary.write_bytes(data)
        temporary.replace(target)
    return len(planned), backup


def main():
    project = Path(__file__).resolve().parent
    source = project / 'rime'
    if not source.is_dir():
        source = project.parent / 'rime'
    parser = argparse.ArgumentParser(description='安装智能 ABC Rime 方案；保留其他方案，并备份覆盖文件。')
    parser.add_argument('--user-dir', required=True, type=Path, help='Rime 用户目录，必须显式指定')
    parser.add_argument('--no-enable', action='store_true', help='不修改 default.custom.yaml')
    parser.add_argument('--dry-run', action='store_true', help='仅检查安装计划，不写文件')
    arguments = parser.parse_args()
    try:
        count, backup = install(source, arguments.user_dir.expanduser(), not arguments.no_enable, arguments.dry_run)
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    print(f'{"计划更新" if arguments.dry_run else "已更新"} {count} 个文件。')
    if not arguments.dry_run:
        print(f'覆盖文件的备份目录（如有）：{backup}')
        print('请在 Rime 前端执行“重新部署”，然后切换到“智能 ABC · 复原”。')


if __name__ == '__main__':
    main()

