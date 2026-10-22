from __future__ import annotations

import ctypes
import shutil
from pathlib import Path
from ctypes import wintypes


class _MemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class SystemMonitor:
    def __init__(self):
        self._last_idle = self._last_kernel = self._last_user = 0
        self._prime_cpu()

    @staticmethod
    def _filetime_value(value: wintypes.FILETIME) -> int:
        return (value.dwHighDateTime << 32) | value.dwLowDateTime

    def _cpu_times(self) -> tuple[int, int, int]:
        idle = wintypes.FILETIME(); kernel = wintypes.FILETIME(); user = wintypes.FILETIME()
        ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
        return tuple(self._filetime_value(value) for value in (idle, kernel, user))

    def _prime_cpu(self) -> None:
        self._last_idle, self._last_kernel, self._last_user = self._cpu_times()

    def cpu_percent(self) -> float:
        idle, kernel, user = self._cpu_times()
        idle_delta, total_delta = idle-self._last_idle, (kernel-self._last_kernel)+(user-self._last_user)
        self._last_idle, self._last_kernel, self._last_user = idle, kernel, user
        return max(0.0, min(100.0, 100.0*(1.0-idle_delta/total_delta))) if total_delta else 0.0

    @staticmethod
    def memory_percent() -> float:
        status = _MemoryStatus(); status.dwLength = ctypes.sizeof(_MemoryStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return float(status.dwMemoryLoad)

    @staticmethod
    def disk_percent() -> float:
        usage = shutil.disk_usage(Path.home().anchor)
        return 100.0*usage.used/usage.total

    def snapshot(self) -> dict[str, float]:
        return {"CPU": self.cpu_percent(), "RAM": self.memory_percent(), "Disco": self.disk_percent()}
