import ipaddress
import os
from queue import Queue
import socket
import struct
import json
import socket
import sys
import threading
import time
from types import NoneType
from typing import Any, Callable, Dict, Tuple, Type
import network
from security import generate_key_pair, generate_block_hash, make_signature
import binascii

WORKER_COUNT = 8

TaskQueue = Queue["Task"]
RequestHandlerRegister = dict[str, Type["HandlingRequest"]]
SocketAddress = Tuple[str, int]
ResponseCallback = Callable[["AppContext", SocketAddress, Any], NoneType]
PeerRegister = Dict[SocketAddress, "ClientThread"]

class AppContext:
    request_handler_register: RequestHandlerRegister
    peer_register: PeerRegister
    task_queue: TaskQueue
    transaction_pool: list


    def __init__(self, port):
        self.request_handler_register = {}
        self._lock = threading.Lock()
        self.peer_register = {}
        self.task_queue = Queue()
        self.port = port
        self.transaction_pool = []
    
    def debug_print(self, str):
        """Print a debug message."""
        print(str, flush=True)

    def execute_task(self, task: "Task"):
        """Delegate a task to one of the workers."""
        self.task_queue.put(task)

    def register_request_handler(self, identifier: str, handler: Type["HandlingRequest"]):
        """Register a class derived from HandlingRequest for processing a request from peers. """
        self.request_handler_register[identifier] = handler

    def broadcast_request(self, request: "Request"):
        """Broadcast a request to every peer."""
        for peer in self.peer_register.values():
            if not peer.crashed:
                peer.request_queue.put(request)

class Task:
    ctx: "AppContext"

    def execute(self):
        raise NotImplementedError()
    
    def __init__(self, ctx: "AppContext") -> None:
        self.ctx = ctx

class HandlingRequest(Task):
    def __init__(self, ctx: AppContext, sock: socket.socket, payload: Any, address: Tuple, nonce) -> None:
        super().__init__(ctx)
        self.payload = payload
        self.sock = sock
        self.address = address
        self.nonce = nonce

    def reply(self, msg: Any):
        """Reply the peer who has sent the request."""
        msg = json.dumps(msg).encode()
        send_prefixed(self.sock, msg)

    def execute(self):
        raise NotImplementedError("This is an abstract class")

class HandlingTestRequest(HandlingRequest):
    """ATTENTION: THIS CLASS SERVES AS A TEMPLATE FOR HANDLING REQUESTS"""
    def execute(self):
        # Step1: process a test request
        self.ctx.debug_print("Processing a test request")
        # Step2: Send a message back to client
        self.reply({"response": "Hi"})

class HandlingBlockRequest(HandlingRequest):
    def execute(self):
        # TODO: process a block request
        pass
        

class HandlingTransactionRequest(HandlingRequest):
    def execute(self):
        print(f"Received a transaction from node {self.address[0]}: {self.payload}")

        error = False
        tx = network.validate_transaction(self.payload, self.nonce)

        if(tx == network.TransactionValidationError.INVALID_JSON):
            print(f"[TX] Received an invalid transaction, wrong data - {self.payload}")
            error = True
        elif(tx == network.TransactionValidationError.INVALID_MESSAGE):
            print(f"[TX] Received an invalid transaction, wrong message - {self.payload}")
            error = True
        elif(tx == network.TransactionValidationError.INVALID_NONCE):
            print(f"[TX] Received an invalid transaction, wrong nonce - {self.payload}")
            error = True
        elif(tx == network.TransactionValidationError.INVALID_SENDER):
            print(f"[TX] Received an invalid transaction, wrong sender - {self.payload}")
            error = True
        elif(tx == network.TransactionValidationError.INVALID_SIGNATURE):
            print(f"[TX] Received an invalid transaction, wrong signature mssage - {self.payload}")
            error = True
        
        if not error:
            self.ctx.transaction_pool.append(tx)
            self.reply({"response": "True"})
        else:
            self.reply({"response": "False"})

class HandlingResponse(Task):
    def __init__(self, ctx: AppContext, socket_addr: SocketAddress, callback: ResponseCallback, message: Any) -> None:
        super().__init__(ctx)
        self.message = message
        self.socket_addr = socket_addr
        self.callback = callback

    def execute(self):
        self.callback(self.ctx, self.socket_addr, self.message)

