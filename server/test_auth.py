import requests
import sys

BASE_URL = "http://localhost:8000/api/auth"

print("--- Testing Fast Pass login (ryuzaki2k5) ---")
resp = requests.post(f"{BASE_URL}/login", json={"email": "ryuzaki2k5@gmail.com"})
print(f"Status: {resp.status_code}")
print(resp.json())

print("\n--- Testing Fast Pass login (reddyanugya) ---")
resp1 = requests.post(f"{BASE_URL}/login", json={"email": "reddyanugya@gmail.com"})
print(f"Status: {resp1.status_code}")
print(resp1.json())

print("\n--- Testing Standard Registration ---")
resp2 = requests.post(f"{BASE_URL}/register", json={
    "username": "testuser123",
    "email": "testuser123@example.com",
    "role": "user"
})
print(f"Status: {resp2.status_code}")
print(resp2.json())

print("\n--- Testing Standard Login ---")
resp3 = requests.post(f"{BASE_URL}/login", json={"email": "testuser123@example.com"})
print(f"Status: {resp3.status_code}")
print(resp3.json())
