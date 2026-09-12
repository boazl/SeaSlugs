"""Interactive, reviewed Git publication. Run from Publish SeaSlugs.command."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_REMOTE = 'https://github.com/boazl/SeaSlugs.git'


def git(*args, capture=False):
    return subprocess.run(['git', *args], cwd=ROOT, check=True,
                          text=True, capture_output=capture)


def validate_paths(paths):
    for value in paths:
        p = Path(value)
        if (any(part in {'.venv', 'media', 'staticfiles', '__pycache__', 'backups'} for part in p.parts)
                or p.name.startswith(('.env', '.secret_key'))
                or any(token in p.name.lower() for token in ('.sqlite', '.db', '.pem', '.key'))):
            raise RuntimeError('Refusing to publish a possible database, backup or secret: ' + value)


def main():
    if git('branch', '--show-current', capture=True).stdout.strip() != 'main':
        raise RuntimeError('Switch to main before publishing.')
    if git('remote', 'get-url', 'origin', capture=True).stdout.strip() != EXPECTED_REMOTE:
        raise RuntimeError('Unexpected GitHub destination; no files were uploaded.')
    paths = set()
    for args in [('diff', '--name-only', '-z'), ('diff', '--cached', '--name-only', '-z'),
                 ('ls-files', '--others', '--exclude-standard', '-z')]:
        paths.update(filter(None, git(*args, capture=True).stdout.split('\0')))
    validate_paths(paths)
    gh = shutil.which('gh')
    if not gh:
        candidate = Path('/Users/boazliebes/Documents/Codex/2026-09-11/referenced-chatgpt-conversation-this-is-an/work/tools/gh')
        if candidate.is_file():
            gh = str(candidate)
    if gh:
        # Use the existing GitHub login, without embedding credentials or changing global Git settings.
        os.environ['GIT_CONFIG_COUNT'] = '2'
        os.environ['GIT_CONFIG_KEY_0'] = 'credential.helper'
        os.environ['GIT_CONFIG_VALUE_0'] = ''
        os.environ['GIT_CONFIG_KEY_1'] = 'credential.helper'
        os.environ['GIT_CONFIG_VALUE_1'] = '!' + shlex.quote(gh) + ' auth git-credential'
    print('Checking GitHub…', flush=True)
    git('fetch', 'origin')
    remote = git('rev-parse', '--verify', 'origin/main', capture=True).stdout.strip()
    if subprocess.run(['git', 'merge-base', '--is-ancestor', remote, 'HEAD'], cwd=ROOT).returncode:
        raise RuntimeError('GitHub has changes missing on this Mac. Sync and review them before publishing.')
    # Check all outgoing files too, including commits from earlier attempts.
    validate_paths(filter(None, git('diff', '--name-only', '-z', 'origin/main', 'HEAD', capture=True).stdout.split('\0')))
    if paths:
        print('\nFiles to publish:\n' + '\n'.join('  ' + p for p in sorted(paths)))
        git('diff', '--stat', 'HEAD')
    git('log', '--oneline', 'origin/main..HEAD')
    if not paths and git('rev-parse', 'HEAD', capture=True).stdout.strip() == remote:
        print('No changes to publish.')
        return
    print('\nDestination: boazl/SeaSlugs → main')
    print('Render will deploy automatically only if Auto-Deploy = On Commit.')
    if input('Type YES to publish, or Enter to cancel: ').strip() != 'YES':
        print('Cancelled. No changes uploaded.')
        return
    if paths:
        message = input('Short description of this update: ').strip()
        if not message:
            raise RuntimeError('An update description is required. Nothing uploaded.')
        git('diff', '--check')
        git('add', '--', *sorted(paths))
        git('commit', '-m', message)
    git('push', 'origin', 'main')
    print('\nUploaded to GitHub successfully.')
    print('Check Render for Live status: https://dashboard.render.com/')
    print('Website: https://seaslugs.org.il/')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, KeyboardInterrupt, EOFError) as exc:
        print('\nPublication stopped:', exc, file=sys.stderr)
        sys.exit(1)
