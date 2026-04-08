import os
import json
import urllib.request

plan_content = open('C:/Users/David Lochmann/Documents/PB_studio_Rebuild/team_structure_plan.md', 'r', encoding='utf-8').read()

api_url = os.environ['PAPERCLIP_API_URL']
api_key = os.environ['PAPERCLIP_API_KEY']
run_id = os.environ['PAPERCLIP_RUN_ID']
issue_id = "1eb49027-c316-4851-b712-83a5960b50c8"

url = f"{api_url}/api/issues/{issue_id}/documents/plan"
payload = {
    "title": "PB Studio Team Structure",
    "format": "markdown",
    "body": plan_content,
    "baseRevisionId": None
}

data = json.dumps(payload).encode('utf-8')
req = urllib.request.Request(url, data=data, method='PUT')
req.add_header('Authorization', f'Bearer {api_key}')
req.add_header('Content-Type', 'application/json')
req.add_header('X-Paperclip-Run-Id', run_id)

try:
    with urllib.request.urlopen(req) as response:
        print(f"Status: {response.status}")
        print(response.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print(f"Error Status: {e.code}")
    print(e.read().decode('utf-8'))
