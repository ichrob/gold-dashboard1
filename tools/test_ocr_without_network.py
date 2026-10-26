"""Linux-only OCR test entrypoint: deny network syscalls before importing tests.

Uses libseccomp; fails closed if unavailable. The restriction is inherited by
OCR subprocesses and covers native libraries, unlike Python socket mocks.
Run from repository root: python tools/test_ocr_without_network.py
"""
import ctypes
import ctypes.util
import errno
import os
from pathlib import Path
import resource
import sys


def deny_network():
    if sys.platform != 'linux':
        raise RuntimeError('Network isolation requires Linux and libseccomp')
    lib = ctypes.CDLL(ctypes.util.find_library('seccomp') or 'libseccomp.so.2')
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = lib.seccomp_init(0x7fff0000)  # allow unrelated filesystem/process work
    if not ctx:
        raise RuntimeError('Cannot initialize network isolation')
    try:
        for name in ('socket', 'socketpair', 'connect', 'sendto', 'sendmsg',
                     'sendmmsg', 'io_uring_setup'):
            syscall = lib.seccomp_syscall_resolve_name(name.encode())
            if syscall < 0 or lib.seccomp_rule_add(ctx, 0x50000 | errno.EPERM, syscall, 0):
                raise RuntimeError('Cannot install network isolation')
        # Remove inherited extra descriptors, including any existing sockets.
        maximum = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
        os.closerange(3, maximum if maximum != resource.RLIM_INFINITY else 1048576)
        if lib.seccomp_load(ctx):
            raise RuntimeError('Cannot activate network isolation')
    finally:
        lib.seccomp_release(ctx)


def verify_isolation():
    import socket
    import subprocess
    for family in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX):
        try:
            socket.socket(family)
        except PermissionError:
            continue
        raise RuntimeError('Network isolation probe failed')
    child = 'import socket\ntry: socket.socket()\nexcept PermissionError: exit(0)\nexit(1)'
    subprocess.run([sys.executable, '-c', child], check=True)


if __name__ == '__main__':
    deny_network()
    verify_isolation()
    print('Network denied in parent and child before OCR imports.', flush=True)
    if '--probe-only' not in sys.argv:
        os.environ.pop('BOB_TEST_DATABASE_URL', None)
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import unittest
        unittest.main(module=None, argv=['offline-ocr', 'test_video_ocr_privacy',
                                       'test_video_ocr', 'test_video_values'])
