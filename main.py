import json
import time
import base64
import os
import secrets
import random
import threading
import websocket
import ssl
import sys
import concurrent.futures
from urllib.parse import quote, unquote
import requests
from flask import Flask, request

try:
    from Crypto.Cipher import DES3
    from Crypto.Util.Padding import pad, unpad
except ImportError:
    print("❌ Error: 'pycryptodome' library install nahi hai. Terminal me type karein: pip install pycryptodome")
    sys.exit()

# ==========================================
# 🌐 1. FLASK SERVER & DYNAMIC ROOM API
# ==========================================
app = Flask(__name__)

# 🔥 Naya Global Variable Temporary Room ke liye (Memory me save hoga, GitHub me nahi)
GLOBAL_DYNAMIC_ROOM = None 

@app.route('/')
def home():
    current = GLOBAL_DYNAMIC_ROOM if GLOBAL_DYNAMIC_ROOM else "Default rooms.txt"
    return f"🚀 Mega Bot is Live! <br>Current Target Room: {current} <br>(Online Viewer + Dynamic Shift + 12H Auto-Restart Sync)"

@app.route('/change_room')
def change_room_api():
    global GLOBAL_DYNAMIC_ROOM
    new_room = request.args.get('cid')
    action = request.args.get('action')
    
    if new_room and new_room.startswith("C_"):
        GLOBAL_DYNAMIC_ROOM = new_room
        action_msg = " + AUTO TAKE SEAT" if action == "take_seat" else ""
        return f"✅ SUCCESS: Server memory update ho gayi! Sabhi bots ab bina restart hue {new_room} me shift ho jayenge{action_msg}."
    return "❌ ERROR: Ghalat Room ID."

def keep_alive():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, use_reloader=False)

# ==========================================
# 🔐 2. TOKEN REFRESHER & GITHUB SYNC LOGIC (Sirf accounts.json ke liye)
# ==========================================
IV = b'01234567'
GLOBAL_ACCOUNTS_DB = {} 

def generate_random_hdid():
    return secrets.token_hex(8)

def decrypt_des_ede(ciphertext_b64, key):
    try:
        key_bytes = key.encode('utf-8').ljust(24, b'\0')[:24]
        cipher = DES3.new(key_bytes, DES3.MODE_CBC, IV)
        ciphertext_bytes = base64.b64decode(ciphertext_b64)
        decrypted_bytes = cipher.decrypt(ciphertext_bytes)
        return unpad(decrypted_bytes, DES3.block_size).decode('utf-8')
    except Exception: return None

def encrypt_des_ede(plaintext, key):
    try:
        key_bytes = key.encode('utf-8').ljust(24, b'\0')[:24]
        cipher = DES3.new(key_bytes, DES3.MODE_CBC, IV)
        padded_bytes = pad(plaintext.encode('utf-8'), DES3.block_size)
        encrypted_bytes = cipher.encrypt(padded_bytes)
        return base64.b64encode(encrypted_bytes).decode('utf-8')
    except Exception: return None

