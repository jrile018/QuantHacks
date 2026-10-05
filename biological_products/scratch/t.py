import requests
qs = ['sponsor_name:GILEAD', 'sponsor_name:"GILEAD SCIENCES, INC."', 'openfda.manufacturer_name:gilead', 'products.brand_name:harvoni', 'sponsor_name.exact:"GILEAD SCIENCES, INC."']
for q in qs:
    print(q, requests.get('https://api.fda.gov/drug/drugsfda.json', params={'search': q, 'limit': 1}).status_code)
