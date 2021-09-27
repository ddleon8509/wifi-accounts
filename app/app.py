#!/usr/bin/env python3
from json.decoder import JSONDecodeError
import os
from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import re
import requests
import json
from pathlib import Path
import shutil

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
app.config['UPLOAD_EXTENSIONS'] = ['.csv']
app.config['UPLOAD_PATH'] = 'upload'

headers = {
  'X-AH-API-CLIENT-SECRET': os.environ.get('X-AH-API-CLIENT-SECRET'),
  'X-AH-API-CLIENT-ID': os.environ.get('X-AH-API-CLIENT-ID'),
  'X-AH-API-CLIENT-REDIRECT-URI': os.environ.get('X-AH-API-CLIENT-REDIRECT-URI'),
  'Authorization': os.environ.get('Authorization')
}
ownerId = os.environ.get('ownerId')
groupUserId = os.environ.get('groupUserId')

def logging(entry, **kwargs):
	entry['dt'] = datetime.now().strftime('%d/%m/%Y-%H:%M:%S')
	id = kwargs.get('id', None)
	try:
		with open('data/log/log.json', 'r') as f:
			try:
				entries = json.load(f)
			except JSONDecodeError:
				{"data": [],"total": 0,"id":id}
	except IOError:
		entries = {"data": [],"total": 0,"id":id}	
	entries["data"].append(entry)
	entries["total"] = entries['total'] + 1
	if id is not None:
		entries["id"] = id
	with open('data/log/log.json', 'w') as f:
		json.dump(entries, f, indent = 4)

def CSVProcessor(filename):
	new = {"data": [],"total": 0, "id":filename}
	notify = {"data": [],"total": 0, "id":filename}
	prev = {"data": [],"total": 0, "id":filename}
	notifyList = []
	newList = []
	with open('data/log/backup.json', 'r+') as f:
		try:
			entries = json.load(f)
		except JSONDecodeError:
			logging({'t': 'ERROR', 'd': f'Backup json file is not present or it is empty'}, id = filename)
			return
	with open('upload/'+ filename + '.csv', 'r') as f:
		data = f.readlines()
	if data is None:
		logging({'t': 'ERROR', 'd': f'File uploaded is empty'}, id = filename)
		return
	if re.search(r'^Email,Room,First Name,Last Name,Banner$', data[0]) is None:
		logging({'t': 'ERROR', 'd': f'File Headers have a wrong format'}, id = filename)
		return
	for line in data[1:]:
		notifyMarker = False
		index = 2
		pattern = re.search(r'^([\w-]+(?:\.[\w-]+)*)@(bucs\.fsw\.edu|fsw\.edu),(\d{3}\w?),([a-zA-z-]+),([a-zA-z-]+),(@\d{8})$', line)
		if pattern is None:
			logging({'t': 'ERROR', 'd': f'File line {index} has errors ({line})'}, id = filename)
		else:
			for i in entries["data"]:
				if i['userName'] == pattern.group(1):
					notify['data'].append({"credentialId": i['id'],"deliverMethod": "EMAIL","email": i['email'],"phone": ""})
					notify['total'] = notify['total'] + 1
					notifyList.append(i['userName'])
					notifyMarker = True
					break
			if not notifyMarker:
				new["data"].append({"deliverMethod": "EMAIL", "email": f'{pattern.group(1)}@{pattern.group(2)}', "firstName": pattern.group(4), \
  									"groupId": groupUserId, "lastName": pattern.group(5), "macBindingList": [], "organization": f"LHC-RESIDENT ({pattern.group(3)})", \
  									"phone": "","policy": "GUEST","purpose": pattern.group(6),"userName": pattern.group(1)})
				new['total'] = new['total'] + 1					  
				newList.append(pattern.group(1))
				notifyMarker = False
		index = index + 1
	#------------------
	# Logic to delete the old accounts.
	#------------------
	if new['total'] > 0:
		logging({'t': 'INFO', 'd': f'CSV File processed. New accounts pending under the Results session'}, id = filename)
		with open('data/log/new.json', 'w') as f:
			json.dump(new, f, indent = 4)
	if notify['total'] > 0:
		logging({'t': 'INFO', 'd': f'CSV File processed. Notify existing users pending under the Results session'}, id = filename)
		with open('data/log/notify.json', 'w') as f:
			json.dump(notify, f, indent = 4)
	return

