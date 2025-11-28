import requests

url = "http://121.40.127.17:8090/api/v1/auth/login"
data = {"username": "admin", "password": "!Dsq20020926"}

resp = requests.post(url, json=data)
print(resp.status_code, resp.text)