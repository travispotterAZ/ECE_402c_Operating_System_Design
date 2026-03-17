#!/usr/bin/env python3
import argparse
import queue
import socket
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

# ----------------------------
# Request/Response protocol
# ----------------------------

@dataclass
class Task:
    conn: socket.socket
    addr: Tuple[str, int]
    line: str
    enqueued_at: float  # perf timing


def parse_and_execute(line: str) -> str:
    """
    Parse a single request line and return a response line (out trailing newline).
    Supported:
      SLEEP ms
      FACT n
      FIB n
      ECHO text...
    """
    line = line.strip()
    if not line:
        return "ERR empty request"

    parts = line.split(" ", 1)
    op = parts[0].upper()
    arg = parts[1] if len(parts) > 1 else ""

    try:
        if op == "SLEEP":
            ms = int(arg)
            if ms < 0 or ms > 10_000:
                return "ERR SLEEP ms must be 0..10000"
            time.sleep(ms / 1000.0)
            return f"OK {ms}"

        elif op == "ECHO":
            return f"OK {arg}"

        else:
            return f"ERR unknown op {op}"
    except ValueError:
        return "ERR invalid argument"


# ----------------------------
# Thread pool + server
# ----------------------------

class ThreadPoolServer:
    def __init__(self, host: str, port: int, workers: int, queue_size: int, reject_when_full: bool):
        self.host = host
        self.port = port
        self.workers = workers
        self.queue_size = queue_size
        self.reject_when_full = reject_when_full 

        self.task_q: "queue.Queue[Task]" = queue.Queue(maxsize=queue_size)

        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._accept_thread: Optional[threading.Thread] = None

        # Stats
        self._lock = threading.Lock()
        self._processed = 0
        self._total_latency = 0.0  # seconds
        self._start_time = time.time()

        self._conn_locks: dict[socket.socket, threading.Lock] = {} #Option (A): per-connection locks - @Potter

    def start(self) -> None:
        """
        Start worker threads + accept loop + stats reporter.
        """
        # COMPLETED(1): start worker threads (self.workers), each runs self._worker_loop

        for i in range(self.workers):                   #Initialize worker-threads for number of worker in ThreadPool defined by self.workers - @Potter
            t = threading.Thread(                       #Thread object
                    target = self._worker_loop,         #Assigns _worker_loop method (thread is waiting to be assigned) 
                    args=(i,),                          #Assigns worker_id to i, no method assigned (idle)
                    daemon = True                       #Classifys it as a daemon thread --> stops thread when main program exits
            )
            t.start()                                   #Launches thread with an assigned method individually
            self._threads.append(t)                     #Stores thread to Pools thread list


        # COMPLETED(2): start accept loop in a thread (self._accept_loop)

        self._accept_thread = threading.Thread(         #This is creating a new thread instance & assigning it to the _accept_thread of our ThreadPool - @Potter      
            target = self._accept_loop,                 #Assigns _accept_loop method (thread handles socket communication & accepting client connections)
            daemon = True
        )
        self._accept_thread.start()                     #Launches the accept thread


        # COMPLETED(3): start stats reporter thread (self._stats_loop)
        #Stats thread is a local variable not a attribute of ThreadPool
        stats_thread = threading.Thread(                #Creating a new thread instance that will be used for reporting stats about ThreadPool - @Potter
            target = self._stats_loop,                  #Assigns _stats_loop method (performance report?)
            daemon = True
        )
        stats_thread.start()                            #Launches stats_thread

        #raise NotImplementedError
        print(f"Server started on {self.host} via {self.port} with {self.workers} workers")

        #We have initialized a set number of [worker threads], [one accept thread], & [one stats thread]
        #---END of start() ---#

    def stop(self) -> None:
        """
        Signal stop and close server.
        """
        self._stop.set()

        # Wake workers blocked on queue.get()
        for _ in range(self.workers):
            try:
                self.task_q.put_nowait(Task(conn=None, addr=("0.0.0.0", 0), line="", enqueued_at=time.time()))  # type: ignore
            except queue.Full:
                pass

        for t in self._threads:
            t.join(timeout=2.0)
        if self._accept_thread:
            self._accept_thread.join(timeout=2.0)

    def _stats_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(2.0)
            with self._lock:
                processed = self._processed
                avg_ms = (self._total_latency / processed * 1000.0) if processed else 0.0
            qlen = self.task_q.qsize()
            elapsed = time.time() - self._start_time
            rps = processed / elapsed if elapsed > 0 else 0.0
            print(f"[stats] processed={processed} avg_latency_ms={avg_ms:.2f} qlen={qlen} rps={rps:.2f}")

    def _accept_loop(self) -> None:
        """
        Accept clients and read lines, enqueue tasks.
        Each client may send many requests; handle line-by-line.
        """
        # COMPLETED(4): create listening socket, accept connections in a loop until stop
        #         For each client connection:
        #           - set TCP_NODELAY (optional)
        #           - read data, split into lines
        #           - for each line:
        #               - enqueue Task(conn, addr, line, time.time())
        #               - if queue full: either block OR reject (depending on reject_when_full)
        #                 If rejecting: send "ERR server busy\n"
        #
        # IMPORTANT: do NOT process requests here; only enqueue.

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)         #Creating new socket instance: AF.INET says this socket uses IPv4 addresses, Is stream based. - @Potter
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)       #Allows for faster server restart: setsockopt (edit config), socket level defintion, allows socket reuse prev address, 1 just enables options
        sock.bind((self.host, self.port))                                #Bind attaches socket to specific IP & Port: has IP host,port as tuple inputs. This is "channel" the server is listening on.
        sock.listen()                                                    #Essentialy activates listening abilites

        print(f"Listening on {self.host} via {self.port}")

        sock.settimeout(1.0) #setting up a timeout for time out after 1 seconds

        connections = []                                    #list of all client connections
        buffers: dict[socket.socket, str] = {}              #allows for every socket to have a buffer so they dont overlap on one buffer
        
        while not self._stop.is_set():                      #Will run until _accept_thread calls stop
            try:
                conn, address = sock.accept()                                 #Connection & address specified: accept a client connection - @Potter
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)    #Sets the TCP to NODELAY: disables Nagle's algorith (small packet buffering), optimal for low-latency server like this one
                conn.setblocking(False)                                       #Non-blocking so we can read multiple clients
                connections.append(conn)
                buffers[conn] = "" #initialize individual buffer
            except socket.timeout:                                                  #If no connection to server_sock.accept() within "try:" is made within 1.0 second
                pass                                                            #Just loop again, basically just looking for connections until stop is called

            for conn in connections[:]: #iterate over all clients
                try:
                    readData = conn.recv(1024).decode("utf-8")      #receive upto 1024 bytes, and then decode bytes into string
                    
                    if not readData: #socket empty
                        conn.close()
                        connections.remove(conn)
                        continue 
                    
                    buffers[conn] += readData                        #adds any received information from client requests

                    while "\n" in buffers[conn]:                                  #will only execute if a new line is present in buffer
                        line, buffers[conn] = buffers[conn].split("\n", 1)        #obtain most current line splitting from buffer at most recent /n
                        line = line.strip()                                       #remove heading or tailing whitespace on line
                        if not line: #checks for empty line
                            continue

                        task = Task(conn, conn.getpeername(), line = line, enqueued_at = time.time())    #Create the task using line: conn=socket, addr=client address, line=request, enqueued-at=time stamp

                        try:
                            self.task_q.put(task, timeout = 1.0)    #Block for up to 1.0 second, then reject
                        except queue.Full:                          #Happens when reject_when_full is True
                            conn.sendall(b"ERR server busy\n")
                except BlockingIOError: #when recv() has no data
                    pass 

                except(BrokenPipeError, ConnectionResetError, ConnectionAbortedError): #handles client disconnects
                    conn.close()
                    connections.remove(conn)
                    buffers.pop(conn, None)
                    pass
                
        for conn in connections:
            conn.close()
        sock.close()

    #This creates a socket that will monitor a port for client requests
    #We run a loop so that we can make a connection between all clients and a socket, then we enque each request as Task requested by client.
    #---END of _accept_loop() ---#


    def _worker_loop(self, worker_id: int) -> None:
        """
        Worker threads: take tasks from queue and process them.
        """
        while not self._stop.is_set():
            task = self.task_q.get()
            # Sentinel check: we used conn=None to wake workers during shutdown
            if task.conn is None:
                self.task_q.task_done()
                break

            started = time.time()
            resp = parse_and_execute(task.line)
            resp_line = resp + "\n"

            # COMPLETED(5): send response back to client safely
            # NOTE: multiple workers may write to the same conn concurrently if client pipelines.
            #       To keep it simple, you can:
            #         (A) add a per-connection lock map
            try:
                with self._lock:                                               #Use existing stats lock so multiple threads cannot make a lock for same socket at once - @Potter
                    if task.conn not in self._conn_locks:                      #Check if this tasks socket has a lock yet
                        self._conn_locks[task.conn] = threading.Lock()         #If not we create one
                    
                    conn_lock = self._conn_locks[task.conn]                    #assign lock to this socket whether just created or already existed
                    
                with conn_lock:                                                #check with lock
                    task.conn.sendall(resp_line.encode("utf-8"))               #send response back to client safely
                
            except (BrokenPipeError, ConnectionResetError, OSError):            #handles client disconnets 
                with self._lock:
                    self._conn_locks.pop(task.conn, None)

            finished = time.time()
            with self._lock:
                self._processed += 1
                self._total_latency += (finished - task.enqueued_at)

            self.task_q.task_done()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--queue", type=int, default=1000)
    ap.add_argument("--reject-when-full", action="store_true", help="reject with ERR server busy instead of blocking")
    args = ap.parse_args()

    srv = ThreadPoolServer(
        host=args.host,
        port=args.port,
        workers=args.workers,
        queue_size=args.queue,
        reject_when_full=args.reject_when_full,
    )

    try:
        srv.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        srv.stop()


if __name__ == "__main__":
    main()
