# build_faiss_index.py
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

# 1. Connexion postgres
def fetch_films() -> list[dict]:
    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"])
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, title FROM film ORDER BY id")
        rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# 2. Construction de l'index
def build_index(films: list[dict]):
    model = SentenceTransformer("all-MiniLM-L6-v2")
    
    titles = [f["title"] for f in films]
    id_map = [f["id"]    for f in films]  # position → film_id
    
    print(f"Encodage de {len(titles)} titres...")
    vectors = model.encode(titles, normalize_embeddings=True, show_progress_bar=True)
    vectors = np.array(vectors, dtype="float32")
    
    index = faiss.IndexFlatIP(vectors.shape[1])  # cosinus (vecteurs normalisés)
    index.add(vectors)
    
    return index, id_map

# 3. Sauvegarde sur disque (pour le réutiliser sans reconstruire)
os.makedirs("data/faiss_index", exist_ok=True)

def save(index, id_map, index_path="data/faiss_index/faiss.index", map_path="data/faiss_index/id_map.npy"):
    faiss.write_index(index, index_path)
    np.save(map_path, np.array(id_map))
    print(f"Index sauvegardé : {index.ntotal} vecteurs")

if __name__ == "__main__":
    films   = fetch_films()
    index, id_map = build_index(films)
    save(index, id_map)