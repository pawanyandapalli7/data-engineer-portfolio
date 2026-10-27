from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import yaml


@dataclass(frozen=True)
class Source:
    name: str
    file: str
    key: List[str]
    columns: List[str]
    types: Dict[str, str]
    rename: Dict[str, str]
    expectations: List[Dict[str, str]]

    @property
    def silver_key(self) -> List[str]:
        return [self.rename.get(k, k) for k in self.key]


def load_sources(path: str) -> Dict[str, Source]:
    raw = yaml.safe_load(Path(path).read_text())["sources"]
    return {
        name: Source(
            name=name,
            file=s["file"],
            key=s["key"],
            columns=s["columns"],
            types=s.get("types", {}),
            rename=s.get("rename", {}),
            expectations=s.get("expectations", []),
        )
        for name, s in raw.items()
    }