def refresh_single_token(current_token, decryption_key):
    device_id = generate_random_hdid()
    decoded_token = unquote(current_token)
    parts = decoded_token.split(',')
    
    if len(parts) < 2: return None
    c_auth, s_t_old = parts[0], parts[1]

    decrypted_payload = decrypt_des_ede(c_auth, decryption_key)
    if not decrypted_payload: return None
    
    try:
        uid = json.loads(decrypted_payload).get("uuid")
    except: return None

    url = "https://i.olaparty.com/uaas/login/refreshAuth"
    headers = {
        'User-Agent': 'okhttp/3.12.1', 'Accept-Encoding': 'gzip',
        'Content-Type': 'application/x-www-form-urlencoded',
        'x-cpuarch': 'aarch64', 'x-devicetype': 'google Pixel 4',
        'x-sdk-ver': '28', 'x-app-name': 'olaparty',
        'x-simciso': 'in', 'x-client-net': '1',
        'x-app-lastver': '11501', 'x-lang': 'en_in',
        'x-app-ver': '41100', 'x-app-real-ver': '11800',
        'x-os-ver': '9', 'x-ostype': 'android',
        'x-auth-token': current_token, 'x-deviceid': device_id,
        'x-olaparty-ver': '11800'
    }
    data = {'app': 'olaparty', 's_t': s_t_old, 'uid': uid, 'c_auth': c_auth, 'appId': 'ikxd'}
    
    try:
        response = requests.post(url, data=data, headers=headers, timeout=10)
        res_json = response.json()
        data_node = res_json.get("data", {})
        s_session = res_json.get("s_session") or data_node.get("s_session")
        s_t_new = res_json.get("s_t") or data_node.get("s_t")
        if not s_session or not s_t_new: return None
    except: return None

    decrypted_session_json = decrypt_des_ede(s_session, decryption_key)
    if not decrypted_session_json: return None
    
    try:
        session_data = json.loads(decrypted_session_json)
        new_uuid = session_data.get("uuid")
        new_session_key = session_data.get("sSessionKey")
    except: return None

    timestamp = int(time.time() * 1000)
    new_payload_json = json.dumps({"uuid": new_uuid, "timestamp": timestamp}, separators=(',', ':'))
    encrypted_part1 = encrypt_des_ede(new_payload_json, new_session_key)
    
    return {
        "new_token": quote(f"{encrypted_part1},{s_t_new}", safe=''),
        "new_session_key": new_session_key
    }

def update_github_json(updated_db_content):
    gh_token = "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"
    url = "https://api.github.com/repos/ganstarlucky71-ui/online/contents/accounts.json"

    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        print("❌ GitHub se accounts.json nahi mil rhi!")
        return
    sha = res.json().get("sha")

    content_encoded = base64.b64encode(json.dumps(updated_db_content, separators=(',', ':')).encode()).decode()

    payload = {
        "message": "Auto-update refreshed accounts [skip ci]",
        "content": content_encoded,
        "sha": sha
    }

    upload_res = requests.put(url, headers=headers, json=payload)
    if upload_res.status_code == 200 or upload_res.status_code == 201:
        print("☁️ ✅ GitHub par accounts.json successfully update ho gayi! Render will restart now.")
    else:
        print(f"☁️ ❌ GitHub upload failed: {upload_res.text}")

def background_token_refresher():
    while True:
        print("\n⏳ [AUTO-REFRESH] Timer Started. Agla refresh theek 12 ghante baad hoga...")
        # Smart timer for logging to avoid render restart silences
        for hour in range(1, 13):
            time.sleep(3600)  # 1 Ghanta wait
            print(f"⏳ [AUTO-REFRESH] {hour} Ghante (Hours) guzar gaye...")

        print("\n🔄 [AUTO-REFRESH] 12 Hours Completed! Token Refresh Cycle Started...")
        accounts = GLOBAL_ACCOUNTS_DB.get("accountInfos", [])

        def worker(acc):
            old_token = acc.get("token")
            old_session = acc.get("sessionKey")
            result = refresh_single_token(old_token, old_session)
            if result:
                acc["token"] = result["new_token"]
                acc["sessionKey"] = result["new_session_key"]
                acc["localTimestamp"] = int(time.time() * 1000)
                print(f"✅ Auto-Refreshed: {acc.get('userName')}")
            else:
                print(f"❌ Auto-Refresh Failed: {acc.get('userName')}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            executor.map(worker, accounts)

        try:
            with open("accounts.json", "w", encoding="utf-8") as f:
                json.dump(GLOBAL_ACCOUNTS_DB, f, separators=(',', ':'))
            print("📁 [AUTO-REFRESH] Local 'accounts.json' updated!")

            update_github_json(GLOBAL_ACCOUNTS_DB)

        except Exception as e:
            print(f"❌ File Save Error: {e}")

# ==========================================
# 📡 3. HEX PACKETS GENERATOR (Bots ke liye)
# ==========================================
def encode_varint(value):
    out = []
    while value > 127:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)

def string_to_hex_spaced(text_str):
    raw_hex = str(text_str).encode('utf-8').hex().upper()
    return " ".join([raw_hex[i:i+2] for i in range(0, len(raw_hex), 2)])

