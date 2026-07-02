import requests
import json

url = "https://api.openalex.org/works"
q = 'astrocyte AND ("calcium wave" OR "calcium signaling") AND "ATP" AND (model OR computational OR simulation)'
params = {
    "filter": "publication_year:>2022",
    "search": q,
    "mailto": "test@example.com"
}
r = requests.get(url, params=params)
print(r.status_code)
if r.status_code == 200:
    res = r.json()
    print("Hits:", res["meta"]["count"])
else:
    print(r.text)
