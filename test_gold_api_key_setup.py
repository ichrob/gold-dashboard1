import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gold_api_key_setup as setup


class KeySetupTests(unittest.TestCase):
    def test_private_exclusive_storage_and_metadata_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            setup.save_key(tmp, 'synthetic-key-only')
            path = Path(tmp)/'.bob-gold-api'/'api-key'
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            with self.assertRaises(FileExistsError):
                setup.save_key(tmp, 'different-synthetic-key')
            self.assertEqual(path.read_text(), 'synthetic-key-only')
            with patch('builtins.open', side_effect=AssertionError('No key reads')):
                self.assertEqual(setup.key_status(tmp), 'locally-stored-not-provider-verified')

    def test_shared_directory_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'.bob-gold-api'
            path.mkdir(mode=0o755)
            os.chmod(path, 0o755)
            with self.assertRaises(ValueError):
                setup.save_key(tmp, 'synthetic-key-only')
            path.rmdir()
            path.symlink_to(tmp, target_is_directory=True)
            with self.assertRaises(OSError):
                setup.save_key(tmp, 'synthetic-key-only')

    def test_symlink_key_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'.bob-gold-api'; root.mkdir(mode=0o700)
            target = Path(tmp)/'untouched'; target.write_text('original')
            (root/'api-key').symlink_to(target)
            with self.assertRaises(FileExistsError):
                setup.save_key(tmp, 'synthetic-key-only')
            self.assertEqual(target.read_text(), 'original')
            self.assertEqual(setup.key_status(tmp), 'unsafe-or-invalid')

    def test_invalid_input_creates_no_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            for key in ['', 'short', 'secret\nline', ' leading-space', 'x'*513]:
                with self.assertRaises(ValueError):
                    setup.save_key(tmp, key)
            self.assertFalse((Path(tmp)/'.bob-gold-api').exists())

    def test_remote_entry_rejected_without_reading(self):
        with patch('sys.argv', ['setup']), patch('sys.stdin.isatty', return_value=False), \
             patch.object(setup.getpass, 'getpass') as prompt, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.main(), 2)
            prompt.assert_not_called()


if __name__ == '__main__':
    unittest.main()
