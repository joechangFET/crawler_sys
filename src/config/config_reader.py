import json
import yaml
from pathlib import Path

class ConfigReader:
    _instances = {}

    def __new__(cls, config_file_path):
        path = Path(config_file_path).resolve()
        if path not in cls._instances:
            instance = super().__new__(cls)
            instance.config_file_path = path
            instance.config = None
            cls._instances[path] = instance
        return cls._instances[path]

    def load(self, *, reload=False):
        """Auto-detect format from file suffix (.json / .yaml / .yml)"""
        if self.config is not None and not reload:
            return self.config

        suffix = self.config_file_path.suffix.lower()
        with open(self.config_file_path, "r", encoding="utf-8") as f:
            try:
                if suffix == ".json":
                    self.config = json.load(f)
                elif suffix in (".yaml", ".yml"):
                    self.config = yaml.safe_load(f)
                else:
                    raise ValueError(f"Unsupported config format: {suffix}")
            except Exception as e:
                raise RuntimeError(f"Failed to load config {self.config_file_path}: {e}")
        return self.config

# cfg = ConfigReader("config/kktix.yaml").load()
# print(cfg["kktix"]["selectors"]["img"])