class RequestDispatcher(Task):
    def __init__(self, ctx: AppContext, sock: socket.socket, data: Any, address: Tuple, nonce: int):
        super().__init__(ctx)
        self.data = data
        self.sock = sock
        self.address = address
        self.nonce = nonce

    def execute(self):
        message_type = self.data["type"]
        handler_class = self.ctx.request_handler_register.get(message_type)
        if handler_class is None:
            raise NotImplementedError(f"The message type '{message_type}' has no handler")
        # Check the type of the message and invoke the correct worker thread
        task = handler_class(self.ctx, self.sock, self.data["payload"], self.address, self.nonce)
        self.ctx.execute_task(task)

class Worker(threading.Thread):
    task_queue: TaskQueue

    def __init__(self, task_queue: TaskQueue):
        super().__init__()
        self.task_queue = task_queue
        self.daemon = True

    def run(self):
        while True:
            if not self.task_queue.empty():
                task = self.task_queue.get()
                task.execute()
                self.task_queue.task_done()

class Request:
    def __init__(self, type: str, payload: Any, callback: ResponseCallback):
        self.type = type
        self.payload = payload
        self.callback = callback

class ClientThread(threading.Thread):
    request_queue: Queue[Request]

    def __init__(self, ctx: AppContext, address: str, port: int):
        super().__init__()
        self.ctx = ctx
        self.address = address
        self.port = port
        self.connected = False
        self.crashed = False
        self.request_queue = Queue()

    def run(self):
        sock = None
        remaining_chances = 2  # Initial try + One retry = 2 chances
        while True:
            if not self.connected:
                if remaining_chances > 0:
                    remaining_chances -= 1
                    try:
                        # Trying to connect to the slave router
                        self.ctx.debug_print(f"I am trying to connect to peer {self.address}:{self.port}")
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.connect((self.address, self.port))
                        # Print a success message
                        self.ctx.debug_print(f"I've connected to the peer {self.address}:{self.port}")
                        self.connected = True
                    except socket.error as e:
                        self.ctx.debug_print(f"Failed to connect the peer {self.address}:{self.port}: {e}. Retrying one more time...")
                        time.sleep(3)  # Wait for a bit before retrying to avoid spamming connection attempts
                else:
                    print("I am crashed")
                    self.crashed = True
                    return
            else:
                try:
                    # SENDING
                    request = self.request_queue.get()
                    message = json.dumps({
                         "type": request.type,
                         "payload": request.payload
                    }).encode()
                    send_prefixed(sock, message)
                    # RECEIVING
                    received_bytes = recv_prefixed(sock)
                    received_data = json.loads(received_bytes.decode())
                    self.ctx.execute_task(HandlingResponse(self.ctx, (self.address, self.port), request.callback, received_data))
                except socket.error as e:
                    self.ctx.debug_print(f"Connection error to the peer {self.slave_id}: {e}")
                    self.connected = False
            time.sleep(0.1)

# A representative is an agent who is spawned for every incoming master connected.
class RepresentativeThread(threading.Thread):
    def __init__(self, conn: socket.socket, ctx: AppContext, address: Tuple):
        super().__init__()
        self.ctx = ctx
        self.conn = conn
        self.address = address
        self.nonce = 0

    def run(self):
        try:
            while True:
                # receive a request
                data = json.loads(recv_prefixed(self.conn).decode())
                # process the request
                self.ctx.execute_task(RequestDispatcher(self.ctx, self.conn, data, self.address, self.nonce))
                time.sleep(0.1)
        except socket.error as e:
            pass

