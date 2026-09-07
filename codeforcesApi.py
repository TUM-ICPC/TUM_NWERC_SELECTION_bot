import hashlib
import os
import secrets
import time

import requests

codeforcesUrl = 'https://codeforces.com/api/'
API_CONFIG_FILE = '.codeforces_api_config.txt'
_last_request_at = 0.0
_minimum_interval = 2.05

def _read_api_credentials():
  if not os.path.exists(API_CONFIG_FILE):
    return None
  try:
    with open(API_CONFIG_FILE, encoding="utf-8") as config_file:
      lines = [line.strip() for line in config_file if line.strip()]
    if len(lines) >= 2:
      return lines[0], lines[1]
  except OSError as error:
    print(f"[ERROR] Cannot read {API_CONFIG_FILE}: {error}")
  return None

def _authenticated_params(method, params):
  credentials = _read_api_credentials()
  if credentials is None:
    print(f"[ERROR] Missing {API_CONFIG_FILE}; private Gym API access is unavailable.")
    return None

  api_key, secret = credentials
  signed = {**params, "apiKey": api_key, "time": int(time.time())}
  ordered = sorted((str(key), str(value)) for key, value in signed.items())
  query = "&".join(f"{key}={value}" for key, value in ordered)
  random_prefix = secrets.token_hex(3)
  signature_text = f"{random_prefix}/{method}?{query}#{secret}"
  digest = hashlib.sha512(signature_text.encode("utf-8")).hexdigest()
  signed["apiSig"] = random_prefix + digest
  return signed

def request(method, params, authenticated=False):
  global _last_request_at

  max_attempts = 3
  for attempt in range(1, max_attempts + 1):
    # Codeforces permits at most one API request per two seconds.
    elapsed = time.monotonic() - _last_request_at
    if elapsed < _minimum_interval:
      time.sleep(_minimum_interval - elapsed)

    request_params = dict(params)
    if authenticated:
      request_params = _authenticated_params(method, request_params)
      if request_params is None:
        return False

    try:
      response = requests.get(codeforcesUrl + method, params=request_params, timeout=20)
      _last_request_at = time.monotonic()
    except requests.exceptions.Timeout:
      print(f"[WARN] Codeforces API timeout: {method} (attempt {attempt}/{max_attempts})")
      if attempt < max_attempts:
        continue
      return False
    except requests.RequestException as error:
      print(f"[WARN] Codeforces API request failed ({method}): {error} (attempt {attempt}/{max_attempts})")
      if attempt < max_attempts:
        continue
      return False

    try:
      payload = response.json()
    except ValueError:
      retryable = response.status_code in (502, 503, 504)
      level = "WARN" if retryable and attempt < max_attempts else "ERROR"
      print(f"[{level}] Codeforces API returned non-JSON for {method} (HTTP {response.status_code}, attempt {attempt}/{max_attempts}).")
      if retryable and attempt < max_attempts:
        continue
      return False

    if payload.get("status") == "OK":
      return payload.get("result")

    comment = payload.get("comment", "unknown API error")
    print(f"[ERROR] Codeforces API {method} failed (HTTP {response.status_code}): {comment}")
    return False

  return False