def cid_to_varint_hex(cid_str, target_length=5):
    try:
        number = int(cid_str)
        encoded_bytes = []
        while True:
            byte = number & 0x7F
            number >>= 7
            if number > 0: byte |= 0x80; encoded_bytes.append(byte)
            else: encoded_bytes.append(byte); break
        while len(encoded_bytes) < target_length:
            last = encoded_bytes.pop()
            encoded_bytes.append(last | 0x80)
            encoded_bytes.append(0x00)
        return ' '.join([f'{b:02X}' for b in encoded_bytes]).upper()
    except: return None

def determine_version(room_id):
    return "V1" if "_V1_" in room_id else "V2"

# 🟢 V1 Packets (Entry & Seat)
def get_v1_enter_packet(room_id):
    id_bytes = room_id.encode('utf-8')
    id_len = encode_varint(len(id_bytes))
    p1 = bytes.fromhex("0A880150001800621D0A06582D506369641213313135323932313530343631323830323734392205656E5F696E3A0D4368616E6E656C2E456E746572480132")
    p2 = bytes.fromhex("10B0F3C798C6330A196E65742E696861676F2E6368616E6E656C2E7372762E6D67724205302E302E301A")
    inner_prefix = bytes.fromhex("9802000A")
    inner_suffix = bytes.fromhex("721C120231351A07616172636836340A0A3233313144524B34384928CD585A00AA02360A1D1A0761617263683634100828F0BBCC0120C0A386010A064D543638393722065869616F6D691A0A3233313144524B34384910CD58FA01280A002200520231315A01326201311216313737313138383634383336343432393038323532311A008A0206080018001000A002005200F001001A8602DA0201319A070131320131E807005A030A0131B8060160009002010A0131FA030131900500F2030131C00700C80700D0070050011801C80200900301F80101C00601980281A004F00601A80600EA0601318A05061201310A0131AA080131E00301A00101B80801A80501C80800C00801800201A0050182040131EA030131B004019805012A0131A80700980300D80801A801012001B80401980800B2010131900800120131A00401900400880401B00601DA060131D00601B00800C80601F8060082050131F00101D20233980200900300A80100800200800500A80500900200D80300980300F80100B00100E80100A001000A0131880200E00100D801006800E00201880201102D82019A01180040001235F09D9983F09D998AF09D9989F09D9980F09D9994C2B0F09F87B2E2808CF09D998AF09D998AF09D9989F09FA9B553544152F09F97BD3000200128000A5768747470733A2F2F6F2D696E2E6F6C6170617274792E636F6D2F626C6F622F76322F616C692F696E2F302F312F6E732F323176353870792F7575726C2F343436363334333532365F313736353232343230362E6A706567900200")
    inner_payload = inner_prefix + id_len + id_bytes + inner_suffix
    return p1 + id_len + id_bytes + p2 + encode_varint(len(inner_payload)) + inner_payload + bytes.fromhex("1000")

def get_v1_sit_packet(room_id, seat_number):
    room_bytes = room_id.encode('utf-8')
    room_len_varint = encode_varint(len(room_bytes))
    time_ms = int(time.time() * 1000)
    time_bytes_raw = encode_varint(time_ms)
    
    prefix = bytes.fromhex("50001800621D0A06582D506369641213313135323932313530343631323830323734392205656E5F6E703A0F4368616E6E656C2E536974646F776E4801")
    route_suffix = bytes.fromhex("0A196E65742E696861676F2E6368616E6E656C2E7372762E6D67724205302E302E30")
    routing_inner = prefix + bytes.fromhex("32") + room_len_varint + room_bytes + bytes.fromhex("10") + time_bytes_raw + route_suffix
    chunk_routing = bytes.fromhex("0A") + encode_varint(len(routing_inner)) + routing_inner
    
    seat_varint = encode_varint(seat_number)
    payload_inner = bytes.fromhex("0A") + room_len_varint + room_bytes + bytes.fromhex("10") + seat_varint
    chunk_payload = bytes.fromhex("1A") + encode_varint(len(payload_inner)) + payload_inner
    
    return chunk_routing + chunk_payload + bytes.fromhex("1000")

