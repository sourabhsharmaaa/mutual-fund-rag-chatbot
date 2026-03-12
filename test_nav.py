import requests # type: ignore

url = "https://www.amfiindia.com/spages/NAVAll.txt"
resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
lines = resp.text.split('\n')

for line in lines:
    if "122639" in line or "147481" in line:
        print(line)
