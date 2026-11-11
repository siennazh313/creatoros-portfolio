"""Isolated DB files in an existing directory; no Windows private-directory ACLs."""
from pathlib import Path
import uuid
class TestDirectory:
    def __init__(self):
        self.name=str(Path(__file__).resolve().parent)
        self.filename='test-'+uuid.uuid4().hex+'.db'
    def cleanup(self):
        for suffix in ('','-journal','-wal','-shm'):
            (Path(self.name)/(self.filename+suffix)).unlink(missing_ok=True)