@app.route('/')
def index():
	counters = {}
	try:
		with open('data/log/log.json', 'r') as f:
			try:
				entries = json.load(f)
			except JSONDecodeError:
				entries = {"data": [],"total": 0,"id":""}
	except IOError:
		entries = {"data": [],"total": 0,"id":""}
		
	for i in ['notify','new','prev']:
		try:
			with open(f'data/log/{i}.json', 'r') as f:
				counters[i] = json.load(f)['total']
		except:
			counters[i] = 0
	return render_template('index.html', counters = counters, logs = entries)

@app.route('/<param>/discard')
def discard(param):
	with open(f'data/log/{param}.json', 'r') as f:
		data = json.load(f)	
	Path(f'data/log/rotate/{data["id"]}').mkdir(parents=True, exist_ok=True)
	logging({'t': 'INFO', 'd': f'File {param}.json was deleted'})
	shutil.move(f'data/log/{param}.json', f'data/log/rotate/{data["id"]}/{param}.json')
	if param == 'log':
		shutil.move(f'data/log/backup.json', f'data/log/rotate/{data["id"]}/backup.json')
		shutil.move(f'upload/{data["id"]}.csv', f'data/log/rotate/{data["id"]}/{data["id"]}.csv')
	return redirect(url_for('index'))

@app.route('/notify')
def notify():
	headers['Content-Type'] = 'application/json'
	with open('data/log/notify.json', 'r') as f:
		try:
			payload = json.load(f)["data"]
		except:
			logging({'t': 'ERROR', 'd': f'Error opening the notify.json file'})
			return redirect(url_for('index'))
	for i in payload:
		response = requests.request("POST", f'https://va.extremecloudiq.com/xapi/v2/identity/credentials/deliver?ownerId={ownerId}', headers = headers, data = json.dumps(i, indent = 4))
		if response.status_code != 200:
			logging({'t': 'ERROR', 'd': f'Error sending credential ({i})'})
	logging({'t': 'INFO', 'd': f'File notify.json was processed'})
	discard('notify')	
	return redirect(url_for('index'))

@app.route('/new')
def new():
	headers['Content-Type'] = 'application/json'
	with open('data/log/new.json', 'r') as f:
		try:
			payload = json.load(f)["data"]
		except:
			logging({'t': 'ERROR', 'd': f'Error opening the new.json file'})
			return redirect(url_for('index'))
	for i in payload:
		response = requests.request("POST", f'https://va.extremecloudiq.com/xapi/v2/identity/credentials?ownerId={ownerId}', headers = headers, data = json.dumps(i, indent = 4))
		if response.status_code != 200:
			logging({'t': 'ERROR', 'd': f'Error creating a new user ({i})'})
	logging({'t': 'INFO', 'd': f'File new.json was processed'})
	discard('new')			
	return redirect(url_for('index'))

@app.route('/download')
def download():
	data = requests.request("GET", f'https://va.extremecloudiq.com/xapi/v2/identity/credentials?ownerId={ownerId}&userGroup={groupUserId}', headers=headers, data='').json()
	with open('data/log/backup.json', 'w') as f:
		json.dump(data, f)
	logging({'t': 'INFO', 'd': f'Backup Processed. Total accounts: {data["pagination"]["totalCount"]}'})
	return redirect(url_for('index'))

@app.route('/', methods=['POST'])
def upload_files():
	uploaded_file = request.files['file']
	file_ext = os.path.splitext(uploaded_file.filename)[1]
	name = f"{datetime.now().strftime('%d%m%Y%H%M%S')}"
	if file_ext not in app.config['UPLOAD_EXTENSIONS']:
		logging({'t': 'ERROR', 'd': f'File uploaded is not on the list of permitted files'}, id = name)
		return redirect(url_for('index'))
	uploaded_file.save(os.path.join(app.config['UPLOAD_PATH'], name + file_ext))
	CSVProcessor(name)
	return redirect(url_for('index'))

if __name__ == "__main__":
	app.run(host='0.0.0.0', port = os.environ.get('PORT'))