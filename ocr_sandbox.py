"""Fail-closed Linux network isolation for the screenshot OCR child only."""
import ctypes
import errno


def deny_network():
    # Install before native OCR imports/threads; descendants inherit the filter.
    # A Python socket patch alone cannot constrain native library telemetry.
    lib = ctypes.CDLL('libseccomp.so.2', use_errno=True)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    context = lib.seccomp_init(0x7fff0000)  # allow non-network syscalls
    if not context:
        raise RuntimeError('OCR isolation unavailable')
    try:
        for name in (b'socket', b'connect', b'sendto', b'sendmsg', b'sendmmsg', b'socketcall'):
            number = lib.seccomp_syscall_resolve_name(name)
            if number >= 0 and lib.seccomp_rule_add(context, 0x50000 | errno.EPERM, number, 0):
                raise RuntimeError('OCR isolation rule failed')
        if lib.seccomp_load(context):
            raise RuntimeError('OCR isolation failed')
    finally:
        lib.seccomp_release(context)
