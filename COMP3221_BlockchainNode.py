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
import math

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
    block_chain: list
    consensus: bool
    list_of_block_proposal: list
    clients: list["RepresentativeThread"]

    def __init__(self, port):
        self.request_handler_register = {}
        self._lock = threading.Lock()
        self.peer_register = {}
        self.task_queue = Queue()
        self.port = port
        self.transaction_pool = []
        self.block_chain = []
        self.init_genesis_block()
        self.consensus = False
        self.list_of_block_proposal = []
        self.clients = []

    def init_genesis_block(self):
        genesis_block = {
            "index": 1,
            "transactions": [],
            "previous_hash": "0000000000000000000000000000000000000000000000000000000000000000",
        }

        current_hash = generate_block_hash(json.dumps(genesis_block))

        genesis_block["current_hash"] = current_hash
        self.block_chain.append(genesis_block)

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

    def send_request(self, addr: SocketAddress, request: "Request"):
        """Send a request to every peer."""
        if addr not in self.peer_register.keys():
            print("Current peer members:", list(self.peer_register.keys()))
            print("Requested socket address", addr)
            raise KeyError("Peer is not in the register")
        self.peer_register[addr].request_queue.put(request)

    def consensus_algorithm(self):
        count = 0
        client_index = {}
        for client in self.peer_register.values():
            client_index[client] = count
            count += 1
            client.conn.settimeout(5)

        responses_count = [0] * len(self.clients)
        def callback(ctx: AppContext, addr, msg: Any):
            print("Recived Message", msg)
            for new_block_proposal in msg:
                if new_block_proposal not in ctx.list_of_block_proposal:
                    ctx.list_of_block_proposal.append(new_block_proposal)
            cur_client = ctx.peer_register[addr]
            responses_count[client_index[cur_client]] += 1
        
        ## excluding self in the peer_register
        f = math.ceil(len(self.peer_register.values()) / 2)
        for _ in range(f):
            self.broadcast_request(Request(
            type="values",
            payload= len(self.block_chain) + 1,
            callback = callback))
            
            while(not self.check_client()):
                pass
            
        can_decide = responses_count.count(f) >= len(self.clients) - f

        if can_decide:
            decided_block_proposal = self.decide_block()

            for transaction in decided_block_proposal["transactions"]:
                self.transaction_pool.remove(transaction)
            
            self.block_chain.append(decided_block_proposal)
            self.debug_print(f"[CONSENSUS] Appended to the blockchain: {decided_block_proposal["current_hash"]}")
        else:
            print(responses_count)
            print(self.list_of_block_proposal)
            ## consensus algorithm fails
            self.debug_print("Can't decide on the current block, terminating....")

        for client in self.clients:
            client.conn.settimeout(None)
        
        self.consensus = False

    def decide_block(self):
        
        lowest_hash = None
        block_obj = None
        self.debug_print("Following is block proposals")
        self.debug_print(self.list_of_block_proposal)
        self.debug_print("\n\n")
        for i, block_proposal in enumerate(self.list_of_block_proposal):
            self.debug_print(block_proposal)
            if len(block_proposal["transactions"]) != 0:
                if lowest_hash == None:
                    lowest_hash = block_proposal["current_hash"]
                    block_obj = block_proposal
                else:
                    if block_proposal["current_hash"] < lowest_hash:
                        lowest_hash = block_proposal["current_hash"]
                        block_obj = block_proposal
        
        return block_obj


    def check_client(self):
        flag = True
        for client in self.peer_register.values():
            if(not (client.ready or client.crashed)):
                flag = False
        
        return flag


"""
def broadcast(self, ps: list['Process'], f: int):
		assert(self not in ps)
		assert(len(ps) >= f)
		responses_count = [0] * len(ps)
		for _ in range(f + 1):
			for idx, p in enumerate(ps):
				v_p = p.values()
				if v_p:
					self.v.update(v_p)
					responses_count[idx] += 1
		can_decide = responses_count.count(f + 1) >= len(ps) - f
		return min(self.v) if can_decide else None

""" 
class Task:
    ctx: "AppContext"

    def execute(self):
        raise NotImplementedError()
    
    def __init__(self, ctx: "AppContext") -> None:
        self.ctx = ctx

class HandlingRequest(Task):
    def __init__(self, ctx: AppContext, sock: socket.socket, payload: Any, address: Tuple, nonce, representative: "RepresentativeThread") -> None:
        super().__init__(ctx)
        self.payload = payload
        self.sock = sock
        self.address = address
        self.nonce = nonce
        self.representative = representative

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