# 🟢 V2 Packets (Entry & Seat)
def get_v2_enter_packet(room_id):
    new_id_hex = room_id.encode('utf-8').hex()
    new_len_hex = format(len(room_id), '02x')
    prefix = "0A860150001800621D0A06582D506369641213313135323932313530343631343034313330332205656E5F696E3A0D4368616E6E656C2E456E746572480132"
    middle = "1087F0A7DDBC330A196E65742E696861676F2E6368616E6E656C2E7372762E6D67724205302E302E301AC0049802000A"
    suffix = "721C120231351A07616172636836340A0A3233313144524B34384928CD585A00AA02360A1D1A0761617263683634100828F0BBCC0120C0A386010A064D543638393722065869616F6D691A0A3233313144524B34384910CD58FA012D0A002200520231335A022D3162022D311219313736383634383437323536343138373932393039373133331A008A0206080018001000A002005200F001001A8302DA0201319A070131320131E807005A030A0131B8060160009002010A0131FA030131900500F2030131C00700C80700D0070050011801C80200900301F80101C00601980281A004F00601A80600EA0601318A05061201310A0131AA080131E00301A00101B80801A80501C80800C00801800201A0050182040131EA030131B004019805012A0131A80700980300A801012001B80401980800B2010131900800120131A00401900400880401B00601DA060131D00601B00800C80601F8060082050131F00101D20233980200900300A80100800200800500A80500900200D80300980300F80100B00100E80100A001000A0131880200E00100D801006800E00201880201100B82017318004000120E4D6163204F53202841646D696E293000200128000A5768747470733A2F2F6F2D696E2E6F6C6170617274792E636F6D2F626C6F622F76322F616C692F696E2F302F312F6E732F323176353870792F7575726C2F343436363334333532365F313736353232343230362E6A7065679002001000"
    return bytes.fromhex(f"{prefix}{new_len_hex}{new_id_hex}{middle}{new_len_hex}{new_id_hex}{suffix}")

def get_v2_sit_packet(room_id):
    id_hex = room_id.encode('utf-8').hex()
    len_hex = format(len(room_id), '02x')
    prefix = "0A880150001800621D0A06582D506369641213313135323932313530343631323830323734392205656E5F696E3A0F4368616E6E656C2E536974646F776E480132"
    middle = "109DCBFD96C3330A196E65742E696861676F2E6368616E6E656C2E7372762E6D67724205302E302E301A2D0A"
    suffix = "10FFFFFFFFFFFFFFFFFF011000"
    return bytes.fromhex(f"{prefix}{len_hex}{id_hex}{middle}{len_hex}{id_hex}{suffix}")

