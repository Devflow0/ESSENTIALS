import streamlit as st
from cryptography.fernet import Fernet

# Initialize the cipher suite
cipher_suite = Fernet(st.secrets["ENCRYPTION_KEY"].encode())

def encrypt_data(data):
    """Converts plain text into scrambled gibberish."""
    if data is None or data == "UNKNOWN": return data
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data):
    """Converts scrambled gibberish back into plain text."""
    try:
        if encrypted_data is None or encrypted_data == "UNKNOWN": return encrypted_data
        return cipher_suite.decrypt(encrypted_data.encode()).decode()
    except:
        return "⚠️ [ENCRYPTED]"

def encrypt_bytes(data_bytes):
    """Encrypts raw bytes (like audio)."""
    if data_bytes is None: return None
    return cipher_suite.encrypt(data_bytes)

def decrypt_bytes(encrypted_bytes):
    """Decrypts raw bytes (like audio)."""
    try:
        if encrypted_bytes is None: return None
        return cipher_suite.decrypt(encrypted_bytes)
    except:
        return None