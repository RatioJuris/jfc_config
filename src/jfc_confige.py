import sys
import subprocess
import importlib.util

# ==============================================================================
# AUTO-DEPENDENCY INSTALLER
# Ensures the script can run on any fresh system (Linux, Termux, Windows)
# by automatically downloading required libraries if they are missing.
# ==============================================================================
def install_dependencies():
    required_packages = ['requests', 'urllib3', 'pyfiglet']
    missing_packages = []
    
    for pkg in required_packages:
        if importlib.util.find_spec(pkg) is None:
            missing_packages.append(pkg)
            
    if missing_packages:
        print(f"[*] Missing required libraries detected: {', '.join(missing_packages)}")
        print("[*] Downloading and installing them locally now...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing_packages])
            print("[+] Libraries installed successfully.\n")
        except subprocess.CalledProcessError:
            print("[!] Failed to install dependencies automatically.")
            print(f"Please run manually: pip install {' '.join(missing_packages)}")
            sys.exit(1)

install_dependencies()

from urllib.parse import urlparse
from ssl import CERT_NONE, create_default_context
import argparse
import configparser
import logging
import os
import json
import time
import requests
import requests.cookies
import socket
import platform
import xml.etree.ElementTree as ET
import urllib3
import pyfiglet

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BRAND_NAME = "".join(chr(i) for i in [74, 105, 111, 70, 105, 98, 101, 114])
BRAND_LOWER = "".join(chr(i) for i in [106, 105, 111, 102, 105, 98, 101, 114])
DEFAULT_IMS_DOMAIN = "".join(chr(i) for i in [120, 120, 46, 119, 108, 110, 46, 105, 109, 115, 46, 106, 105, 111, 46, 99, 111, 109])
DEFAULT_TARGET_HOSTNAME = "".join(chr(i) for i in [106, 105, 111, 102, 105, 98, 101, 114, 46, 108, 111, 99, 97, 108, 46, 104, 116, 109, 108])

HASH_MULTIPLIER = 33
FALLBACK_TARGET_IP = "192.168.31.1"
DEFAULT_HTTPS_PORT = 8443
DEFAULT_CONFIG_FLAG_FILENAME = "RATIOJURIS_CONFIG_DONE"
CACHE_FILENAME = ".ratiojuris_cache.json"

DEFAULT_MICROSIP_CONFIG_TEMPLATE = """
[Settings]
accountId=1
singleMode=1
ringingSound=ringing.wav
volumeRing=100
audioRingDevice=""
audioOutputDevice=""
audioInputDevice=""
micAmplification=0
swLevelAdjustment=0
audioCodecs=AMR-WB/16000/1 AMR/8000/1
VAD=0
EC=0
forceCodec=0
opusStereo=0
disableMessaging=0
disableVideo=0
videoCaptureDevice=""
videoCodec=
videoH264=1
videoH263=1
videoVP8=1
videoVP9=1
videoBitrate=512
rport=1
sourcePort=0
rtpPortMin=52000
rtpPortMax=52200
dnsSrvNs=
dnsSrv=0
STUN=
enableSTUN=0
recordingPath=Recordings
recordingFormat=mp3
autoRecording=1
recordingButton=1
DTMFMethod=0
autoAnswer=button
autoAnswerDelay=0
autoAnswerNumber=
forwarding=
forwardingNumber=
forwardingDelay=0
denyIncoming=button
usersDirectory=
defaultAction=
enableMediaButtons=0
headsetSupport=0
localDTMF=1
enableLog=0
bringToFrontOnIncoming=1
enableLocalAccount=0
randomAnswerBox=0
callWaiting=1
updatesInterval=never
checkUpdatesTime=1737295400
noResize=0
userAgent=
autoHangUpTime=0
maxConcurrentCalls=0
noIgnoreCall=0
cmdOutgoingCall=
cmdIncomingCall=
cmdCallRing=
cmdCallAnswer=
cmdCallAnswerVideo=
cmdCallBusy=
cmdCallStart=
cmdCallEnd=
minimized=0
silent=0
portKnockerHost=
portKnockerPorts=
mainX=194
mainY=88
mainW=748
mainH=528
messagesX=986
messagesY=288
messagesW=550
messagesH=528
ringinX=0
ringinY=0
callsWidth0=0
callsWidth1=0
callsWidth2=0
callsWidth3=0
callsWidth4=0
callsWidth5=0
contactsWidth0=0
contactsWidth1=0
contactsWidth2=0
volumeOutput=100
volumeInput=100
activeTab=0
AA=0
AC=0
DND=0
alwaysOnTop=0
multiMonitor=0
enableShortcuts=0
shortcutsBottom=0
lastCallNumber=01234567890
lastCallHasVideo=1
callsLastKey=36
[Account1]
label=+910000000000@__IMS_DOMAIN_PLACEHOLDER__
server=__IMS_DOMAIN_PLACEHOLDER__
proxy=192.168.29.1:5068
domain=192.168.29.1:5068
username=+910000000000@__IMS_DOMAIN_PLACEHOLDER__
password=xxxxxxx
authID=910000000000@__IMS_DOMAIN_PLACEHOLDER__
displayName=
dialingPrefix=
dialPlan=
hideCID=0
voicemailNumber=
transport=tls
publicAddr=
SRTP=
registerRefresh=86400
keepAlive=15
publish=0
ICE=0
allowRewrite=0
disableSessionTimer=0
[Calls]

[Dialed]

"""

DEFAULT_MICROSIP_CONFIG = DEFAULT_MICROSIP_CONFIG_TEMPLATE.replace("__IMS_DOMAIN_PLACEHOLDER__", DEFAULT_IMS_DOMAIN)

class RawResponse:
    """A response-like object to mimic `requests.Response`."""
    def __init__(self, status_code, headers, body, raw_data):
        self.status_code = status_code
        self.headers = headers
        self.text = body.decode(errors='replace')
        self.raw = raw_data

    def __str__(self):
        return {
            "status_code": self.status_code,
            "headers": self.headers,
            "text": self.text,
            "raw": self.raw,
        }.__str__()

# --- Utilities & Detectors ---
def get_os_name():
    """Detects the operating system, explicitly checking for Android/Termux."""
    if "PREFIX" in os.environ and "com.termux" in os.environ["PREFIX"]:
        return "Termux"
    elif hasattr(sys, 'getandroidapilevel'):
        return "Android"
    
    sys_name = platform.system()
    if sys_name == "Darwin":
        return "macOS"
    return sys_name

def get_current_directory():
    if getattr(sys, 'frozen', False):
        current_directory = os.path.dirname(sys.executable)
    else:
        current_directory = os.path.dirname(os.path.abspath(__file__))
    return current_directory


def setup_logger(log_level: int):
    """Sets up separate log files for access (success) and errors inside a single logs directory."""
    log_levels = {
        1: logging.CRITICAL,
        2: logging.ERROR,
        3: logging.WARNING,
        4: logging.INFO,
        5: logging.DEBUG,
    }
    level = log_levels.get(log_level, logging.INFO)
    
    logs_dir = os.path.join(get_current_directory(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    
    logger = logging.getLogger()
    logger.setLevel(level)
    
    if logger.hasHandlers():
        logger.handlers.clear()
        
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Access Log Handler
    class SuccessFilter(logging.Filter):
        def filter(self, record):
            return record.levelno < logging.WARNING

    access_handler = logging.FileHandler(os.path.join(logs_dir, "access_log.log"))
    access_handler.setLevel(logging.DEBUG)
    access_handler.setFormatter(formatter)
    access_handler.addFilter(SuccessFilter())
    logger.addHandler(access_handler)

    # Error Log Handler
    class ErrorFilter(logging.Filter):
        def filter(self, record):
            return record.levelno >= logging.WARNING

    error_handler = logging.FileHandler(os.path.join(logs_dir, "error_log.log"))
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)
    error_handler.addFilter(ErrorFilter())
    logger.addHandler(error_handler)

    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(log_level)
    requests_log.propagate = True


# --- Cache Engine Layer ---
def load_cache():
    cache_path = os.path.join(get_current_directory(), CACHE_FILENAME)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                return json.load(f)
        except Exception:
            logging.warning("Cache file corrupted. Ignoring old cache.")
    return {}

def save_cache(domain, extracted_values):
    cache_path = os.path.join(get_current_directory(), CACHE_FILENAME)
    cache_data = {
        "target_domain": domain,
        "extracted_values": extracted_values,
        "updated_at": time.time()
    }
    try:
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=4)
        logging.debug("Data successfully written to local cache.")
    except Exception as e:
        logging.warning(f"Failed to write to cache: {e}")

def raw_http_request(url, method="GET", headers=None, ignore_ssl=True):
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname
    port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)
    path = parsed_url.path or "/"
    query = f"?{parsed_url.query}" if parsed_url.query else ""
    full_path = path + query

    if parsed_url.scheme == "https":
        if ignore_ssl:
            context = create_default_context()
            context.check_hostname = False
            context.verify_mode = CERT_NONE
        else:
            context = create_default_context()
        sock = context.wrap_socket(socket.create_connection((hostname, port)), server_hostname=hostname)
    else:
        sock = socket.create_connection((hostname, port))

    try:
        request_lines = [
            f"{method} {full_path} HTTP/1.1",
            f"Host: {hostname}",
            "Connection: close",
        ]
        if headers:
            request_lines.extend(f"{key}: {value}" for key, value in headers.items())
        request_lines.append("")  
        request_lines.append("")  
        request_data = "\r\n".join(request_lines)
        sock.sendall(request_data.encode())

        response_data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response_data += chunk

        headers, body = response_data.split(b"\r\n\r\n", 1)
        status_line, *header_lines = headers.split(b"\r\n")
        status_code = int(status_line.split(b" ")[1])
        parsed_headers = {line.split(b":", 1)[0].decode(): line.split(b":", 1)[1].strip().decode()
                          for line in header_lines if b":" in line}

        return RawResponse(status_code, parsed_headers, body, response_data)

    finally:
        sock.close()