def generate_heartbeat_packet(target_cid):
    target_cid_clean = target_cid.strip()
    new_cid_hex = string_to_hex_spaced(target_cid_clean)
    new_time_varint = cid_to_varint_hex(str(int(time.time() * 1000)), 6)

    if "_V1_" in target_cid_clean:
        base_hex = "0A 50 50 00 18 00 22 05 65 6E 5F 69 6E 3A 14 42 61 73 65 4F 6E 6C 69 6E 65 2E 48 65 61 72 74 42 65 61 74 48 01 32 00 10 BC 8A 8A E7 FE 33 0A 1B 6E 65 74 2E 69 68 61 67 6F 2E 6F 6E 6C 69 6E 65 2E 73 72 76 2E 6F 6E 6C 69 6E 65 42 05 30 2E 30 2E 30 1A 80 01 18 00 22 7A 0A 06 72 6F 6F 6D 69 64 12 70 43 5F 31 36 32 35 38 39 38 35 36 31 34 39 39 36 30 39 35 38 38 5F 56 31 5F 49 4E 5F 38 38 31 5F 49 4E 7C 63 68 61 74 7C 31 37 38 36 33 38 35 36 35 30 34 39 34 34 39 32 30 30 31 36 39 32 7C 30 7C 34 7C 7C 32 7C 7C 7C 7C 30 7C 30 7C 30 7C 30 7C 31 7C 2D 31 7C 30 7C 30 7C 30 7C 30 7C 7C 7C 30 7C 7C 7C 30 7C 30 7C 7C 31 7C 7C 7C 7C 7C 7C 10 00 10 00"
        old_cid_v1 = "C_1625898561499609588_V1_IN_881_IN"
        old_cid_v1_hex = string_to_hex_spaced(old_cid_v1)
        base_hex = base_hex.replace(old_cid_v1_hex, new_cid_hex)
        if new_time_varint:
            base_hex = base_hex.replace("BC 8A 8A E7 FE 33", new_time_varint)
    else:
        base_hex = "0A 50 50 00 18 00 22 05 65 6E 5F 69 6E 3A 14 42 61 73 65 4F 6E 6C 69 6E 65 2E 48 65 61 72 74 42 65 61 74 48 01 32 00 10 B7 9B 95 E7 FE 33 0A 1B 6E 65 74 2E 69 68 61 67 6F 2E 6F 6E 6C 69 6E 65 2E 73 72 76 2E 6F 6E 6C 69 6E 65 42 05 30 2E 30 2E 30 1A 7E 18 00 22 78 0A 06 72 6F 6F 6D 69 64 12 6E 43 5F 31 39 39 36 33 31 34 34 33 33 32 34 34 32 36 33 39 33 38 5F 56 32 5F 49 4E 5F 30 5F 49 4E 7C 63 68 61 74 7C 31 37 38 36 33 38 35 38 31 37 30 38 32 34 39 33 36 36 37 35 37 35 7C 30 7C 34 7C 7C 32 7C 7C 7C 7C 30 7C 30 7C 30 7C 30 7C 31 7C 2D 31 7C 30 7C 30 7C 30 7C 30 7C 7C 7C 30 7C 7C 7C 30 7C 30 7C 7C 31 7C 7C 7C 7C 7C 7C 10 00 10 00"
        old_cid_v2 = "C_1996314433244263938_V2_IN_0_IN"
        old_cid_v2_hex = string_to_hex_spaced(old_cid_v2)
        base_hex = base_hex.replace(old_cid_v2_hex, new_cid_hex)
        if new_time_varint:
            base_hex = base_hex.replace("B7 9B 95 E7 FE 33", new_time_varint)

    return bytes.fromhex(base_hex.replace(" ", ""))

# ==========================================
# 🤖 4. BOT WORKER (Dynamic Room Shift + Take Seat System)
# ==========================================
def run_single_bot(bot_num, account_ref, original_room_cid):
    def on_open(ws):
        def run():
            current_room = original_room_cid
            r_version = determine_version(current_room)
            
            try:
                # 1. PEHLI BAAR ENTER ROOM (Jo rooms.txt me hai)
                ws.send(get_v1_enter_packet(current_room) if r_version == "V1" else get_v2_enter_packet(current_room), opcode=websocket.ABNF.OPCODE_BINARY)
                time.sleep(1)
                
                print(f"✅ [Bot {bot_num}] Assigned to Room: {current_room}")

                # 2. HEARTBEAT LOOP & DYNAMIC ROOM CHECK (Har 40 seconds)
                while True:
                    time.sleep(40)
                    
                    # 🔥 Check if Room was dynamically changed via Termux
                    target_room = GLOBAL_DYNAMIC_ROOM if GLOBAL_DYNAMIC_ROOM else original_room_cid
                    
                    # Agar naya room mila, toh shift ho jao aur seat lo!
                    if current_room != target_room:
                        print(f"🚀 [Bot {bot_num}] Shifting to NEW Room: {target_room}")
                        current_room = target_room
                        r_version = determine_version(current_room)
                        
                        # Step A: Naye room me enter packet bhejo
                        ws.send(get_v1_enter_packet(current_room) if r_version == "V1" else get_v2_enter_packet(current_room), opcode=websocket.ABNF.OPCODE_BINARY)
                        time.sleep(1) # Entry ke baad 1 sec ruko
                        
                        # Step B: Naye room me aate hi TAKE SEAT (Baith jao)
                        if r_version == "V1":
                            for seat in range(2, 13):
                                ws.send(get_v1_sit_packet(current_room, seat), opcode=websocket.ABNF.OPCODE_BINARY)
                                time.sleep(0.05) # V1 me sab seat par apply karo
                        else:
                            ws.send(get_v2_sit_packet(current_room), opcode=websocket.ABNF.OPCODE_BINARY)
                            
                        print(f"🪑 [Bot {bot_num}] Ne naye room me Seat le li hai!")
                    
                    # Heartbeat hamesha usi room me bhejega jisme abhi khada hai
                    ws.send(generate_heartbeat_packet(current_room), opcode=websocket.ABNF.OPCODE_BINARY)

            except Exception: pass
            finally: ws.close()

        threading.Thread(target=run, daemon=True).start()

    def connect_ws():
        while True:
            current_token = account_ref.get("token", "").strip()
            headers = {
                "User-Agent": "com.live.party/2952 (Linux; U; Android 15)",
                "Origin": "https://i-875.olaparty.com",
                "X-App-Name": "olaparty",
                "X-App-Ver": "50800",
                "X-Auth-Token": current_token
            }
            ws = websocket.WebSocketApp("wss://i-875.olaparty.com/ikxd_cproxy", header=headers, on_open=on_open, on_message=lambda w,m:None, on_error=lambda w,e:None, on_close=lambda w,c,m:None)
            ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
            time.sleep(4) 

    threading.Thread(target=connect_ws, daemon=True).start()

