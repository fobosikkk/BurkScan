import datetime
import asyncio
from typing import Optional, Set, Dict

class ScanState:
    def __init__(self):
        self.running: bool = False
        self.process: Optional[asyncio.subprocess.Process] = None
        self.start_time: Optional[datetime.datetime] = None
        self.mode: str = "cidr"
        self.cidr: Optional[str] = None
        self.port: int = 25565
        self.rate: int = 1000
        self.out_dir: Optional[str] = None
        self.out_json_path: Optional[str] = None
        self.log_path: Optional[str] = None
        self.discovered: Set[str] = set()
        self.versions_set: Optional[Set[str]] = None
        self.only_online: bool = False

scan_states: Dict[int, ScanState] = {}