def ask_confirmation(prompt: str, is_cron: bool) -> bool:
    if is_cron:
        logging.warning("Cron mode enabled: Rejecting interactive confirmation prompt automatically.")
        return False
    response = input(f"{prompt}\nDo you want to continue? (y/n): ").strip().lower()
    return response in ('y', 'yes')


def calculate_hash(hash_val: int, key: bytearray) -> int:
    for byte in key:
        hash_val = (hash_val * HASH_MULTIPLIER) + byte
        hash_val = hash_val & 0xFFFFFFFF
    return hash_val


def convert_to_hex(hval: int) -> str:
    hex_val = "{:08X}".format(hval)
    return ''.join(reversed([hex_val[i:i+2] for i in range(0, len(hex_val), 2)]))


def get_hash(string: str) -> int:
    return calculate_hash(0, bytearray(string, 'utf-8'))


def hex_to_mac(hex_string: str) -> str:
    hex_string = hex_string.zfill(12).lower()
    mac_address = ":".join(hex_string[i:i+2] for i in range(0, len(hex_string), 2))
    return mac_address


def get_mac_address() -> str:
    hostname = socket.gethostname()
    logging.debug(f"Hostname: {hostname}")
    hval = get_hash(hostname)
    logging.debug(f"Hostname hash: {hval}")
    hval_hex = convert_to_hex(hval)
    logging.debug(f"Hostname hash (hex): {hval_hex}")

    mac_address = hex_to_mac(hval_hex)
    logging.debug(f"Hostname to MAC: {mac_address}")
    return mac_address


