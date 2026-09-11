import os
import threading
import chromadb

from mempalace.backends.chroma import ChromaBackend, ChromaCollection, _fix_blob_seq_ids

_client_cache = {}
_client_lock = threading.Lock()

def _get_collection_reutilizando_client(self, palace_path, collection_name="mempalace_drawers", create=False):
    if not create and not os.path.isdir(palace_path):
        raise FileNotFoundError(palace_path)
    if create:
        os.makedirs(palace_path, exist_ok=True)
        try:
            os.chmod(palace_path, 0o700)
        except (OSError, NotImplementedError):
            pass
    _fix_blob_seq_ids(palace_path)
    with _client_lock:
        client = _client_cache.get(palace_path)
        if client is None:
            client = chromadb.PersistentClient(path=palace_path)
            _client_cache[palace_path] = client
    if create:
        collection = client.get_or_create_collection(
            collection_name, metadata={"hnsw:space": "cosine"}
        )
    else:
        collection = client.get_collection(collection_name)
    return ChromaCollection(collection)

def aplicar_patch():
    ChromaBackend.get_collection = _get_collection_reutilizando_client