# ==========================================
# 🚀 5. MAIN LAUNCHER
# ==========================================
def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("==================================================")
    print("🔥 MEGA BOT: VIEWER + TERMUX SHIFT + AUTO SEAT 🔥")
    print("==================================================")

    # 1. Start Web Server
    threading.Thread(target=keep_alive, daemon=True).start()

    # 2. Load Global Data
    if not os.path.exists("accounts.json") or not os.path.exists("rooms.txt"):
        print("❌ Error: 'accounts.json' ya 'rooms.txt' file nahi mili!")
        return

    try:
        with open("accounts.json", "r", encoding="utf-8") as f:
            global GLOBAL_ACCOUNTS_DB
            GLOBAL_ACCOUNTS_DB = json.load(f)
            accounts_list = GLOBAL_ACCOUNTS_DB.get("accountInfos", [])
    except Exception as e:
        print(f"❌ JSON Load Error: {e}")
        return

    with open("rooms.txt", "r", encoding="utf-8") as file:
        rooms = [line.strip() for line in file if line.strip().startswith("C_")]

    if not accounts_list:
        print("❌ accounts.json mein koi accounts nahi mile!")
        return

    if not rooms:
        print("❌ rooms.txt mein koi valid rooms (C_ se shuru hone wale) nahi mile!")
        return

    # 3. Start Background Token Refresher Thread (Har 12 Ghante)
    threading.Thread(target=background_token_refresher, daemon=True).start()

    # 4. Start Bots
    tokens_per_room = 97
    bot_counter = 1

    print(f"📂 Total Accounts: {len(accounts_list)} | Total Rooms: {len(rooms)}")

    for room_index, room_id in enumerate(rooms):
        start_index = room_index * tokens_per_room
        end_index = start_index + tokens_per_room

        if not start_index < len(accounts_list):
            print("⚠️ Saare accounts rooms mein bante ja chuke hain.")
            break

        current_room_accounts = accounts_list[start_index:end_index]
        if not current_room_accounts:
            continue

        print(f"\n🚀 Deploying {len(current_room_accounts)} bots to Room: {room_id}...")

        for acc in current_room_accounts:
            run_single_bot(bot_counter, acc, room_id)
            bot_counter += 1
            time.sleep(0.3)

    print("\n✅ All Bots deployed! Termux shift system is active.")
    print("⏳ Running continuously... Don't close this terminal.")

    while True:
        time.sleep(100)

if __name__ == "__main__":
    main()
