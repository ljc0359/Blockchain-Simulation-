import socket
import struct
from enum import Enum
import json
import cryptography.hazmat.primitives.asymmetric.ed25519 as ed25519
import re
from cryptography.exceptions import InvalidSignature

TransactionValidationError = Enum('TransactionValidationError', ['INVALID_JSON', 'INVALID_SENDER', 'INVALID_MESSAGE', 'INVALID_SIGNATURE', 'INVALID_NONCE'])
sender_valid = re.compile('^[a-fA-F0-9]{64}$')

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

def transaction_bytes(transaction: dict) -> bytes:
	return json.dumps({'sender': transaction['sender'], 'message': transaction['message']}, sort_keys=True).encode()

def make_transaction(sender, message, signature) -> str:
	return json.dumps({'sender': sender, 'message': message, 'signature': signature})

def transaction_bytes(transaction: dict) -> bytes:
	return json.dumps({'sender': transaction['sender'], 'message': transaction['message'], 'nonce': transaction['nonce']}, sort_keys=True).encode()

def validate_transaction(transaction: str, nonce) -> dict | TransactionValidationError:
	tx = transaction

	if not(tx.get('sender') and isinstance(tx['sender'], str) and sender_valid.search(tx['sender'])):
		return TransactionValidationError.INVALID_SENDER

	if not(tx.get('message') and isinstance(tx['message'], str) and len(tx['message']) <= 70 and tx['message'].isalnum()):
		return TransactionValidationError.INVALID_MESSAGE

	public_key = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(tx['sender']))
	try:
		public_key.verify(bytes.fromhex(tx['signature']), transaction_bytes(tx))
	except InvalidSignature:
		return TransactionValidationError.INVALID_SIGNATURE
	
	if "nonce" not in tx or tx["nonce"] <= nonce:
		return TransactionValidationError.INVALID_NONCE
	
	return tx