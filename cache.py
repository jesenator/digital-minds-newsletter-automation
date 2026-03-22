import json, os, hashlib, copy
from datetime import datetime, timedelta
from threading import RLock
from functools import wraps

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "digital-minds")


def cached(cache_name, expiry=None, active=True):
  def decorator(func):
    fc = FileCache(cache_name)
    @wraps(func)
    def wrapper(*args, **kwargs):
      if not active:
        return func(*args, **kwargs)
      key = hashlib.md5(str((args, kwargs)).encode()).hexdigest()
      result = fc.get(key)
      if result is None:
        result = func(*args, **kwargs)
        fc.set(key, result, expiry)
      return result
    return wrapper
  return decorator


class FileCache:
  _instances = {}
  _global_lock = RLock()

  def __new__(cls, cache_name):
    with cls._global_lock:
      if cache_name not in cls._instances:
        inst = super().__new__(cls)
        inst._init(cache_name)
        cls._instances[cache_name] = inst
      return cls._instances[cache_name]

  def _init(self, cache_name):
    os.makedirs(CACHE_DIR, exist_ok=True)
    self.cache_file = os.path.join(CACHE_DIR, f"{cache_name}.json")
    self.cache = self._load()
    self._lock = RLock()

  def _load(self):
    try:
      with open(self.cache_file, "r") as f:
        return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
      return {}

  def _save(self):
    with open(self.cache_file, "w") as f:
      json.dump(self.cache, f)

  def get(self, key):
    with self._lock:
      if key not in self.cache:
        return None
      data = self.cache[key]
      if datetime.now() > datetime.fromisoformat(data["expiry"]):
        del self.cache[key]
        self._save()
        return None
      return copy.deepcopy(data["value"])

  def set(self, key, value, expiry=None):
    with self._lock:
      expiry = expiry or 86400
      if expiry <= 0:
        return
      try:
        v = copy.deepcopy(value)
        json.dumps(v)
        self.cache[key] = {
          "value": v,
          "expiry": (datetime.now() + timedelta(seconds=expiry)).isoformat(),
        }
        self._save()
      except (TypeError, ValueError):
        pass