def generate_block_proposal(ctx: AppContext):
    block_proposal = {
        "index": len(ctx.block_chain) + 1,
        "transactions": [ctx.transaction_pool[0]] if len(ctx.transaction_pool) != 0 else [],
        "previous_hash": ctx.block_chain[-1]["current_hash"]
    }

    current_hash = generate_block_hash(json.dumps(block_proposal))
    block_proposal["current_hash"] = current_hash

    return block_proposal

class HandlingBlockRequest(HandlingRequest):
    def execute(self):
        # TODO: process a block request
        self.ctx.debug_print("Recived Block request")
        if not self.ctx.consensus:
            self.ctx.debug_print("Start consensus")
            self.ctx.list_of_block_proposal = []
            self.ctx.consensus = True
            self.ctx.consensus_algorithm()
            self.ctx.list_of_block_proposal.append(generate_block_proposal(self.ctx))
            self.reply(self.ctx.list_of_block_proposal)
            self.ctx.debug_print(f"Reply with my block proposal: {self.ctx.list_of_block_proposal}")
        else:
            self.reply(self.ctx.list_of_block_proposal)
            self.ctx.debug_print(f"Reply with my block proposal: {self.ctx.list_of_block_proposal}")


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
            print(f"[MEM] Stored transaction in the transaction pool: {tx["signature"]}")
            self.reply({"response": "True"})
            block_proposal = generate_block_proposal(self.ctx)

            self.ctx.debug_print(f"[PROPOSAL] Created a block proposal: {json.dumps(block_proposal)}")
            self.consensus = True
            self.ctx.list_of_block_proposal.append(block_proposal)
            self.ctx.consensus_algorithm()
        else:
            self.reply({"response": "False"})
            
class HandlingCensensus(Task):
    def __init__(self, ctx: AppContext) -> NoneType:
        super().__init__(ctx)

    def execute(self):
        return super().execute()

class HandlingResponse(Task):
    def __init__(self, ctx: AppContext, socket_addr: SocketAddress, callback: ResponseCallback, message: Any) -> None:
        super().__init__(ctx)
        self.message = message
        self.socket_addr = socket_addr
        self.callback = callback

    def execute(self):
        self.callback(self.ctx, self.socket_addr, self.message)

class RequestDispatcher(Task):
    def __init__(self, ctx: AppContext, sock: socket.socket, data: Any, address: Tuple, nonce: int, client_obj: "RepresentativeThread"):
        super().__init__(ctx)
        self.data = data
        self.sock = sock
        self.address = address
        self.nonce = nonce
        self.representative = client_obj

    def execute(self):
        message_type = self.data["type"]
        handler_class = self.ctx.request_handler_register.get(message_type)
        if handler_class is None:
            raise NotImplementedError(f"The message type '{message_type}' has no handler")
        # Check the type of the message and invoke the correct worker thread
        task = handler_class(self.ctx, self.sock, self.data["payload"], self.address, self.nonce, self.representative)
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
        self.ready = False
        self.request_queue = Queue()
        self.conn = None

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
                        self.conn = sock
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
                    self.ready = True
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
        self.local_block_proposals = []
        self.ready = False

    def run(self):
        try:
            while True:
                # receive a request
                data = json.loads(recv_prefixed(self.conn).decode())
                # process the request
                self.ctx.execute_task(RequestDispatcher(self.ctx, self.conn, data, self.address, self.nonce, self))
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
                self.ctx.clients.append(rep)
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

    for i, peer in enumerate(peers):
        if peer[1] == port:
            peers.remove(peer)
            break
    
    print(peers)
    connect_peers(ctx, peers)
    

    private_key, public_key = generate_key_pair()
    hex_string = binascii.hexlify(public_key.public_bytes_raw()).decode('ascii')
    signature = make_signature(private_key, network.transaction_bytes({"sender": hex_string, "message": "hello", "nonce": 0}))
    # Broadcast a test message
    
    payload_ = {"sender": hex_string, "message": "hello", "nonce": 0, "signature": signature}
    """ATTENTION: THIS SERVES AS A TEMPLATE FOR BROADCASTING REQUESTS."""

    if port == 8888:
        ctx.send_request(("127.0.0.1", 8889), Request(
            type="transaction", 
            payload=payload_,
            callback = lambda ctx, addr, msg:  # Callback method is used for handling server's response
            ctx.debug_print(f"Received a response from {addr[0]}:{addr[1]} : " + msg["response"])))


if __name__ == "__main__":
    main()