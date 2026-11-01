import runpy
import tempfile
import unittest
from pathlib import Path
Lock=runpy.run_path(str(Path(__file__).resolve().parents[1]/'production_write_lock.py'))['ProductionWriteLock']

class Tests(unittest.TestCase):
    def test_second_writer_blocked_and_release_allows_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            first=Lock(directory)
            try:
                with self.assertRaisesRegex(RuntimeError,'database lock'):Lock(directory)
            finally:first.close()
            second=Lock(directory);second.close()

if __name__=='__main__':unittest.main()