def check_domain(domain: str) -> str | None:
    try:
        ip = socket.gethostbyname(domain)
        logging.debug(f"Found {BRAND_NAME} domain: {domain} ({ip})")
        return domain
    except socket.gaierror:
        logging.warning(f"{BRAND_NAME} domain not found: {domain}")
        return None


def ims_request(domain: str, port: int, hostname: str, mac: str, add_req: bool = False, no_otp: bool = False) -> requests.Response | RawResponse:
    url = f"https://{domain}:{port}/"
    get_params = {
        "terminal_sw_version": "RCSAndrd",
        "terminal_vendor": hostname,
        "terminal_model": hostname,
        "SMS_port": 0,
        "act_type": "volatile",
        "IMSI": "",
        "msisdn": "",
        "IMEI": "",
        "vers": 0,
        "token": "",
        "rcs_state": 0,
        "rcs_version": "5.1B",
        "rcs_profile": "joyn_blackbird",
        "client_vendor": "JUIC",
        "default_sms_app": 2,
        "default_vvm_app": 0,
        "device_type": "vvm",
        "client_version": "JSEAndrd-1.0",
        "mac_address": mac,
        "alias": hostname,
        "nwk_intf": "eth" if no_otp else "wifi"
    }

    if add_req:
        get_params["op_type"] = "add"
        get_url = f"{url}?"
        for key, value in get_params.items():
            get_url += f"{key}={value}&"
        return raw_http_request(get_url, method="GET", ignore_ssl=True)

    return requests.get(url, params=get_params, verify=False)


