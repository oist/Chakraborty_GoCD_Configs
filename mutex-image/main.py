from random import randint
import time
import os
from flask import Flask, request

LOCK_TIMEOUT = int(os.environ.get('LOCK_TIMEOUT', default=600))

app = Flask(__name__)

lock_time = None
keyId = None

def _lock_req():
	global lock_time
	global keyId
	now = time.time()
	if lock_time is None:
		lock_time = now
		keyId = randint(0,999999)
		return True, keyId
	elif (now - lock_time) >= LOCK_TIMEOUT:
		lock_time = now
		keyId = randint(0,999999)
		return True, keyId
	return False, 0


@app.route('/lock', methods=['PUT'])
def lock_req():
	[success, code] = _lock_req()
	if success:
		return str(code), 202
	return "unavailable", 409


def _unlock_req(keynum):
	global lock_time
	global keyId
	if(keynum == keyId):
		lock_time = None
		keyId = None
		return True
	return False


@app.route('/unlock', methods=['PUT'])
def unlock_req():
	global lock_time
	keynum = request.args.get("mutexKey", type=int, default=-1)
	unlocked = _unlock_req(keynum)
	if unlocked:
		return "unlocked", 202
	if not lock_time:
		return "no current lock", 409	
	return "wrong mutexKey parameter", 401


if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0', port=8888)