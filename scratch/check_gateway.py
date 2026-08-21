import urllib.request
import json

try:
    req = urllib.request.urlopen("http://127.0.0.1:8111/v1/status")
    print("Gateway Response:", req.read().decode())
except Exception as e:
    print("Gateway Error:", e)
