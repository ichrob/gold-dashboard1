"""Owner-only foreground key entry; no network, retrieval or provider activation.

The key is stored as plaintext in Termux's private app directory (0700/0600),
not in git, shared Android storage, command arguments or logs. Never execute
the entry mode through the remote maintenance queue. Status reads metadata only.
"""
import getpass
import os
from pathlib import Path
import stat
import sys
import warnings


def private_directory(home):
    path = Path(home) / '.bob-gold-api'
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        os.close(fd)
        raise ValueError('Private directory required')
    return fd


def save_key(home, key):
    if (not isinstance(key, str) or not 8 <= len(key) <= 512
            or not key.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in key)):
        raise ValueError('Invalid key format')
    directory = private_directory(home)
    try:
        fd = os.open('api-key', os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     os.O_NOFOLLOW, 0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(key.encode('ascii'))
                output.flush()
                os.fsync(output.fileno())
            os.fsync(directory)
        except BaseException:
            os.unlink('api-key', dir_fd=directory)
            raise
    finally:
        os.close(directory)


def key_status(home):
    path = Path(home) / '.bob-gold-api'
    if not path.exists() and not path.is_symlink():
        return 'not-configured'
    directory = private_directory(home)
    try:
        try:
            info = os.stat('api-key', dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            return 'not-configured'
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or not 8 <= info.st_size <= 512):
            return 'unsafe-or-invalid'
        return 'locally-stored-not-provider-verified'
    finally:
        os.close(directory)


def main():
    if sys.argv[1:] == ['--status']:
        try:
            print(key_status(Path.home()))
            return 0
        except (OSError, ValueError):
            print('unsafe-or-unavailable')
            return 1
    if sys.argv[1:] or not sys.stdin.isatty() or not sys.stderr.isatty():
        print('Bitte direkt in Termux starten; keine Schluessel als Befehlsargument.')
        return 2
    try:
        print('Speichert nur lokal im privaten Termux-Ordner. Kein API-Abruf.')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            key = getpass.getpass('Gold-API-Schluessel verdeckt einfuegen, dann Enter: ')
        save_key(Path.home(), key)
        print('Schluessel lokal gespeichert. Noch nicht beim Anbieter geprueft.')
        return 0
    except FileExistsError:
        print('Ein lokaler Schluessel existiert bereits. Nichts ueberschrieben.')
    except (OSError, ValueError, EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print('Nicht gespeichert. Keine sichere Eingabe oder ungueltiges Format.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
