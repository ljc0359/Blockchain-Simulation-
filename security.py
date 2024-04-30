from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
import hashlib
import json

def generate_key_pair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    '''
    Generate public and private key pair for asymmetric encryption

    Parameters:
    Return:
        return tuple of public and private key
    '''

    private_key = Ed25519PrivateKey.generate() ## generate private key
    public_key = private_key.public_key() ## generate corrsonding public key

    return private_key, public_key

def make_signature(private_key: Ed25519PrivateKey, transaction: bytes) -> str:
	'''
        generate hex representation of signature of the given messsage

        Parameters:
            private_key: The private key to generate the signature
            transaction: bytes 

        Return:
            hex representation of signature of the given messsage
    '''
    # , created by calling private_key.sign and using transaction_bytes function
	return private_key.sign(transaction).hex()

def generate_block_hash(json_obj: "json"):
    '''
        generate hash for the given block

        Parameters:
            json_obj: json representation of block object

        Return:
            hash value for the block
    '''
    block_hash = hashlib.sha256(json_obj.encode("utf-8")).hexdigest()
    return block_hash

