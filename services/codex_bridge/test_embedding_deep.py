#!/usr/bin/env python3
"""
Deep test for AICarmine OVMS embedding service on port 3551.

Tests:
1. Health check on /get endpoint
2. Single text embedding
3. Batch embedding
4. Similarity comparison between embeddings
5. Embedding dimensionality and structure
"""
import json
import sys
import urllib.request
import time
from pathlib import Path

PORT = 3551
BASE_URL = f"http://127.0.0.1:{PORT}"
TIMEOUT = 30

def json_rpc(method, params=None):
    """Send a raw HTTP POST to the OVMS /get endpoint."""
    payload = json.dumps({"model_name": "BAAI/bge-small-en-v1.5", "texts": [params] if isinstance(params, str) else params}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/get",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))

def test_health():
    """Test 1: Check if /get endpoint responds."""
    print("\n=== TEST 1: Health check ===")
    try:
        req = urllib.request.Request(f"{BASE_URL}/get", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"  Response: {json.dumps(data, indent=2)[:500]}")
            return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def test_single_embedding(text):
    """Test 2: Generate embedding for a single text."""
    print(f"\n=== TEST 2: Single embedding ===")
    print(f"  Input: '{text}'")
    try:
        payload = json.dumps({"model_name": "BAAI/bge-small-en-v1.5", "texts": [text]}).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/get",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            embedding = result.get("outputs", [{}])[0] if "outputs" in result else result.get("embeddings", [{}])[0]
            print(f"  Output keys: {list(result.keys())}")
            print(f"  Embedding shape: {len(embedding)} dimensions")
            print(f"  First 5 values: {embedding[:5]}")
            return result
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

def test_similarity(text1, text2):
    """Test 3: Compute cosine similarity between two embeddings."""
    print(f"\n=== TEST 3: Similarity comparison ===")
    print(f"  Text A: '{text1}'")
    print(f"  Text B: '{text2}'")
    
    # Get embedding for text1
    emb1 = None
    payload = json.dumps({"model_name": "BAAI/bge-small-en-v1.5", "texts": [text1]}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/get",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        result1 = json.loads(resp.read().decode("utf-8"))
        emb1 = result1.get("outputs", [{}])[0] if "outputs" in result1 else result1.get("embeddings", [{}])[0]
    
    # Get embedding for text2
    payload = json.dumps({"model_name": "BAAI/bge-small-en-v1.5", "texts": [text2]}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/get",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        result2 = json.loads(resp.read().decode("utf-8"))
        emb2 = result2.get("outputs", [{}])[0] if "outputs" in result2 else result2.get("embeddings", [{}])[0]
    
    # Compute cosine similarity
    dot_product = sum(a * b for a, b in zip(emb1, emb2))
    norm_a = sum(a * a for a in emb1) ** 0.5
    norm_b = sum(b * b for b in emb2) ** 0.5
    similarity = dot_product / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0
    
    print(f"  Cosine similarity: {similarity:.6f}")
    return similarity

def test_batch_embedding(texts):
    """Test 4: Generate embeddings for multiple texts at once."""
    print(f"\n=== TEST 4: Batch embedding ===")
    print(f"  Input count: {len(texts)}")
    try:
        payload = json.dumps({"model_name": "BAAI/bge-small-en-v1.5", "texts": texts}).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/get",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            print(f"  Output keys: {list(result.keys())}")
            embeddings = result.get("embeddings", [])
            print(f"  Batch size: {len(embeddings)}")
            if embeddings:
                print(f"  First embedding shape: {len(embeddings[0])} dimensions")
            return result
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

def test_structural_similarity():
    """Test 5: Structural similarity (should be high)."""
    text1 = "Il gatto dorme sul divano"
    text2 = "Il felino riposa sul sofà"
    return test_similarity(text1, text2)

def test_semantic_similarity():
    """Test 6: Semantic similarity (should be moderate-high)."""
    text1 = "La tecnologia AI sta cambiando il mondo"
    text2 = "Il machine learning trasforma l'industria tecnologica"
    return test_similarity(text1, text2)

def test_dissimilarity():
    """Test 7: Dissimilarity (should be low)."""
    text1 = "La tecnologia AI sta cambiando il mondo"
    text2 = "Stamane ho mangiato una pizza con gli amici"
    return test_similarity(text1, text2)

def main():
    print("=" * 60)
    print("AICarmine OVMS Embedding Deep Test")
    print(f"Target: {BASE_URL}")
    print("=" * 60)
    
    # Test 1: Health check
    health_ok = test_health()
    
    # Test 2: Single embedding
    single_result = test_single_embedding("Hello world, this is a test embedding")
    
    # Test 3: Similarity tests
    structural_sim = test_structural_similarity()
    semantic_sim = test_semantic_similarity()
    dissimilarity_sim = test_dissimilarity()
    
    # Test 4: Batch embedding
    batch_result = test_batch_embedding([
        "Python is a programming language",
        "JavaScript runs in the browser",
        "Rust gives you memory safety"
    ])
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Health check: {'PASS' if health_ok else 'FAIL'}")
    print(f"  Single embedding: {'PASS' if single_result else 'FAIL'}")
    print(f"  Structural similarity: {structural_sim:.6f} (expect high)")
    print(f"  Semantic similarity: {semantic_sim:.6f} (expect moderate-high)")
    print(f"  Dissimilarity: {dissimilarity_sim:.6f} (expect low)")
    print(f"  Batch embedding: {'PASS' if batch_result else 'FAIL'}")
    print("=" * 60)

if __name__ == "__main__":
    main()