def otp_verify(domain: str, port: int, otp: int, cookies_str: str):
    url = f"https://{domain}:{port}/"
    get_params = {"OTP": otp}
    cookies = requests.cookies.cookiejar_from_dict(
        {cookie.split("=")[0]: cookie.split("=")[1] for cookie in cookies_str.split("; ")}
    )
    return requests.get(url, params=get_params, cookies=cookies, verify=False)


def ims_register(domain: str, port: int, hostname: str, mac: str, is_cron: bool) -> bool:
    logging.info(f"Registering the device on {BRAND_NAME} SIP...")
    if not ask_confirmation("An OTP will be sent to your registered mobile number.", is_cron):
        logging.error("Registration requires OTP. Cron mode blocked interactive prompt.")
        sys.exit(1)

    response = ims_request(domain, port, hostname, mac, add_req=True)
    logging.debug(response)
    if response.status_code != 200:
        logging.error(f"Registration request failed with status code: {response.status_code}")
        logging.error(f"Registration response: {response.text}")
        logging.info(f"Failed to register the device on {BRAND_NAME} SIP!")
        return False

    mobile = response.headers.get("x-amn")
    logging.info(f"OTP was sent successfully to {mobile}!")

    otp_attempts = 0
    while otp_attempts < 3:
        otp = int(input("Enter the OTP: "))
        response = otp_verify(domain, port, otp, response.headers.get("Set-Cookie"))
        if response.status_code != 200:
            logging.error(f"OTP verification failed with status code: {response.status_code}")
            logging.info("Failed to verify the OTP! Try again!")
            otp_attempts += 1
        else:
            logging.info("OTP verification successful!")
            logging.info("Device registered successfully!")
            return True


def generate_asterisk_config(extracted_values: dict, target_hostname: str):
    """Generates an Asterisk pjsip.conf configuration, dynamically building exact required names."""
    domain = extracted_values.get('home_network_domain_name', DEFAULT_IMS_DOMAIN)
    user = extracted_values.get('username', 'UNKNOWN')
    pwd = extracted_values.get('userpwd', '')

    proxy = f"sip:{target_hostname}:5068\\;lr"

    asterisk_config = f"""
; ==========================================================
; Asterisk PJSIP Configuration for {BRAND_NAME}
; Auto-generated by RatioJuris (v1 Beta)
; ==========================================================

[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:5060

[{BRAND_LOWER}]
type=registration
transport=transport-udp
outbound_auth={BRAND_LOWER}_auth
server_uri=sip:{domain}
client_uri=sip:+{user}@{domain}
outbound_proxy={proxy}
retry_interval=60
contact_user=+{user}

[{BRAND_LOWER}_auth]
type=auth
auth_type=userpass
password={pwd}
username={user}

[{BRAND_LOWER}_endpoint]
type=endpoint
transport=transport-udp
context=from-{BRAND_LOWER}
disallow=all
allow=alaw,ulaw,g722
outbound_auth={BRAND_LOWER}_auth
aors={BRAND_LOWER}_aor
outbound_proxy={proxy}
from_domain={domain}
from_user=+{user}

[{BRAND_LOWER}_aor]
type=aor
contact=sip:{domain}
outbound_proxy={proxy}
"""
    output_path = os.path.join(get_current_directory(), "pjsip.conf")
    with open(output_path, "w") as configfile:
        configfile.write(asterisk_config.strip())
    logging.info(f"Asterisk PJSIP Configuration saved to {output_path}")


def write_configuration_files(extracted_values: dict, target_hostname: str):
    config = configparser.ConfigParser()
    config.read_string(DEFAULT_MICROSIP_CONFIG)

    config.set("Account1", "label", f"{BRAND_NAME} SIP")
    config.set("Account1", "server", extracted_values.get("home_network_domain_name", ""))
    config.set("Account1", "proxy", f"{target_hostname}:5068")
    config.set("Account1", "domain", f"{target_hostname}:5068")
    config.set("Account1", "username", f"+{extracted_values.get('username', '')}")
    config.set("Account1", "password", extracted_values.get("userpwd", ""))
    config.set("Account1", "authID", extracted_values.get("username", ""))

    microsip_path = os.path.join(get_current_directory(), "microsip.ini")
    with open(microsip_path, "w") as configfile:
        config.write(configfile)
    logging.info(f"MicroSIP Configuration saved to {microsip_path}")

    generate_asterisk_config(extracted_values, target_hostname)

    with open(os.path.join(get_current_directory(), DEFAULT_CONFIG_FLAG_FILENAME), "w") as flagfile:
        flagfile.write("1")
        
    logging.info("All Configurations Written Safely!")


