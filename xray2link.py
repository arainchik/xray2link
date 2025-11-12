#!/usr/bin/env python3

import json
import argparse
import sys
import base64
from urllib.parse import urlencode, quote

# Try to import pyqrcode and set a flag
try:
    import pyqrcode
    PYQRCODE_AVAILABLE = True
except ImportError:
    PYQRCODE_AVAILABLE = False


def list_all_clients(config):
    """
    Iterates through the config and returns a list of all client emails.
    """
    all_emails = []
    for inbound in config.get('inbounds', []):
        protocol = inbound.get('protocol')
        if protocol not in ['vless', 'vmess', 'trojan']:
            continue

        client_list = inbound.get('settings', {}).get('clients', [])
        for client in client_list:
            if client.get('email'):
                all_emails.append(client.get('email'))
    
    # Return a sorted list of unique emails
    return sorted(list(set(all_emails)))

def find_client_config(config, client_email):
    """
    Iterates through the config's inbounds to find the specified client by email.
    Supports vless, vmess, and trojan.
    Returns a dictionary with all necessary info if found, else None.
    """
    for inbound in config.get('inbounds', []):
        protocol = inbound.get('protocol')
        if protocol not in ['vless', 'vmess', 'trojan']:
            continue

        inbound_port = inbound.get('port')
        stream_settings = inbound.get('streamSettings', {})
        client_list = inbound.get('settings', {}).get('clients', [])

        for client in client_list:
            if client.get('email') == client_email:
                return {
                    'client_data': client,
                    'protocol': protocol,
                    'port': inbound_port,
                    'stream_settings': stream_settings
                }
    return None

def create_vless_url(client_info, server_address):
    """Generates a vless:// URL."""
    client_data = client_info['client_data']
    port = client_info['port']
    stream_settings = client_info['stream_settings']
    
    uuid = client_data.get('id')
    remark = quote(client_data.get('email', ''))
    
    url = f"vless://{uuid}@{server_address}:{port}"
    
    params = {}
    network = stream_settings.get('network')
    security = stream_settings.get('security')

    params['type'] = network
    if security and security != 'none':
        params['security'] = security

    if client_data.get('flow'):
        params['flow'] = client_data.get('flow')
    
    if security in ['tls', 'xtls']:
        security_settings = stream_settings.get(f"{security}Settings", {})
        if security_settings.get('serverName'):
            params['sni'] = security_settings.get('serverName')
        if security_settings.get('fingerprint'):
            params['fp'] = security_settings.get('fingerprint')
    
    if network == 'ws':
        ws_settings = stream_settings.get('wsSettings', {})
        if ws_settings.get('path'):
            params['path'] = ws_settings.get('path')
        if ws_settings.get('headers', {}).get('Host'):
            params['host'] = ws_settings.get('headers').get('Host')
    
    elif network == 'grpc':
        grpc_settings = stream_settings.get('grpcSettings', {})
        if grpc_settings.get('serviceName'):
            params['serviceName'] = grpc_settings.get('serviceName')

    if params:
        url += f"?{urlencode(params)}"
    
    url += f"#{remark}"
    return url

def create_vmess_url(client_info, server_address):
    """Generates a vmess:// URL by Base64-encoding a JSON object."""
    client_data = client_info['client_data']
    port = client_info['port']
    stream_settings = client_info['stream_settings']
    network = stream_settings.get('network')
    security = stream_settings.get('security')

    share_data = {
        "v": "2",
        "ps": client_data.get('email', ''),
        "add": server_address,
        "port": str(port),
        "id": client_data.get('id'),
        "aid": str(client_data.get('alterId', 0)),
        "net": network,
        "type": "none",
        "tls": security if security in ['tls', 'xtls'] else 'none'
    }

    if network == 'ws':
        ws_settings = stream_settings.get('wsSettings', {})
        share_data['path'] = ws_settings.get('path', '/')
        share_data['host'] = ws_settings.get('headers', {}).get('Host', server_address)
    
    elif network == 'grpc':
        grpc_settings = stream_settings.get('grpcSettings', {})
        share_data['path'] = grpc_settings.get('serviceName') 

    json_str = json.dumps(share_data, sort_keys=True, separators=(',', ':'))
    b64_str = base64.b64encode(json_str.encode()).decode()
    return f"vmess://{b64_str}"

