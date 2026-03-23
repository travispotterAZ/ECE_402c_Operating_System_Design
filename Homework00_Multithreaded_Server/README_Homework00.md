# Multithreaded TCP Server with Thread Pool

**ECE 402C Operating Systems — University of Arizona**
**Author:** T. Potter

---

## Overview

Built a concurrent TCP server in Python capable of handling many simultaneous clients using a fixed thread pool. The server accepts text-based requests over TCP, processes them concurrently across worker threads, and responds with results or graceful error messages under load.

Supported operations:
- `SLEEP ms` — sleeps for the given number of milliseconds, returns `OK ms`
- `ECHO text` — echoes the argument back, returns `OK text`

---

## Architecture

### Thread Pool
A fixed number of worker threads (`--workers`) are spawned at startup and kept alive for the lifetime of the server. Each worker blocks on a shared task queue, picks up a request, processes it, and sends the response back to the client. This avoids the overhead of spawning a new thread per request, which does not scale under high concurrency.

### Bounded Task Queue
Incoming requests are enqueued into a `queue.Queue` with a configurable maximum size (`--queue`, default 1000). This bounds memory usage and prevents the server from being overwhelmed by a flood of slow requests.

### Backpressure
When the queue is full, the accept loop attempts to enqueue with a 1-second timeout. If the queue remains full, the server responds immediately with `ERR server busy` and drops the request — protecting the server from unbounded request buildup.

### Concurrency Safety
Multiple worker threads can write to the same client socket if requests are pipelined. A per-connection lock map (`_conn_locks`) ensures only one thread writes to a given socket at a time, preventing interleaved or corrupted responses. The lock map itself is protected by the global stats lock to prevent races during lock creation.

### Non-blocking Accept Loop
The accept loop runs in a dedicated thread and uses non-blocking sockets (`setblocking(False)`) with per-client receive buffers. This allows a single thread to multiplex reads across all connected clients without blocking on any one of them, while worker threads independently handle the actual request processing.

---

## Testing

All tests run with the server configured at `--workers 8 --queue 500`.

| Test | Clients | Requests | In-flight | Sent | Received | OK | ERR | RPS |
|------|---------|----------|-----------|------|----------|----|-----|-----|
| Basic single request | 1 | 1 | 1 | 1 | 1 | 1 | 0 | 2.97 |
| Single client pipelined | 1 | 100 | 10 | 100 | 100 | 100 | 0 | 11.81 |
| Multi-client moderate load | 10 | 50 | 10 | 500 | 500 | 500 | 0 | 29.91 |
| High stress (queue saturation) | 50 | 200 | 10 | 650 | 150 | 150 | 0 | 13.95 |

The high-stress test intentionally saturates the queue — the server correctly applies backpressure, rejects excess requests with `ERR server busy`, and continues serving accepted requests without crashing or stalling.

---

## What I Learned

- How thread pools improve scalability over one-thread-per-request by amortizing thread creation cost and capping resource usage.
- How bounded queues and backpressure prevent a server from being overwhelmed, and why both are necessary together.
- How to safely share resources (sockets, counters) across threads using locks, and how to scope locking to minimize contention.
- How non-blocking I/O and per-client buffers allow a single thread to multiplex many concurrent connections.
- How to design for graceful shutdown: daemon threads, sentinel values to unblock workers, and socket cleanup on exit.