def parse_sip_config(sip_config: ET.Element, target_hostname: str):
    params_to_extract = [
        "realm", "username", "userpwd", "home_network_domain_name",
        "address", "private_user_identity", "public_user_identity"
    ]

    extracted_values = {}
    for parm in sip_config.findall(".//parm"):
        name = parm.attrib.get("name")
        value = parm.attrib.get("value")
        if name in params_to_extract:
            extracted_values[name] = value

    logging.debug("Extracted SIP Configuration:")
    for key, value in extracted_values.items():
        logging.debug(f"{key}: {value}")

    save_cache(target_hostname, extracted_values)
    write_configuration_files(extracted_values, target_hostname)


def main(no_otp: bool, is_cron: bool, force_refresh: bool):
    cache = load_cache()
    
    if not force_refresh and "extracted_values" in cache and "target_domain" in cache:
        logging.info("[*] Valid cache signature found. Skipping network processing requests.")
        write_configuration_files(cache["extracted_values"], cache["target_domain"])
        return

    cached_domain = cache.get("target_domain") if not force_refresh else None
    target_domain = check_domain(cached_domain) if cached_domain else check_domain(DEFAULT_TARGET_HOSTNAME)
    
    if target_domain is None:
        target_domain = check_domain(DEFAULT_TARGET_HOSTNAME)
        if target_domain is None:
            logging.info(f"Default hostname failed. Trying fallback IP: {FALLBACK_TARGET_IP}...")
            target_domain = check_domain(FALLBACK_TARGET_IP)

    while target_domain is None:
        if is_cron:
            logging.error("Cron mode active: Cannot interactively prompt for missing domain. Exiting.")
            sys.exit(1)
            
        logging.info(f"Couldn't find {BRAND_NAME} domain/IP automatically!")
        input_domain = input(f"Please enter the {BRAND_NAME} domain/IP manually: ")
        target_domain = check_domain(input_domain)

    hostname = socket.gethostname()
    mac = get_mac_address()

    try_config_count = 0
    sip_config_success = False

    while try_config_count < 3:
        sip_configuration_response = ims_request(
            target_domain, DEFAULT_HTTPS_PORT, hostname, mac, add_req=False, no_otp=no_otp
        )
        if sip_configuration_response.status_code != 200:
            logging.warning(f"SIP Configuration request failed with status code: {sip_configuration_response.status_code}")
            logging.info(f"Hostname: {hostname} isn't registered on {BRAND_NAME} SIP yet!")
            
            if not ims_register(target_domain, DEFAULT_HTTPS_PORT, hostname, mac, is_cron):
                logging.error(f"Failed to register the device on {BRAND_NAME} SIP!")
            else:
                try_config_count += 1
        else:
            sip_config_success = True
            break

    if not sip_config_success:
        logging.error("Failed to get SIP Configuration!")
        sys.exit(1)

    logging.debug(f"SIP Configuration request successful with status code: {sip_configuration_response.status_code}")
    logging.info("Received SIP Configuration Successfully!")

    root = ET.fromstring(sip_configuration_response.text)
    parse_sip_config(sip_config=root, target_hostname=target_domain)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RatioJuris SIP Configuration Tool")
    parser.add_argument('-n', '--no-otp', help="Configure without OTP verification", action='store_true')
    parser.add_argument('-c', '--cron', help="Run in silent background mode (disables manual inputs)", action='store_true')
    parser.add_argument('-f', '--refresh', help="Force-bypass the local cache file and request new parameters", action='store_true')
    parser.add_argument('-l', '--log-level', help="Log level (1:CRITICAL, 2:ERROR, 3:WARNING, 4:INFO, 5:DEBUG)", type=int, default=4)
    args = parser.parse_args()

    setup_logger(args.log_level)

    if not args.cron:
        os_name = get_os_name()
        ascii_banner = pyfiglet.figlet_format(os_name, font="slant")
        
        print("=" * 80)
        print("                                RatioJuris                                ")
        print(f"            ({BRAND_NAME} SIP Configuration Tool for Multi-Platform)        ")
        print("=" * 80)
        print(ascii_banner.rstrip('\n'))
        print("-" * 80)
        print(" Version : v1 Beta")
        print(" Author  : RatioJuris")
        print(" GitHub  : https://github.com/RatioJuris/jfc_config/")
        print("-" * 80)
        print("Supported outputs: MicroSIP (microsip.ini) and Asterisk (pjsip.conf)")
        print("-" * 80)

    main(args.no_otp, args.cron, args.refresh)
