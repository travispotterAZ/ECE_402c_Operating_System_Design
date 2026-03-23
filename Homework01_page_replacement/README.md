
# Page Replacement Algorithm Simulator

**ECE 402C Operating Systems — University of Arizona**
**Author:** T. Potter

---

## Overview

Implemented and compared three OS page-replacement algorithms in Python, validating correctness against a suite of 27 test cases covering both typical workloads and pathological edge cases.

| Algorithm | Strategy |
|-----------|----------|
| **FIFO** | Evict the page resident longest (Given Completed Example) |
| **LRU** | Evict the least recently accessed page |
| **TwoList** | Active/inactive split; protects hot pages from large sequential scans |

---

## Implementation

### LRU
Used a `collections.OrderedDict` as an ordered set (head = least recently used, tail = most recently used). On a cache hit, `move_to_end()` refreshes the page to the tail in O(1). On a fault, the head is evicted and the new page inserted at the tail — giving O(1) lookup, insertion, and eviction with a single data structure.

### Two-List (Active / Inactive)
Inspired by the Linux 2.4–2.6 kernel page reclaim algorithm. Memory is split into two pools:

- **Inactive list** (cold pages) — newly loaded pages enter here; eviction always comes from this list's head.
- **Active list** (hot pages) — pages promoted here on their second access; protected from direct eviction.

Pages are promoted from inactive → active on a second reference, and demoted back when the active list exceeds its capacity cap. This design prevents a single large sequential scan from flushing frequently-used pages out of memory — a key weakness of plain LRU.

---

## What I Learned

- How page replacement policy directly impacts system performance, and why workload characteristics (locality, scan patterns, working-set size) determine which policy wins.
- The practical tradeoff between simplicity (FIFO) and recency-awareness (LRU) — and why neither alone is sufficient for real OS workloads.
- Why LRU is immune to Belady's anomaly (stack algorithm property) while FIFO is not.
- How the Linux kernel's two-list design solves the scan-resistance problem that plain LRU cannot handle.
- Efficient implementation of ordered eviction structures using `OrderedDict` for O(1) hit/eviction in both LRU and TwoList.
