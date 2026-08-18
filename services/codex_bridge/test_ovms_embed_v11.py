import json
import urllib.request
import urllib.error

URL = "http://127.0.0.1:3551/v2/models/BAAI%2Fbge-small-en-v1.5/infer"

BATCH = 32
SEQ = 5

single = [1, 2, 3, 4, 5]
data = [single for _ in range(BATCH)]  # 32x5

payload = {
    "inputs": [
        {
            "name": "Parameter_10391",
            "shape": [BATCH, SEQ],   # <-- batch=32
            "datatype": "INT64",
            "data": data
        }
    ],
    "outputs": [{"name": "last_hidden_state"}]
}

print("SENT PAYLOAD shape:", payload["inputs"][0]["shape"])
print("First row:", payload["inputs"][0]["data"][0])

try:
    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        print("Status:", resp.status)
        print("Body (troncato):", body[:2000])
except urllib.error.HTTPError as e:
    err_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
    print("HTTP Error:", e.code)
    print("Error body:", err_body[:4000])
except Exception as e:
    print("Error:", type(e).__name__, str(e)[:2000])