# A reception is a thread who spawns a RepresentativeThread for every incoming master.
class ReceptionThread(threading.Thread):
    ctx: AppContext
    port: int

    def __init__(self, ctx: AppContext, port: int):
        super().__init__()
        self.ctx = ctx
        self.port = port

    def run(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server_socket.bind(("127.0.0.1", self.port))
            server_socket.listen()
            self.ctx.debug_print(f"Listening on 127.0.0.1:{self.port}")
        except socket.error as e:
            self.ctx.debug_print(f"Failed to listen on 127.0.0.1:{self.port} - {e}")
            server_socket.close()
            return  # Early exit on failure to bind or listen
        try:
            while True:
                conn, (client_addr, client_port) = server_socket.accept()
                self.ctx.debug_print(f"Connected by the client {client_addr}: {client_port}")
                rep = RepresentativeThread(conn, self.ctx, (client_addr, client_port))
                rep.start()

        except Exception as e:
            self.ctx.debug_print(f"Error during server operation: {e}")
        finally:
            self.ctx.debug_print("Server is shutting down")
            server_socket.close()

def recv_exact(sock: socket.socket, msglen):
	chunks = []
	bytes_recd = 0
	while bytes_recd < msglen:
		chunk = sock.recv(min(msglen - bytes_recd, 2048))
		if chunk == b'':
			raise RuntimeError("socket connection broken")
		chunks.append(chunk)
		bytes_recd = bytes_recd + len(chunk)
	return b''.join(chunks)

def send_exact(sock: socket.socket, msg: bytes):
	totalsent = 0
	while totalsent < len(msg):
		sent = sock.send(msg[totalsent:])
		if sent == 0:
			raise RuntimeError("socket connection broken")
		totalsent = totalsent + sent

def recv_prefixed(sock: socket.socket):
	size_bytes = recv_exact(sock, 2)
	size = struct.unpack("!H", size_bytes)[0]
	if size == 0:
		raise RuntimeError("empty message")
	if size > 65535 - 2:
		raise RuntimeError("message too large")
	return recv_exact(sock, size)

def send_prefixed(sock: socket.socket, msg: bytes):
	size = len(msg)
	if size == 0:
		raise RuntimeError("empty message")
	if size > 65535 - 2:
		raise RuntimeError("message too large")
	size_bytes = struct.pack("!H", size)
	send_exact(sock, size_bytes + msg)

def read_peers(filepath):
    """Read peers from a file and return a list of valid (addr, port) tuples."""
    peers = []
    with open(filepath, "r") as fo:
        for peer in fo.read().splitlines():
            try:
                addr, port = peer.split(":", 1)
                ipaddress.ip_address(addr)  # Validate IP address
                port = int(port)  # Validate port number
                if not (1 <= port <= 65535):
                    raise ValueError("Port must be between 1 and 65535")
                peers.append((addr, port))
            except ValueError as e:
                print(f"Error with peer '{peer}': {e}")
    return peers

def connect_peers(ctx, peers):
    """Establish connections with a list of peers."""
    for addr, port in peers:
        try:
            client_thread = ClientThread(ctx, addr, port)
            client_thread.start()
            ctx.peer_register[(addr, port)] = client_thread
        except Exception as e:
            print(f"Failed to connect to {addr}:{port} - {e}")

def main():
    if len(sys.argv) < 3:
        print("Usage: python COMP3221_BlockchainNode.py <port> <filepath>")
        sys.exit(1)

    # Check if port number is valid
    try:
        port = int(sys.argv[1])
    except ValueError:
        print("Error: Port must be an integer.")
        sys.exit(1)

    if not 1024 <= port <= 65535:
        print("Error: Port number must be between 1024 and 65535.")
        sys.exit(1)

    filepath = sys.argv[2]

    # Check if the nodes.txt exists and is readable
    if not os.path.isfile(filepath) or not os.access(filepath, os.R_OK):
        print(f"Error: The file {filepath} does not exist or is not readable.")
        sys.exit(1)

    ctx = AppContext(port)

    # Register request handlers
    ctx.register_request_handler("values", HandlingBlockRequest)
    ctx.register_request_handler("transaction", HandlingTransactionRequest)
    ctx.register_request_handler("test", HandlingTestRequest)

    # Start workers
    for i in range(WORKER_COUNT):
        worker = Worker(ctx.task_queue)
        worker.start()

    # Start the reception thread
    reception_thread = ReceptionThread(ctx, port)
    reception_thread.start()

    # Allow some time to wait for all peers start listening
    time.sleep(2)

    # Connect all peers
    peers = read_peers(filepath)
    connect_peers(ctx, peers)
    

    private_key, public_key = generate_key_pair()
    hex_string = binascii.hexlify(public_key.public_bytes_raw()).decode('ascii')
    signature = make_signature(private_key, network.transaction_bytes({"sender": hex_string, "message": "hello", "nonce": 10}))
    # Broadcast a test message
    
    payload_ = {"sender": hex_string, "message": "hello", "nonce": 10, "signature": signature}
    """ATTENTION: THIS SERVES AS A TEMPLATE FOR BROADCASTING REQUESTS."""
    ctx.broadcast_request(Request(
         type="transaction", 
         payload=payload_, 
         callback = lambda ctx, addr, msg:  # Callback method is used for handling server's response
         ctx.debug_print(f"Received a response from {addr[0]}:{addr[1]} : " + msg["response"])))


if __name__ == "__main__":
    main()