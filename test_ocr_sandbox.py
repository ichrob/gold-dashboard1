import subprocess
import sys
import unittest


class SandboxTests(unittest.TestCase):
    def test_python_native_and_thread_sockets_are_denied_before_connect(self):
        script = '''
from ocr_sandbox import deny_network
deny_network()
import ctypes, socket, threading
def check():
    try: socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except PermissionError: pass
    else: raise AssertionError('Python network allowed')
    libc=ctypes.CDLL(None,use_errno=True)
    assert libc.socket(2,1,0)==-1
    assert ctypes.get_errno()==1
check()
errors=[]
def child():
    try: check()
    except BaseException as e: errors.append(e)
t=threading.Thread(target=child);t.start();t.join()
assert not errors
print('network denied')
'''
        result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout.strip(),'network denied')
