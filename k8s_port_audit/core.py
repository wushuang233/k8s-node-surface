"""兼容导出层。

保留给仍然引用 ``k8s_port_audit.core`` 的旧入口。
"""

from .report import emit_report, utc_now
from .runtime.state import ReportStore, ScanCoordinator
from .scan.scanner import HostExposureScanner

__all__ = [
    "HostExposureScanner",
    "ReportStore",
    "ScanCoordinator",
    "emit_report",
    "utc_now",
]
