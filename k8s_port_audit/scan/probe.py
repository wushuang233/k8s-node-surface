from __future__ import annotations

import asyncio
import copy
import errno
import time
from typing import Any, Callable, Iterable

from ..domain import ProbeTarget
from ..report import status_priority, utc_now


def classify_os_error(error: OSError) -> str:
    if error.errno == errno.ECONNREFUSED:
        return "closed"
    if error.errno in {errno.ETIMEDOUT}:
        return "timeout"
    if error.errno in {errno.EHOSTUNREACH, errno.ENETUNREACH}:
        return "unreachable"
    return "error"


async def probe_target(target: ProbeTarget, timeout_seconds: float) -> dict[str, Any]:
    started_at = utc_now()
    start = time.perf_counter()

    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(target.address, target.port),
            timeout=timeout_seconds,
        )
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        writer.close()
        await writer.wait_closed()
        return {
            "address": target.address,
            "port": target.port,
            "status": "open",
            "latency_ms": latency_ms,
            "error": None,
            "started_at": started_at,
            "sources": target.sources,
        }
    except asyncio.TimeoutError:
        return {
            "address": target.address,
            "port": target.port,
            "status": "timeout",
            "latency_ms": None,
            "error": "connection timed out",
            "started_at": started_at,
            "sources": target.sources,
        }
    except ConnectionRefusedError:
        return {
            "address": target.address,
            "port": target.port,
            "status": "closed",
            "latency_ms": None,
            "error": "connection refused",
            "started_at": started_at,
            "sources": target.sources,
        }
    except OSError as exc:
        return {
            "address": target.address,
            "port": target.port,
            "status": classify_os_error(exc),
            "latency_ms": None,
            "error": str(exc),
            "started_at": started_at,
            "sources": target.sources,
        }
    except Exception as exc:
        return {
            "address": target.address,
            "port": target.port,
            "status": "error",
            "latency_ms": None,
            "error": str(exc),
            "started_at": started_at,
            "sources": target.sources,
        }


async def probe_targets(
    targets: Iterable[ProbeTarget],
    timeout_seconds: float,
    concurrency: int,
    keep_result: Callable[[dict[str, Any]], bool] | None = None,
) -> list[dict[str, Any]]:
    worker_count = max(1, concurrency)
    # 有界队列能限制一次性堆积的待探测目标数量，避免 1-65535 节点扫描时内存暴涨。
    queue: asyncio.Queue[ProbeTarget | None] = asyncio.Queue(maxsize=worker_count * 4)
    results: list[dict[str, Any]] = []
    keep_result = keep_result or (lambda _: True)

    async def producer() -> None:
        for target in targets:
            await queue.put(target)
        for _ in range(worker_count):
            await queue.put(None)

    async def worker() -> None:
        while True:
            target = await queue.get()
            try:
                if target is None:
                    return
                result = await probe_target(target, timeout_seconds)
                if keep_result(result):
                    results.append(result)
            finally:
                queue.task_done()

    producer_task = asyncio.create_task(producer())
    workers = [asyncio.create_task(worker()) for _ in range(worker_count)]
    await producer_task
    await queue.join()
    await asyncio.gather(*workers)
    return results


def merge_probe_results(*result_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, int], dict[str, Any]] = {}

    for result_group in result_groups:
        for result in result_group:
            key = (result["address"], result["port"])
            existing = merged.get(key)
            if existing is None:
                merged[key] = copy.deepcopy(result)
                continue

            existing_sources = existing.setdefault("sources", [])
            for source in result.get("sources", []):
                if source not in existing_sources:
                    existing_sources.append(source)

            existing_priority = status_priority(existing.get("status"))
            result_priority = status_priority(result.get("status"))

            if result_priority < existing_priority:
                replacement = copy.deepcopy(result)
                replacement["sources"] = existing_sources
                merged[key] = replacement
                continue

            if existing.get("latency_ms") is None and result.get("latency_ms") is not None:
                existing["latency_ms"] = result["latency_ms"]

    return sorted(merged.values(), key=lambda item: (item["address"], item["port"]))
