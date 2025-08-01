from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import binascii
import uid_generator_pb2
import requests
from flask import Flask, jsonify
import json
from zitado_pb2 import Users
import asyncio
import aiohttp

app = Flask(__name__)

def load_accounts_from_file(path="token.ind.json"):
    try:
        with open(path, "r") as f:
            data = json.load(f)  # dict: { uid: password, ... }
        return [(str(uid), str(password)) for uid, password in data.items()]
    except Exception as e:
        print(f"❌ Error loading accounts file: {e}")
        return []

async def fetch_token(session, uid, password):
    url = f"https://ffwlxd-access-jwt.vercel.app/api/get_jwt?guest_uid={uid}&guest_password={password}"
    try:
        async with session.get(url, ssl=False) as resp:
            if resp.status == 200:
                data = await resp.json()
                token = data.get("BearerAuth")
                if token:
                    return token
    except Exception as e:
        print(f"❌ Error fetching token for UID {uid}: {e}")
    return None

async def load_tokens_from_accounts(accounts):
    connector = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_token(session, uid, password) for uid, password in accounts]
        results = await asyncio.gather(*tasks)
    return [token for token in results if token]

def create_protobuf(saturn_, garena):
    message = uid_generator_pb2.uid_generator()
    message.saturn_ = saturn_
    message.garena = garena
    return message.SerializeToString()

def protobuf_to_hex(protobuf_data):
    return binascii.hexlify(protobuf_data).decode()

def encrypt_aes(hex_data, key, iv):
    key = key.encode()[:16]
    iv = iv.encode()[:16]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_data = pad(bytes.fromhex(hex_data), AES.block_size)
    encrypted_data = cipher.encrypt(padded_data)
    return binascii.hexlify(encrypted_data).decode()

def decode_hex(hex_string):
    byte_data = binascii.unhexlify(hex_string.replace(' ', ''))
    users = Users()
    users.ParseFromString(byte_data)
    return users

async def apis(session, idd, token):
    headers = {
        'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)',
        'Connection': 'Keep-Alive',
        'Expect': '100-continue',
        'Authorization': f'Bearer {token}',
        'X-Unity-Version': '2018.4.11f1',
        'X-GA': 'v1 1',
        'ReleaseVersion': 'OB50',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    data = bytes.fromhex(idd)
    try:
        async with session.post('https://clientbp.ggblueshark.com/GetPlayerPersonalShow', headers=headers, data=data) as response:
            content = await response.read()
            return content.hex()
    except Exception as e:
        print(f"❌ API request error: {e}")
        return None

@app.route('/favicon.ico')
def favicon():
    return '', 204  # No Content

@app.route('/<int:uid>', methods=['GET'])
def main(uid):
    accounts = load_accounts_from_file("token.ind.json")
    if not accounts:
        return jsonify({"error": "No accounts found"}), 500

    saturn_ = uid
    garena = 1

    protobuf_data = create_protobuf(saturn_, garena)
    hex_data = protobuf_to_hex(protobuf_data)

    from secret import key, iv
    encrypted_hex = encrypt_aes(hex_data, key, iv)

    tokens = asyncio.run(load_tokens_from_accounts(accounts))
    if not tokens:
        return jsonify({"error": "Failed to get any valid token"}), 500

    tokenn = tokens[0]

    async def fetch_info():
        connector = aiohttp.TCPConnector(limit=10)
        async with aiohttp.ClientSession(connector=connector) as session:
            return await apis(session, encrypted_hex, tokenn)

    hex_response = asyncio.run(fetch_info())

    if not hex_response:
        return jsonify({"error": "No response data from API"}), 500

    try:
        users = decode_hex(hex_response)
    except Exception as e:
        return jsonify({"error": f"Invalid protobuf data: {e}"}), 500

    result = {}

    if users.basicinfo:
        result['basicinfo'] = []
        for user_info in users.basicinfo:
            result['basicinfo'].append({
                'username': user_info.username,
                'region': user_info.region,
                'level': user_info.level,
                'Exp': user_info.Exp,
                'bio': users.bioinfo[0].bio if users.bioinfo else None,
                'banner': user_info.banner,
                'avatar': user_info.avatar,
                'brrankscore': user_info.brrankscore,
                'BadgeCount': user_info.BadgeCount,
                'likes': user_info.likes,
                'lastlogin': user_info.lastlogin,
                'csrankpoint': user_info.csrankpoint,
                'csrankscore': user_info.csrankscore,
                'brrankpoint': user_info.brrankpoint,
                'createat': user_info.createat,
                'OB': user_info.OB
            })

    if users.claninfo:
        result['claninfo'] = []
        for clan in users.claninfo:
            result['claninfo'].append({
                'clanid': clan.clanid,
                'clanname': clan.clanname,
                'guildlevel': clan.guildlevel,
                'livemember': clan.livemember
            })

    if users.clanadmin:
        result['clanadmin'] = []
        for admin in users.clanadmin:
            result['clanadmin'].append({
                'idadmin': admin.idadmin,
                'adminname': admin.adminname,
                'level': admin.level,
                'exp': admin.exp,
                'brpoint': admin.brpoint,
                'lastlogin': admin.lastlogin,
                'cspoint': admin.cspoint
            })

    result['Owners'] = ['BNGX']
    return jsonify(result)

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port)