def create_trojan_url(client_info, server_address):
    """Generates a trojan:// URL."""
    client_data = client_info['client_data']
    port = client_info['port']
    stream_settings = client_info['stream_settings']
    
    password = client_data.get('password')
    remark = quote(client_data.get('email', ''))
    
    url = f"trojan://{password}@{server_address}:{port}"
    
    params = {}
    network = stream_settings.get('network')
    security = stream_settings.get('security')

    if security and security in ['tls', 'xtls']:
        params['security'] = security
        security_settings = stream_settings.get(f"{security}Settings", {})
        if security_settings.get('serverName'):
            params['sni'] = security_settings.get('serverName')
        if security_settings.get('fingerprint'):
            params['fp'] = security_settings.get('fingerprint')

    if network:
        params['type'] = network

    if network == 'ws':
        ws_settings = stream_settings.get('wsSettings', {})
        if ws_settings.get('path'):
            params['path'] = ws_settings.get('path')
        if ws_settings.get('headers', {}).get('Host'):
            params['host'] = ws_settings.get('headers').get('Host')
    
    elif network == 'grpc':
        grpc_settings = stream_settings.get('grpcSettings', {})
        if grpc_settings.get('serviceName'):
            params['serviceName'] = grpc_settings.get('serviceName')

    if params:
        url += f"?{urlencode(params)}"
    
    url += f"#{remark}"
    return url

def main():
    # --- Updated program name ---
    parser = argparse.ArgumentParser(
        prog="xray2link.py",  # Set program name for help messages
        description="Generate Xray share links or list client emails from config.json"
    )
    # ----------------------------
    
    parser.add_argument(
        "config_file", 
        help="Path to your server's config.json file"
    )
    
    parser.add_argument(
        "--listemails",
        action="store_true",
        help="List all client emails found in the config and exit"
    )

    parser.add_argument(
        "server_address", 
        nargs='?',
        default=None,
        help="Your server's public domain or IP (required for link generation)"
    )
    
    parser.add_argument(
        "client_email", 
        nargs='?',
        default=None,
        help="The 'email' of the client to generate a link for (required for link generation)"
    )
    
    qrcode_help = "Print the share link as an ASCII QR code"
    if not PYQRCODE_AVAILABLE:
        qrcode_help += " (DISABLED: 'pyqrcode' module not found)"
    
    parser.add_argument(
        "-qrcode",
        "--qrcode",
        action="store_true",
        help=qrcode_help
    )

    args = parser.parse_args()

    if args.qrcode and not PYQRCODE_AVAILABLE:
        print(
            "Warning: --qrcode flag was used, but 'pyqrcode' module is not installed.", 
            file=sys.stderr
        )
        print(
            "Please install it with 'pip install pyqrcode' to use this feature.", 
            file=sys.stderr
        )
        print("Falling back to text URL output.", file=sys.stderr)
        print("-" * 30, file=sys.stderr)

    try:
        with open(args.config_file, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Error: Config file not found at {args.config_file}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {args.config_file}. Check for syntax errors.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred while reading the file: {e}", file=sys.stderr)
        sys.exit(1)

    if args.listemails:
        emails = list_all_clients(config)
        if not emails:
            print("No client emails found in the configuration.", file=sys.stderr)
            sys.exit(0)
        
        print("Found client emails:")
        for email in emails:
            print(f"- {email}")
        sys.exit(0)
    
    if not args.server_address or not args.client_email:
        parser.error("The arguments server_address and client_email are required when --listemails is not used.")

    client_info = find_client_config(config, args.client_email)

    if not client_info:
        print(f"Error: Client with email '{args.client_email}' not found in any inbounds.", file=sys.stderr)
        sys.exit(1)

    protocol = client_info['protocol']
    url = ""
    
    try:
        if protocol == 'vless':
            url = create_vless_url(client_info, args.server_address)
        elif protocol == 'vmess':
            url = create_vmess_url(client_info, args.server_address)
        elif protocol == 'trojan':
            url = create_trojan_url(client_info, args.server_address)
        else:
            print(f"Error: Unsupported protocol '{protocol}'", file=sys.stderr)
            sys.exit(1)
            
    except Exception as e:
        print(f"An error occurred during URL generation: {e}", file=sys.stderr)
        sys.exit(1)

    if args.qrcode and PYQRCODE_AVAILABLE:
        try:
            qr_code = pyqrcode.create(url)
            print(qr_code.terminal())
        except Exception as e:
            print(f"Error generating QR code: {e}", file=sys.stderr)
            print("\nHere is the URL string instead:")
            print(url)
            sys.exit(1)
    else:
        print(url)

if __name__ == "__main__":
    main()
