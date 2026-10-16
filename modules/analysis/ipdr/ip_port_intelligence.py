"""Forensic IP Company/ISP and Port/Application/VPN Intelligence for IPDR."""

from __future__ import annotations

from functools import lru_cache
import ipaddress
import re
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Known CIDR Networks -> (Company / ISP, Network Role)
# ---------------------------------------------------------------------------
_KNOWN_NETWORKS_RAW: tuple[tuple[str, str, str], ...] = (
    # --- Meta Platforms (WhatsApp / Facebook / Instagram) ---
    ("2a03:2880::/32", "Meta Platforms (WhatsApp / Facebook / Instagram)", "META_SOCIAL_VOIP"),
    ("31.13.24.0/21", "Meta Platforms (WhatsApp / Facebook / Instagram)", "META_SOCIAL_VOIP"),
    ("31.13.64.0/18", "Meta Platforms (WhatsApp / Facebook / Instagram)", "META_SOCIAL_VOIP"),
    ("66.220.144.0/20", "Meta Platforms (WhatsApp / Facebook / Instagram)", "META_SOCIAL_VOIP"),
    ("69.63.176.0/20", "Meta Platforms (WhatsApp / Facebook / Instagram)", "META_SOCIAL_VOIP"),
    ("69.171.224.0/19", "Meta Platforms (WhatsApp / Facebook / Instagram)", "META_SOCIAL_VOIP"),
    ("102.132.96.0/20", "Meta Platforms (WhatsApp / Facebook / Instagram)", "META_SOCIAL_VOIP"),
    ("129.134.0.0/17", "Meta Platforms (WhatsApp / Facebook / Instagram)", "META_SOCIAL_VOIP"),
    ("157.240.0.0/16", "Meta Platforms (WhatsApp / Facebook / Instagram)", "META_SOCIAL_VOIP"),
    ("173.252.64.0/18", "Meta Platforms (WhatsApp / Facebook / Instagram)", "META_SOCIAL_VOIP"),
    ("179.60.192.0/22", "Meta Platforms (WhatsApp / Facebook / Instagram)", "META_SOCIAL_VOIP"),
    ("185.60.216.0/22", "Meta Platforms (WhatsApp / Facebook / Instagram)", "META_SOCIAL_VOIP"),
    ("204.15.20.0/22", "Meta Platforms (WhatsApp / Facebook / Instagram)", "META_SOCIAL_VOIP"),

    # --- Telegram Messenger ---
    ("91.108.4.0/22", "Telegram Messenger LLP", "TELEGRAM_VOIP_CHAT"),
    ("91.108.8.0/22", "Telegram Messenger LLP", "TELEGRAM_VOIP_CHAT"),
    ("91.108.12.0/22", "Telegram Messenger LLP", "TELEGRAM_VOIP_CHAT"),
    ("91.108.16.0/22", "Telegram Messenger LLP", "TELEGRAM_VOIP_CHAT"),
    ("91.108.20.0/22", "Telegram Messenger LLP", "TELEGRAM_VOIP_CHAT"),
    ("91.108.56.0/22", "Telegram Messenger LLP", "TELEGRAM_VOIP_CHAT"),
    ("91.105.192.0/23", "Telegram Messenger LLP", "TELEGRAM_VOIP_CHAT"),
    ("149.154.160.0/20", "Telegram Messenger LLP", "TELEGRAM_VOIP_CHAT"),
    ("185.76.151.0/24", "Telegram Messenger LLP", "TELEGRAM_VOIP_CHAT"),
    ("2001:67c:4e8::/48", "Telegram Messenger LLP", "TELEGRAM_VOIP_CHAT"),
    ("2001:b28:f23c::/46", "Telegram Messenger LLP", "TELEGRAM_VOIP_CHAT"),
    ("2a0a:f280::/32", "Telegram Messenger LLP", "TELEGRAM_VOIP_CHAT"),

    # --- Zangi / Hetzner VoIP & Messaging Clusters ---
    ("138.201.0.0/16", "Hetzner / Zangi & VoIP Cloud Cluster", "ZANGI_OR_VPS"),
    ("144.76.0.0/16", "Hetzner / Zangi & VoIP Cloud Cluster", "ZANGI_OR_VPS"),
    ("148.251.0.0/16", "Hetzner / Zangi & VoIP Cloud Cluster", "ZANGI_OR_VPS"),
    ("176.9.0.0/16", "Hetzner / Zangi & VoIP Cloud Cluster", "ZANGI_OR_VPS"),
    ("88.198.0.0/16", "Hetzner / Zangi & VoIP Cloud Cluster", "ZANGI_OR_VPS"),
    ("95.216.0.0/16", "Hetzner / Zangi & VoIP Cloud Cluster", "ZANGI_OR_VPS"),
    ("65.108.0.0/16", "Hetzner / Zangi & VoIP Cloud Cluster", "ZANGI_OR_VPS"),
    ("5.9.0.0/16", "Hetzner / Zangi & VoIP Cloud Cluster", "ZANGI_OR_VPS"),
    ("2a01:4f8::/32", "Hetzner / Zangi & VoIP Cloud Cluster", "ZANGI_OR_VPS"),
    ("2a01:4ff::/32", "Hetzner / Zangi & VoIP Cloud Cluster", "ZANGI_OR_VPS"),

    # --- Known Commercial VPN & Anonymizer Networks ---
    ("2a03:1b20::/32", "31173 Services AB (Mullvad VPN / OVPN Sweden)", "VPN_PROVIDER"),
    ("185.65.134.0/23", "31173 Services AB (Mullvad VPN / OVPN Sweden)", "VPN_PROVIDER"),
    ("193.138.218.0/24", "31173 Services AB (Mullvad VPN / OVPN Sweden)", "VPN_PROVIDER"),
    ("185.159.156.0/22", "M247 / ProtonVPN / Commercial VPN Server", "VPN_PROVIDER"),
    ("37.120.128.0/18", "M247 / Commercial VPN Infrastructure", "VPN_PROVIDER"),
    ("146.70.0.0/16", "M247 / NordVPN / Surfshark / ProtonVPN Server", "VPN_PROVIDER"),
    ("2a0d:5600::/32", "M247 / Commercial VPN Infrastructure", "VPN_PROVIDER"),
    ("138.199.0.0/16", "Datacamp / CDN77 (ExpressVPN / NordVPN Server)", "VPN_PROVIDER"),
    ("156.146.0.0/16", "Datacamp / Commercial VPN Server", "VPN_PROVIDER"),
    ("212.102.32.0/19", "Datacamp / Commercial VPN Server", "VPN_PROVIDER"),
    ("162.159.192.0/24", "Cloudflare WARP VPN Endpoint", "VPN_PROVIDER"),
    ("162.159.193.0/24", "Cloudflare WARP VPN Endpoint", "VPN_PROVIDER"),
    ("162.159.195.0/24", "Cloudflare WARP VPN Endpoint", "VPN_PROVIDER"),

    # --- VPS / Cloud Hosting Often Used for Custom VPNs / Proxies ---
    ("2400:8900::/28", "Akamai Connected Cloud / Linode VPS", "VPS_HOSTING"),
    ("139.162.0.0/16", "Akamai Connected Cloud / Linode VPS", "VPS_HOSTING"),
    ("172.104.0.0/15", "Akamai Connected Cloud / Linode VPS", "VPS_HOSTING"),
    ("45.79.0.0/16", "Akamai Connected Cloud / Linode VPS", "VPS_HOSTING"),
    ("2401:c080::/32", "Choopa / Constant / Vultr VPS", "VPS_HOSTING"),
    ("45.32.0.0/16", "Choopa / Constant / Vultr VPS", "VPS_HOSTING"),
    ("45.76.0.0/16", "Choopa / Constant / Vultr VPS", "VPS_HOSTING"),
    ("45.77.0.0/16", "Choopa / Constant / Vultr VPS", "VPS_HOSTING"),
    ("139.180.0.0/16", "Choopa / Constant / Vultr VPS", "VPS_HOSTING"),
    ("149.28.0.0/16", "Choopa / Constant / Vultr VPS", "VPS_HOSTING"),
    ("2400:6180::/32", "DigitalOcean Cloud VPS", "VPS_HOSTING"),
    ("159.65.0.0/16", "DigitalOcean Cloud VPS", "VPS_HOSTING"),
    ("159.89.0.0/16", "DigitalOcean Cloud VPS", "VPS_HOSTING"),
    ("165.22.0.0/16", "DigitalOcean Cloud VPS", "VPS_HOSTING"),
    ("167.71.0.0/16", "DigitalOcean Cloud VPS", "VPS_HOSTING"),
    ("134.209.0.0/16", "DigitalOcean Cloud VPS", "VPS_HOSTING"),
    ("143.110.0.0/16", "DigitalOcean Cloud VPS", "VPS_HOSTING"),
    ("51.15.0.0/16", "Scaleway / Online S.A.S. VPS", "VPS_HOSTING"),
    ("51.158.0.0/16", "Scaleway / Online S.A.S. VPS", "VPS_HOSTING"),
    ("51.159.0.0/16", "Scaleway / Online S.A.S. VPS", "VPS_HOSTING"),
    ("51.38.0.0/16", "OVHcloud VPS Hosting", "VPS_HOSTING"),
    ("51.68.0.0/16", "OVHcloud VPS Hosting", "VPS_HOSTING"),
    ("51.75.0.0/16", "OVHcloud VPS Hosting", "VPS_HOSTING"),
    ("51.77.0.0/16", "OVHcloud VPS Hosting", "VPS_HOSTING"),
    ("51.79.0.0/16", "OVHcloud VPS Hosting", "VPS_HOSTING"),
    ("51.89.0.0/16", "OVHcloud VPS Hosting", "VPS_HOSTING"),
    ("51.195.0.0/16", "OVHcloud VPS Hosting", "VPS_HOSTING"),
    ("51.210.0.0/16", "OVHcloud VPS Hosting", "VPS_HOSTING"),

    # --- Indian Mobile & Broadband Subscriber ISPs (P2P VoIP / Social Calling) ---
    ("157.32.0.0/12", "Reliance Jio Infocomm Limited", "INDIAN_ISP_SUBSCRIBER"),
    ("152.56.0.0/13", "Reliance Jio Infocomm Limited", "INDIAN_ISP_SUBSCRIBER"),
    ("49.32.0.0/11", "Reliance Jio Infocomm Limited", "INDIAN_ISP_SUBSCRIBER"),
    ("115.240.0.0/13", "Reliance Jio Infocomm Limited", "INDIAN_ISP_SUBSCRIBER"),
    ("2409:4000::/19", "Reliance Jio Infocomm Limited", "INDIAN_ISP_SUBSCRIBER"),
    ("2405:200::/31", "Reliance Jio Infocomm Limited", "INDIAN_ISP_SUBSCRIBER"),
    ("106.192.0.0/11", "Bharti Airtel Limited", "INDIAN_ISP_SUBSCRIBER"),
    ("27.56.0.0/13", "Bharti Airtel Limited", "INDIAN_ISP_SUBSCRIBER"),
    ("122.160.0.0/11", "Bharti Airtel Limited", "INDIAN_ISP_SUBSCRIBER"),
    ("182.64.0.0/12", "Bharti Airtel Limited", "INDIAN_ISP_SUBSCRIBER"),
    ("49.200.0.0/13", "Bharti Airtel Limited", "INDIAN_ISP_SUBSCRIBER"),
    ("223.176.0.0/12", "Bharti Airtel Limited", "INDIAN_ISP_SUBSCRIBER"),
    ("2401:4900::/32", "Bharti Airtel Limited", "INDIAN_ISP_SUBSCRIBER"),
    ("2404:a800::/32", "Bharti Airtel Limited", "INDIAN_ISP_SUBSCRIBER"),
    ("42.104.0.0/13", "Vodafone Idea Limited (Vi)", "INDIAN_ISP_SUBSCRIBER"),
    ("49.128.0.0/11", "Vodafone Idea Limited (Vi)", "INDIAN_ISP_SUBSCRIBER"),
    ("103.208.0.0/22", "Vodafone Idea Limited (Vi)", "INDIAN_ISP_SUBSCRIBER"),
    ("112.79.0.0/16", "Vodafone Idea Limited (Vi)", "INDIAN_ISP_SUBSCRIBER"),
    ("27.97.0.0/16", "Vodafone Idea Limited (Vi)", "INDIAN_ISP_SUBSCRIBER"),
    ("2402:3a80::/32", "Vodafone Idea Limited (Vi)", "INDIAN_ISP_SUBSCRIBER"),
    ("2402:8100::/32", "Vodafone Idea Limited (Vi)", "INDIAN_ISP_SUBSCRIBER"),
    ("117.96.0.0/11", "BSNL (Bharat Sanchar Nigam Limited)", "INDIAN_ISP_SUBSCRIBER"),
    ("117.192.0.0/10", "BSNL (Bharat Sanchar Nigam Limited)", "INDIAN_ISP_SUBSCRIBER"),
    ("59.88.0.0/13", "BSNL (Bharat Sanchar Nigam Limited)", "INDIAN_ISP_SUBSCRIBER"),
    ("61.0.0.0/14", "BSNL (Bharat Sanchar Nigam Limited)", "INDIAN_ISP_SUBSCRIBER"),

    # --- Google LLC (YouTube / Android / Gmail / Google Meet / FCM) ---
    ("2001:4860::/32", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("2404:6800::/32", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("2607:f8b0::/32", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("2a00:1450::/32", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("2600:1900::/28", "Google Cloud Platform (GCP)", "GOOGLE_CLOUD_APP"),
    ("8.8.8.0/24", "Google Public DNS", "GOOGLE_CLOUD_APP"),
    ("8.8.4.0/24", "Google Public DNS", "GOOGLE_CLOUD_APP"),
    ("34.0.0.0/8", "Google Cloud Platform (GCP)", "GOOGLE_CLOUD_APP"),
    ("35.184.0.0/13", "Google Cloud Platform (GCP)", "GOOGLE_CLOUD_APP"),
    ("35.192.0.0/11", "Google Cloud Platform (GCP)", "GOOGLE_CLOUD_APP"),
    ("35.224.0.0/12", "Google Cloud Platform (GCP)", "GOOGLE_CLOUD_APP"),
    ("35.240.0.0/13", "Google Cloud Platform (GCP)", "GOOGLE_CLOUD_APP"),
    ("64.233.160.0/19", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("66.102.0.0/20", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("66.249.64.0/19", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("72.14.192.0/18", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("74.125.0.0/16", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("108.177.0.0/17", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("142.250.0.0/15", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("172.217.0.0/16", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("172.253.0.0/16", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("173.194.0.0/16", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("209.85.128.0/17", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("216.58.192.0/19", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),
    ("216.239.32.0/19", "Google LLC (YouTube / Android / Google Services)", "GOOGLE_CLOUD_APP"),

    # --- Apple Inc. (FaceTime / iMessage / iCloud / APNs) ---
    ("17.0.0.0/8", "Apple Inc. (iCloud / FaceTime / iMessage)", "APPLE_SERVICES"),
    ("2620:149::/32", "Apple Inc. (iCloud / FaceTime / iMessage)", "APPLE_SERVICES"),
    ("2403:300::/32", "Apple Inc. (iCloud / FaceTime / iMessage)", "APPLE_SERVICES"),

    # --- Amazon AWS / CloudFront (Signal, Snapchat, Botim, App Backends) ---
    ("2600:9000::/28", "Amazon CloudFront / AWS (Signal / App CDN)", "CLOUD_CDN"),
    ("2600:1f00::/24", "Amazon Web Services (AWS)", "CLOUD_CDN"),
    ("2406:da00::/24", "Amazon Web Services (AWS India/APAC)", "CLOUD_CDN"),
    ("3.0.0.0/8", "Amazon Web Services (AWS / Signal / App Cloud)", "CLOUD_CDN"),
    ("13.32.0.0/12", "Amazon CloudFront CDN", "CLOUD_CDN"),
    ("13.126.0.0/15", "Amazon AWS (Mumbai Region)", "CLOUD_CDN"),
    ("13.232.0.0/14", "Amazon AWS (Mumbai Region)", "CLOUD_CDN"),
    ("15.206.0.0/15", "Amazon AWS (Mumbai Region)", "CLOUD_CDN"),
    ("18.60.0.0/14", "Amazon AWS (India Region)", "CLOUD_CDN"),
    ("52.0.0.0/10", "Amazon Web Services (AWS)", "CLOUD_CDN"),
    ("54.0.0.0/9", "Amazon Web Services (AWS)", "CLOUD_CDN"),
    ("65.8.0.0/14", "Amazon CloudFront CDN", "CLOUD_CDN"),
    ("99.84.0.0/16", "Amazon CloudFront CDN", "CLOUD_CDN"),

    # --- Cloudflare (CDN / Security / WARP) ---
    ("2606:4700::/32", "Cloudflare Inc. (CDN / Security / WARP)", "CLOUDFLARE"),
    ("1.1.1.0/24", "Cloudflare Public DNS (1.1.1.1)", "CLOUDFLARE"),
    ("1.0.0.0/24", "Cloudflare Public DNS (1.0.0.1)", "CLOUDFLARE"),
    ("104.16.0.0/12", "Cloudflare Inc. (CDN / Reverse Proxy / WARP)", "CLOUDFLARE"),
    ("172.64.0.0/13", "Cloudflare Inc. (CDN / Reverse Proxy / WARP)", "CLOUDFLARE"),
    ("162.158.0.0/15", "Cloudflare Inc. (CDN / Reverse Proxy / WARP)", "CLOUDFLARE"),

    # --- Akamai Technologies ---
    ("2600:1400::/24", "Akamai Technologies (App & Video CDN)", "CLOUD_CDN"),
    ("2a02:26f0::/32", "Akamai Technologies (App & Video CDN)", "CLOUD_CDN"),
    ("23.0.0.0/12", "Akamai Technologies (App & Video CDN)", "CLOUD_CDN"),
    ("96.6.0.0/15", "Akamai Technologies (App & Video CDN)", "CLOUD_CDN"),
    ("104.64.0.0/10", "Akamai Technologies (App & Video CDN)", "CLOUD_CDN"),
    ("184.24.0.0/13", "Akamai Technologies (App & Video CDN)", "CLOUD_CDN"),

    # --- Microsoft Corporation (Azure / Teams / Skype) ---
    ("2603:1000::/20", "Microsoft Corporation (Azure / Teams / Skype)", "MICROSOFT_CLOUD"),
    ("2a01:111::/32", "Microsoft Corporation (Azure / Teams / Skype)", "MICROSOFT_CLOUD"),
    ("20.0.0.0/8", "Microsoft Corporation (Azure / Teams / Skype)", "MICROSOFT_CLOUD"),
    ("40.64.0.0/10", "Microsoft Corporation (Azure / Teams / Skype)", "MICROSOFT_CLOUD"),
    ("52.96.0.0/12", "Microsoft Corporation (Teams / Office 365 / Skype)", "MICROSOFT_CLOUD"),
)

_COMPILED_IPV4: list[tuple[ipaddress.IPv4Network, str, str]] = []
_COMPILED_IPV6: list[tuple[ipaddress.IPv6Network, str, str]] = []

for _cidr, _org, _role in _KNOWN_NETWORKS_RAW:
    _net = ipaddress.ip_network(_cidr, strict=False)
    if isinstance(_net, ipaddress.IPv4Network):
        _COMPILED_IPV4.append((_net, _org, _role))
    else:
        _COMPILED_IPV6.append((_net, _org, _role))

# Sort most specific prefixes first
_COMPILED_IPV4.sort(key=lambda item: item[0].prefixlen, reverse=True)
_COMPILED_IPV6.sort(key=lambda item: item[0].prefixlen, reverse=True)
_NAT64_NET = ipaddress.IPv6Network("64:ff9b::/96")


def sanitize_ip_text(value: Any) -> str:
    """Clean IPv4/IPv6 text, fixing Vi quadruple-colon typos (:::: -> ::)."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>", "null"}:
        return ""
    if "/" in text:
        text = text.split("/", 1)[0].strip()
    if ":" in text:
        text = re.sub(r":{3,}", "::", text)
    try:
        return ipaddress.ip_address(text).compressed
    except ValueError:
        return text


@lru_cache(maxsize=16384)
def identify_ip_owner(ip_value: str) -> tuple[str, str, str]:
    """Return (company_name, role_code, decoded_nat64_ipv4)."""
    cleaned = sanitize_ip_text(ip_value)
    if not cleaned:
        return ("Unknown / Missing IP", "UNKNOWN", "")

    lower_ip = cleaned.lower()

    # Meta's signature ':face:b00c:' is embedded in ISP edge caches (Jio/Airtel)
    if ":face:b00c:" in lower_ip or lower_ip.startswith("2a03:2880:"):
        isp_cache = ""
        if lower_ip.startswith("2404:a800:"):
            isp_cache = " [via Airtel Edge Cache]"
        elif lower_ip.startswith(("2405:200:", "2405:201:")):
            isp_cache = " [via Jio Edge Cache]"
        return (
            f"Meta Platforms (WhatsApp / Facebook / Instagram){isp_cache}",
            "META_SOCIAL_VOIP",
            "",
        )

    try:
        ip_obj = ipaddress.ip_address(cleaned)
    except ValueError:
        return ("Unverified / Invalid IP Format", "INVALID", "")

    if ip_obj.is_private or ip_obj.is_loopback:
        return ("Private / Carrier-Grade NAT Internal IP", "PRIVATE_IP", "")

    # Decode NAT64 (64:ff9b::/96) embedded IPv4
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj in _NAT64_NET:
        embedded_v4 = str(ipaddress.IPv4Address(int(ip_obj) & 0xFFFFFFFF))
        v4_org, v4_role, _ = identify_ip_owner(embedded_v4)
        return (
            f"{v4_org} [via NAT64 -> {embedded_v4}]",
            v4_role if v4_role != "UNKNOWN" else "NAT64_GATEWAY",
            embedded_v4,
        )

    if isinstance(ip_obj, ipaddress.IPv4Address):
        for net, org, role in _COMPILED_IPV4:
            if ip_obj in net:
                return (org, role, "")
    else:
        for net, org, role in _COMPILED_IPV6:
            if ip_obj in net:
                return (org, role, "")

    return ("External Server / Unindexed ASN", "EXTERNAL_UNINDEXED", "")


@lru_cache(maxsize=32768)
def classify_ip_and_port(
    ip_value: str,
    port_value: Any,
    source_port_value: Any = None,
) -> dict[str, str]:
    """Classify (Destination IP, Destination Port) into Company, App, Category & Risk."""
    company, role, nat64_v4 = identify_ip_owner(ip_value)

    port: int | None = None
    try:
        if port_value is not None and str(port_value).strip() != "":
            port = int(float(str(port_value).strip()))
    except (TypeError, ValueError):
        port = None

    src_port: int | None = None
    try:
        if source_port_value is not None and str(source_port_value).strip() != "":
            src_port = int(float(str(source_port_value).strip()))
    except (TypeError, ValueError):
        src_port = None

    # 1. Explicit VPN / Proxy Ports or Known VPN Providers
    vpn_ports = {
        1194: "OpenVPN Tunnel (Port 1194)",
        51820: "WireGuard VPN Tunnel (Port 51820)",
        2408: "Cloudflare WARP WireGuard VPN (Port 2408)",
        1723: "PPTP VPN Tunnel (Port 1723)",
        1701: "L2TP VPN Tunnel (Port 1701)",
        8388: "Shadowsocks Encrypted Proxy / VPN (Port 8388)",
        8389: "Shadowsocks Encrypted Proxy / VPN (Port 8389)",
        9050: "Tor Anonymizer SOCKS Proxy (Port 9050)",
        9150: "Tor Browser Anonymizer (Port 9150)",
        9001: "Tor Relay Node (Port 9001)",
        1080: "SOCKS5 Proxy Tunnel (Port 1080)",
    }

    if port in vpn_ports:
        return {
            "ip_company": company,
            "service_category": "VPN_PROXY_ANONYMIZER",
            "application_name": vpn_ports[port],
            "forensic_significance": "HIGH - Encrypted VPN / Proxy / Anonymizer Tunnel Detected",
            "nat64_embedded_ipv4": nat64_v4,
        }

    if port in {500, 4500}:
        is_isp = role == "INDIAN_ISP_SUBSCRIBER"
        return {
            "ip_company": company,
            "service_category": "VPN_PROXY_ANONYMIZER" if not is_isp else "VOIP_SOCIAL_CALLING",
            "application_name": (
                f"IPSec / IKEv2 VPN Tunnel (Port {port})"
                if not is_isp
                else f"VoWiFi / IPSec ePDG Tunnel (Port {port})"
            ),
            "forensic_significance": (
                "HIGH - IPSec / IKEv2 Encrypted VPN Tunnel"
                if not is_isp
                else "MEDIUM - Carrier VoWiFi / IPSec Signaling"
            ),
            "nat64_embedded_ipv4": nat64_v4,
        }

    if role == "VPN_PROVIDER":
        if port in {6881, 6882, 6883, 6884, 6885, 6886, 6887, 6888, 6889, 51413} or src_port in {6881, 6882, 51413}:
            app_label = f"VPN + P2P / BitTorrent Traffic ({company}, Port {port or 'N/A'})"
        else:
            app_label = f"Commercial VPN Session ({company}, Port {port or 'N/A'})"
        return {
            "ip_company": company,
            "service_category": "VPN_PROXY_ANONYMIZER",
            "application_name": app_label,
            "forensic_significance": "HIGH - Commercial Privacy VPN Server Connection",
            "nat64_embedded_ipv4": nat64_v4,
        }

    # 2. Meta Platforms (WhatsApp / Facebook / Instagram)
    if role == "META_SOCIAL_VOIP":
        if port in {5222, 5223, 4244, 5242, 5228}:
            return {
                "ip_company": company,
                "service_category": "VOIP_SOCIAL_CALLING",
                "application_name": f"WhatsApp Messaging & Call Signaling (Port {port})",
                "forensic_significance": "HIGH - WhatsApp Active Chat / Call Setup Channel",
                "nat64_embedded_ipv4": nat64_v4,
            }
        if port in {3478, 3479, 50318, 59234} or (port is not None and port >= 1024 and port not in {8080, 8443}):
            return {
                "ip_company": company,
                "service_category": "VOIP_SOCIAL_CALLING",
                "application_name": f"WhatsApp Voice / Video Call Relay (Port {port})",
                "forensic_significance": "HIGH - WhatsApp Voice/Video Call Media Relay (STUN/TURN)",
                "nat64_embedded_ipv4": nat64_v4,
            }
        return {
            "ip_company": company,
            "service_category": "SOCIAL_MESSAGING_MEDIA",
            "application_name": f"WhatsApp / Instagram / Facebook HTTPS & Media (Port {port or 443})",
            "forensic_significance": "MEDIUM - Meta Social Media / WhatsApp Media Transfer",
            "nat64_embedded_ipv4": nat64_v4,
        }

    # 3. Telegram Messenger
    if role == "TELEGRAM_VOIP_CHAT":
        if port in {1400, 3478, 596, 597, 598, 599} or (port is not None and port >= 10000):
            return {
                "ip_company": company,
                "service_category": "VOIP_SOCIAL_CALLING",
                "application_name": f"Telegram Voice / Video Call (Port {port})",
                "forensic_significance": "HIGH - Telegram Encrypted VoIP Call Relay",
                "nat64_embedded_ipv4": nat64_v4,
            }
        return {
            "ip_company": company,
            "service_category": "SOCIAL_MESSAGING_MEDIA",
            "application_name": f"Telegram Messenger MTProto Chat/Media (Port {port or 443})",
            "forensic_significance": "HIGH - Telegram Encrypted Chat / Bot / Media Session",
            "nat64_embedded_ipv4": nat64_v4,
        }

    # 4. Zangi / Hetzner VoIP Clusters
    if role == "ZANGI_OR_VPS":
        if port in {5222, 5223, 3478, 5060, 5061} or (port is not None and port >= 10000):
            return {
                "ip_company": company,
                "service_category": "VOIP_SOCIAL_CALLING",
                "application_name": f"Zangi Messenger / Encrypted VoIP Call (Port {port})",
                "forensic_significance": "HIGH - Suspected Zangi / Encrypted VoIP Calling",
                "nat64_embedded_ipv4": nat64_v4,
            }
        return {
            "ip_company": company,
            "service_category": "VPN_PROXY_ANONYMIZER",
            "application_name": f"Hetzner Cloud VPS / Custom VPN or Zangi TLS (Port {port or 443})",
            "forensic_significance": "HIGH - Foreign VPS / Zangi Infrastructure",
            "nat64_embedded_ipv4": nat64_v4,
        }

    # 5. Indian Telecom Subscriber IP -> P2P Social Media / VoIP Call (Arbiter Pattern!)
    if role == "INDIAN_ISP_SUBSCRIBER":
        if port is not None and port not in {80, 443, 53, 123, 8080}:
            return {
                "ip_company": company,
                "service_category": "P2P_SUBSCRIBER_CALL",
                "application_name": f"Direct P2P Social/VoIP Call (WhatsApp/Signal/Telegram/Zangi Peer on Port {port})",
                "forensic_significance": (
                    f"HIGH - Suspected B-Party Subscriber IP on {company}; "
                    "Eligible for Reverse-IPDR Lookup to identify B-Party MSISDN"
                ),
                "nat64_embedded_ipv4": nat64_v4,
            }
        return {
            "ip_company": company,
            "service_category": "CLOUD_CDN_WEB",
            "application_name": f"ISP Hosted Service / CDN ({company}, Port {port or 443})",
            "forensic_significance": "LOW - Standard ISP Web/DNS Service",
            "nat64_embedded_ipv4": nat64_v4,
        }

    # 6. Apple FaceTime / iMessage
    if role == "APPLE_SERVICES":
        if port in {5223, 2195, 2196}:
            return {
                "ip_company": company,
                "service_category": "PUSH_NOTIFICATION",
                "application_name": f"Apple APNs Push / iMessage / FaceTime Ring (Port {port})",
                "forensic_significance": "MEDIUM - Apple Push Notification / Call Alert",
                "nat64_embedded_ipv4": nat64_v4,
            }
        if port is not None and (3478 <= port <= 3497 or 16384 <= port <= 16402):
            return {
                "ip_company": company,
                "service_category": "VOIP_SOCIAL_CALLING",
                "application_name": f"Apple FaceTime Voice / Video Call (Port {port})",
                "forensic_significance": "HIGH - Apple FaceTime Encrypted Call",
                "nat64_embedded_ipv4": nat64_v4,
            }

    # 7. Google Services (FCM Push / Meet / Duo / YouTube / DNS / NTP)
    if role == "GOOGLE_CLOUD_APP":
        if port in {5228, 5229, 5230}:
            return {
                "ip_company": company,
                "service_category": "PUSH_NOTIFICATION",
                "application_name": f"Google FCM Push Notification / App Wake-up (Port {port})",
                "forensic_significance": "MEDIUM - Android Push Notification (Incoming Call/Message Trigger)",
                "nat64_embedded_ipv4": nat64_v4,
            }
        if port is not None and (19302 <= port <= 19309 or port == 3478):
            return {
                "ip_company": company,
                "service_category": "VOIP_SOCIAL_CALLING",
                "application_name": f"Google Meet / Duo / WebRTC VoIP Call (Port {port})",
                "forensic_significance": "HIGH - Google Meet / WebRTC Voice-Video Call",
                "nat64_embedded_ipv4": nat64_v4,
            }
        if port == 123:
            return {
                "ip_company": company,
                "service_category": "SYSTEM_TIME_DNS",
                "application_name": "Google Public NTP Time Synchronization (Port 123)",
                "forensic_significance": "LOW - Handset Clock Sync",
                "nat64_embedded_ipv4": nat64_v4,
            }

    # 8. Generic Port-Based VoIP / Messaging / System Detection (Signal, Zangi, SIP, STUN, etc.)
    if port in {3478, 3479, 5349, 10000, 4433}:
        return {
            "ip_company": company,
            "service_category": "VOIP_SOCIAL_CALLING",
            "application_name": f"Signal / WhatsApp / Zangi WebRTC VoIP Call (STUN/TURN Port {port})",
            "forensic_significance": "HIGH - Encrypted VoIP Call Relay (STUN/TURN Media)",
            "nat64_embedded_ipv4": nat64_v4,
        }

    if port in {5222, 5223}:
        return {
            "ip_company": company,
            "service_category": "VOIP_SOCIAL_CALLING",
            "application_name": f"WhatsApp / Zangi / XMPP Messaging & Call Signaling (Port {port})",
            "forensic_significance": "HIGH - Instant Messaging / VoIP Call Signaling",
            "nat64_embedded_ipv4": nat64_v4,
        }

    if port in {5060, 5061}:
        return {
            "ip_company": company,
            "service_category": "VOIP_SOCIAL_CALLING",
            "application_name": f"SIP VoIP Internet Calling (Port {port})",
            "forensic_significance": "HIGH - SIP Voice Call Signaling",
            "nat64_embedded_ipv4": nat64_v4,
        }

    if port in {5228, 5229, 5230}:
        return {
            "ip_company": company,
            "service_category": "PUSH_NOTIFICATION",
            "application_name": f"Android FCM Push Notification Channel (Port {port})",
            "forensic_significance": "MEDIUM - Background Push Notification",
            "nat64_embedded_ipv4": nat64_v4,
        }

    if port in {6881, 6882, 6883, 6884, 6885, 6886, 6887, 6888, 6889, 51413} or src_port in {6881, 6882, 51413}:
        return {
            "ip_company": company,
            "service_category": "P2P_FILE_SHARING",
            "application_name": f"BitTorrent / P2P Peer Connection (Port {port or src_port})",
            "forensic_significance": "MEDIUM - P2P / BitTorrent Traffic",
            "nat64_embedded_ipv4": nat64_v4,
        }

    if port == 22:
        return {
            "ip_company": company,
            "service_category": "VPN_PROXY_ANONYMIZER",
            "application_name": "SSH Remote Shell / Encrypted Tunnel (Port 22)",
            "forensic_significance": "HIGH - Remote Server Access / SSH Tunnel",
            "nat64_embedded_ipv4": nat64_v4,
        }

    if port in {53, 853}:
        return {
            "ip_company": company,
            "service_category": "SYSTEM_TIME_DNS",
            "application_name": f"DNS / DNS-over-TLS Query (Port {port})",
            "forensic_significance": "LOW - Domain Name Resolution",
            "nat64_embedded_ipv4": nat64_v4,
        }

    if port == 123:
        return {
            "ip_company": company,
            "service_category": "SYSTEM_TIME_DNS",
            "application_name": f"NTP Time Sync ({company}, Port 123)",
            "forensic_significance": "LOW - Network Time Sync",
            "nat64_embedded_ipv4": nat64_v4,
        }

    if role == "VPS_HOSTING":
        return {
            "ip_company": company,
            "service_category": "VPN_PROXY_ANONYMIZER",
            "application_name": f"VPS Hosted Service / Custom VPN or Proxy ({company}, Port {port or 443})",
            "forensic_significance": "HIGH - Dedicated VPS Connection (Verify for Custom VPN / Proxy / C2)",
            "nat64_embedded_ipv4": nat64_v4,
        }

    if port in {443, 8443}:
        return {
            "ip_company": company,
            "service_category": "CLOUD_CDN_WEB",
            "application_name": f"HTTPS / QUIC Encrypted App or Web ({company}, Port {port})",
            "forensic_significance": "LOW - Encrypted HTTPS / App Traffic",
            "nat64_embedded_ipv4": nat64_v4,
        }

    if port in {80, 8080}:
        return {
            "ip_company": company,
            "service_category": "CLOUD_CDN_WEB",
            "application_name": f"HTTP Web / App Traffic ({company}, Port {port})",
            "forensic_significance": "LOW - Standard HTTP Traffic",
            "nat64_embedded_ipv4": nat64_v4,
        }

    if port is not None and port >= 1024:
        return {
            "ip_company": company,
            "service_category": "OTHER_NETWORK_SERVICE",
            "application_name": f"Custom / P2P / High-Port Session ({company}, Port {port})",
            "forensic_significance": "MEDIUM - Non-standard High Port (Verify for VoIP / Tunnel / P2P)",
            "nat64_embedded_ipv4": nat64_v4,
        }

    return {
        "ip_company": company,
        "service_category": "OTHER_NETWORK_SERVICE",
        "application_name": f"Network Session ({company}, Port {port if port is not None else 'N/A'})",
        "forensic_significance": "LOW - General Network Activity",
        "nat64_embedded_ipv4": nat64_v4,
    }


def format_duration_hms(seconds_value: Any) -> str:
    """Format seconds into readable Xh Ym Zs string."""
    try:
        total = int(round(float(seconds_value or 0)))
    except (TypeError, ValueError):
        total = 0
    if total <= 0:
        return "0s"
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def _deduplicated_session_duration(group: pd.DataFrame) -> int:
    """Compute realistic active duration without double-counting repeated session rows."""
    if group.empty:
        return 0
    dur_col = (
        "session_duration_seconds"
        if "session_duration_seconds" in group.columns
        else "event_duration_seconds"
        if "event_duration_seconds" in group.columns
        else None
    )
    if dur_col is None:
        return 0

    work = group.copy()
    work["_dur"] = pd.to_numeric(work[dur_col], errors="coerce").fillna(0).clip(lower=0)

    # In Airtel/Jio IPDR, multiple event rows inside the same allocation/session
    # repeat the total session duration. Deduplicate by allocation_key + session_start if present.
    if "allocation_key" in work.columns and work["allocation_key"].astype("object").fillna("").astype(str).str.strip().ne("").any():
        dedup_Dur = work.groupby("allocation_key", dropna=False)["_dur"].max().sum()
        return int(round(float(dedup_Dur)))

    return int(round(float(work["_dur"].sum())))


def annotate_ipdr_with_intelligence(data: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of normalized IPDR DataFrame with IP/Port intelligence columns."""
    if not isinstance(data, pd.DataFrame) or data.empty:
        out = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame()
        for col in (
            "ip_company",
            "service_category",
            "application_name",
            "forensic_significance",
            "nat64_embedded_ipv4",
        ):
            if col not in out.columns:
                out[col] = pd.Series(dtype="string")
        return out

    out = data.copy()
    dest_ips = (
        out["destination_ip"].astype("object").fillna("").astype(str).str.strip()
        if "destination_ip" in out.columns
        else pd.Series("", index=out.index, dtype="string")
    )
    dest_ports = (
        out["destination_port"]
        if "destination_port" in out.columns
        else pd.Series(pd.NA, index=out.index)
    )
    src_ports = (
        out["source_port"]
        if "source_port" in out.columns
        else pd.Series(pd.NA, index=out.index)
    )

    classifications = [
        classify_ip_and_port(ip, dp, sp)
        for ip, dp, sp in zip(dest_ips, dest_ports, src_ports)
    ]
    intel_df = pd.DataFrame(classifications, index=out.index)
    for col in (
        "ip_company",
        "service_category",
        "application_name",
        "forensic_significance",
        "nat64_embedded_ipv4",
    ):
        out[col] = intel_df[col]
    return out


def build_application_usage_summary(data: pd.DataFrame) -> pd.DataFrame:
    """Summarize which subscriber used which Application/Website/VPN and for how long."""
    columns = [
        "subscriber_number",
        "application_name",
        "ip_company",
        "service_category",
        "forensic_significance",
        "events",
        "unique_sessions",
        "estimated_duration_seconds",
        "readable_duration",
        "activity_span_seconds",
        "readable_activity_span",
        "first_used",
        "last_used",
        "unique_destination_ips",
        "destination_ports",
        "sample_destination_ips",
    ]
    if not isinstance(data, pd.DataFrame) or data.empty:
        return pd.DataFrame(columns=columns)

    work = annotate_ipdr_with_intelligence(data)
    work = work[work["destination_ip"].astype("object").fillna("").astype(str).str.strip().ne("")].copy()
    if work.empty:
        return pd.DataFrame(columns=columns)

    work["_sub"] = work.get("subscriber_number", pd.Series("", index=work.index)).astype("object").fillna("").astype(str).str.strip()
    work["_sub"] = work["_sub"].replace("", "UNKNOWN_SUBSCRIBER")
    work["_port_str"] = (
        pd.to_numeric(work.get("destination_port"), errors="coerce")
        .astype("Int64")
        .astype(str)
        .replace("<NA>", "")
    )
    work["_time"] = pd.to_datetime(work.get("event_time"), errors="coerce")
    if "session_start" in work.columns:
        work["_time"] = work["_time"].fillna(pd.to_datetime(work["session_start"], errors="coerce"))

    rows: list[dict[str, Any]] = []
    grouped = work.groupby(
        ["_sub", "application_name", "ip_company", "service_category", "forensic_significance"],
        dropna=False,
        sort=False,
    )
    for (sub, app_name, company, cat, sig), grp in grouped:
        first_seen = grp["_time"].min()
        last_seen = grp["_time"].max()
        span_sec = (
            int((last_seen - first_seen).total_seconds())
            if pd.notna(first_seen) and pd.notna(last_seen) and last_seen >= first_seen
            else 0
        )
        est_dur = _deduplicated_session_duration(grp)
        if est_dur == 0 and span_sec > 0:
            est_dur = span_sec

        ports_used = ", ".join(sorted({p for p in grp["_port_str"] if p})[:10])
        sample_ips = ", ".join(sorted({ip for ip in grp["destination_ip"].astype(str) if ip})[:5])
        sess_count = (
            grp["allocation_key"].nunique()
            if "allocation_key" in grp.columns
            else len(grp)
        )

        rows.append(
            {
                "subscriber_number": sub,
                "application_name": app_name,
                "ip_company": company,
                "service_category": cat,
                "forensic_significance": sig,
                "events": len(grp),
                "unique_sessions": int(sess_count),
                "estimated_duration_seconds": est_dur,
                "readable_duration": format_duration_hms(est_dur),
                "activity_span_seconds": span_sec,
                "readable_activity_span": format_duration_hms(span_sec),
                "first_used": first_seen,
                "last_used": last_seen,
                "unique_destination_ips": grp["destination_ip"].nunique(),
                "destination_ports": ports_used,
                "sample_destination_ips": sample_ips,
            }
        )

    result = pd.DataFrame(rows, columns=columns)
    priority_order = {
        "VPN_PROXY_ANONYMIZER": 1,
        "P2P_SUBSCRIBER_CALL": 2,
        "VOIP_SOCIAL_CALLING": 3,
        "SOCIAL_MESSAGING_MEDIA": 4,
        "PUSH_NOTIFICATION": 5,
        "P2P_FILE_SHARING": 6,
        "OTHER_NETWORK_SERVICE": 7,
        "CLOUD_CDN_WEB": 8,
        "SYSTEM_TIME_DNS": 9,
    }
    result["_prio"] = result["service_category"].map(lambda c: priority_order.get(str(c), 99))
    result = (
        result.sort_values(
            ["_prio", "events", "estimated_duration_seconds"],
            ascending=[True, False, False],
        )
        .drop(columns=["_prio"])
        .reset_index(drop=True)
    )
    return result


def build_voip_vpn_highlights(app_summary: pd.DataFrame) -> pd.DataFrame:
    """Filter high-priority VoIP calling, P2P subscriber calling, and VPN/Proxy usage."""
    if not isinstance(app_summary, pd.DataFrame) or app_summary.empty:
        return pd.DataFrame(columns=app_summary.columns if isinstance(app_summary, pd.DataFrame) else [])
    high_categories = {
        "VPN_PROXY_ANONYMIZER",
        "P2P_SUBSCRIBER_CALL",
        "VOIP_SOCIAL_CALLING",
        "SOCIAL_MESSAGING_MEDIA",
    }
    return (
        app_summary[app_summary["service_category"].isin(high_categories)]
        .copy()
        .reset_index(drop=True)
    )


def build_p2p_social_calling_leads(data: pd.DataFrame) -> pd.DataFrame:
    """Build Arbiter-style 'IMPORTANT IP SOCIAL CALLING' & Reverse-IPDR leads table."""
    columns = [
        "A Party",
        "Destination Ip",
        "Destination Port",
        "Destination ISP",
        "Detected Application",
        "Date",
        "Time",
        "End Date",
        "End Time",
        "Events",
        "Duration (Sec)",
        "Readable Duration",
        "Reverse IPDR Action",
    ]
    if not isinstance(data, pd.DataFrame) or data.empty:
        return pd.DataFrame(columns=columns)

    work = annotate_ipdr_with_intelligence(data)
    mask = work["service_category"].isin(
        {"P2P_SUBSCRIBER_CALL", "VOIP_SOCIAL_CALLING", "VPN_PROXY_ANONYMIZER"}
    )
    work = work[mask].copy()
    if work.empty:
        return pd.DataFrame(columns=columns)

    work["_a_party"] = (
        work.get("subscriber_number", pd.Series("", index=work.index))
        .astype("object").fillna("").astype(str)
        .str.strip()
    )
    work["_dest_ip"] = work["destination_ip"].astype("object").fillna("").astype(str).str.strip()
    work["_dest_port"] = (
        pd.to_numeric(work.get("destination_port"), errors="coerce")
        .astype("Int64")
        .astype(str)
        .replace("<NA>", "")
    )
    work["_start"] = pd.to_datetime(work.get("event_time"), errors="coerce")
    if "session_start" in work.columns:
        work["_start"] = work["_start"].fillna(pd.to_datetime(work["session_start"], errors="coerce"))
    work["_end"] = (
        pd.to_datetime(work["session_end"], errors="coerce")
        if "session_end" in work.columns
        else pd.Series(pd.NaT, index=work.index)
    )
    if "allocation_end" in work.columns:
        work["_end"] = work["_end"].fillna(pd.to_datetime(work["allocation_end"], errors="coerce"))
    work["_end"] = work["_end"].fillna(work["_start"])

    rows: list[dict[str, Any]] = []
    grouped = work.groupby(
        ["_a_party", "_dest_ip", "_dest_port", "ip_company", "application_name", "service_category"],
        dropna=False,
        sort=False,
    )
    for (a_party, dip, dport, isp, app_name, cat), grp in grouped:
        min_start = grp["_start"].min()
        max_end = grp["_end"].max()
        if pd.notna(min_start) and pd.notna(max_end) and max_end < min_start:
            max_end = min_start

        est_dur = _deduplicated_session_duration(grp)
        if est_dur == 0 and pd.notna(min_start) and pd.notna(max_end):
            est_dur = int(max(0, (max_end - min_start).total_seconds()))

        action = (
            f"Send Reverse-IPDR Request to {isp} for IP {dip} + Port {dport} to identify B-Party MSISDN"
            if cat == "P2P_SUBSCRIBER_CALL"
            else "Verify VoIP / VPN Server Session"
        )
        rows.append(
            {
                "A Party": a_party,
                "Destination Ip": dip,
                "Destination Port": dport,
                "Destination ISP": isp,
                "Detected Application": app_name,
                "Date": min_start.strftime("%Y-%m-%d") if pd.notna(min_start) else "",
                "Time": min_start.strftime("%H:%M:%S") if pd.notna(min_start) else "",
                "End Date": max_end.strftime("%Y-%m-%d") if pd.notna(max_end) else "",
                "End Time": max_end.strftime("%H:%M:%S") if pd.notna(max_end) else "",
                "Events": len(grp),
                "Duration (Sec)": est_dur,
                "Readable Duration": format_duration_hms(est_dur),
                "Reverse IPDR Action": action,
            }
        )

    result = pd.DataFrame(rows, columns=columns)
    return result.sort_values(
        ["Events", "Duration (Sec)", "Date", "Time"],
        ascending=[False, False, True, True],
        ignore_index=True,
    )


def build_ipdr_specialized_sheets(
    data: pd.DataFrame,
    *,
    partition_parts: list[dict[str, Any]] | None = None,
) -> dict[str, pd.DataFrame]:
    """Build IPv4, IPv6, Airtel, Jio, Vi, BSNL, Others & Session Same-Time Co-Activity sheets."""
    import numpy as np

    coactivity_cols = [
        "Subscriber No.",
        "Operator",
        "IP Version",
        "Destination IP",
        "Destination Port",
        "IP Company",
        "Application",
        "Session From",
        "Session To",
        "Part",
        "Same Time Apps",
        "Same Time Companies",
    ]
    if not isinstance(data, pd.DataFrame) or data.empty:
        empty = pd.DataFrame(columns=coactivity_cols)
        return {
            "session_coactivity": empty,
            "ipv4_sessions": empty.copy(),
            "ipv6_sessions": empty.copy(),
            "airtel_ips": empty.copy(),
            "jio_ips": empty.copy(),
            "vi_ips": empty.copy(),
            "bsnl_ips": empty.copy(),
            "other_company_ips": empty.copy(),
        }

    work = annotate_ipdr_with_intelligence(data)

    sub_series = (
        work["subscriber_number"].astype("object").fillna("").astype(str).str.strip()
        if "subscriber_number" in work.columns
        else pd.Series("", index=work.index, dtype="object")
    )
    op_series = (
        work["operator"].astype("object").fillna("").astype(str).str.strip()
        if "operator" in work.columns
        else pd.Series("", index=work.index, dtype="object")
    )
    src_ip = (
        work["source_ip"].astype("object").fillna("").astype(str).str.strip()
        if "source_ip" in work.columns
        else pd.Series("", index=work.index, dtype="object")
    )
    dst_ip = (
        work["destination_ip"].astype("object").fillna("").astype(str).str.strip()
        if "destination_ip" in work.columns
        else pd.Series("", index=work.index, dtype="object")
    )

    dst_ver = (
        work["destination_ip_version"].astype("object").fillna("").astype(str).str.strip()
        if "destination_ip_version" in work.columns
        else pd.Series("", index=work.index, dtype="object")
    )
    src_ver = (
        work["source_ip_version"].astype("object").fillna("").astype(str).str.strip()
        if "source_ip_version" in work.columns
        else pd.Series("", index=work.index, dtype="object")
    )
    ip_ver = dst_ver.where(dst_ver.isin(["IPv4", "IPv6"]), src_ver)
    inferred_v6 = dst_ip.str.contains(":", regex=False) | (
        dst_ip.eq("") & src_ip.str.contains(":", regex=False)
    )
    inferred_v4 = dst_ip.str.contains(".", regex=False) | (
        dst_ip.eq("") & src_ip.str.contains(".", regex=False)
    )
    ip_ver = pd.Series(
        np.where(
            ip_ver.isin(["IPv4", "IPv6"]),
            ip_ver,
            np.where(inferred_v6, "IPv6", np.where(inferred_v4, "IPv4", "")),
        ),
        index=work.index,
        dtype="object",
    )

    if "destination_port" in work.columns:
        dport_num = pd.to_numeric(work["destination_port"].astype("object"), errors="coerce")
        dport_str = dport_num.astype("Int64").astype(str).replace({"<NA>": "", "nan": ""})
    else:
        dport_str = pd.Series("", index=work.index, dtype="object")

    company_series = (
        work["ip_company"].astype("object").fillna("").astype(str).str.strip()
        if "ip_company" in work.columns
        else pd.Series("", index=work.index, dtype="object")
    )
    app_series = (
        work["application_name"].astype("object").fillna("").astype(str).str.strip()
        if "application_name" in work.columns
        else pd.Series("", index=work.index, dtype="object")
    )

    evt_ts = (
        pd.to_datetime(work["event_time"], errors="coerce")
        if "event_time" in work.columns
        else pd.Series(pd.NaT, index=work.index)
    )
    sess_start = (
        pd.to_datetime(work["session_start"], errors="coerce")
        if "session_start" in work.columns
        else pd.Series(pd.NaT, index=work.index)
    )
    alloc_start = (
        pd.to_datetime(work["allocation_start"], errors="coerce")
        if "allocation_start" in work.columns
        else pd.Series(pd.NaT, index=work.index)
    )
    session_from = sess_start.fillna(evt_ts).fillna(alloc_start)

    sess_end = (
        pd.to_datetime(work["session_end"], errors="coerce")
        if "session_end" in work.columns
        else pd.Series(pd.NaT, index=work.index)
    )
    alloc_end = (
        pd.to_datetime(work["allocation_end"], errors="coerce")
        if "allocation_end" in work.columns
        else pd.Series(pd.NaT, index=work.index)
    )
    session_to = sess_end.fillna(alloc_end).fillna(session_from)

    # Part detection (for Tower IPDR Part-wise analysis or Spot-wise dumps)
    if "partition_id" in work.columns:
        part_series = work["partition_id"].astype("object").fillna("").astype(str).str.strip()
        if "partition_location" in work.columns:
            loc_s = work["partition_location"].astype("object").fillna("").astype(str).str.strip()
            part_series = pd.Series(
                np.where(
                    part_series.ne("") & loc_s.ne(""),
                    part_series + " (" + loc_s + ")",
                    part_series,
                ),
                index=work.index,
                dtype="object",
            )
    elif "part_name" in work.columns:
        part_series = work["part_name"].astype("object").fillna("").astype(str).str.strip()
    else:
        part_series = pd.Series("", index=work.index, dtype="object")

    if partition_parts and part_series.eq("").all():
        matched_parts = pd.Series("", index=work.index, dtype="object")
        for idx_p, p in enumerate(partition_parts, start=1):
            if not isinstance(p, dict):
                continue
            p_label = str(
                p.get("part_name")
                or p.get("partition_id")
                or p.get("sighting_id")
                or f"P{idx_p}"
            ).strip()
            w_start = pd.to_datetime(
                p.get("start_time") or p.get("window_start"), errors="coerce"
            )
            w_end = pd.to_datetime(
                p.get("end_time") or p.get("window_end"), errors="coerce"
            )
            p_spot = str(p.get("spot_id") or "").strip()
            if pd.notna(w_start) and pd.notna(w_end):
                t_mask = (session_from <= w_end) & (session_to >= w_start)
                if (
                    p_spot
                    and p_spot not in {"ALL_SPOTS", "LEGACY_ALL_SPOTS"}
                    and "spot_id" in work.columns
                ):
                    s_mask = (
                        work["spot_id"]
                        .astype("object")
                        .fillna("")
                        .astype(str)
                        .str.strip()
                        .eq(p_spot)
                    )
                    t_mask = t_mask & s_mask
                matched_parts = pd.Series(
                    np.where(
                        t_mask & (matched_parts == ""),
                        p_label,
                        np.where(
                            t_mask & (matched_parts != ""),
                            matched_parts + ", " + p_label,
                            matched_parts,
                        ),
                    ),
                    index=work.index,
                    dtype="object",
                )
        part_series = matched_parts

    if "spot_id" in work.columns:
        spot_vals = work["spot_id"].astype("object").fillna("").astype(str).str.strip()
        spot_vals = spot_vals.replace("UNASSIGNED-ROOT", "")
        part_series = part_series.where(part_series.ne(""), spot_vals)

    part_series = part_series.replace("", "Full Dump")

    # Compute Same Time Apps & Same Time Companies per subscriber in 5-min window / session
    time_bucket = session_from.dt.floor("5min").astype(str).replace("NaT", "")
    alloc_key = (
        work["allocation_key"].astype("object").fillna("").astype(str).str.strip()
        if "allocation_key" in work.columns
        else pd.Series("", index=work.index, dtype="object")
    )
    co_group_key = sub_series + "|" + pd.Series(
        np.where(time_bucket != "", time_bucket, alloc_key),
        index=work.index,
        dtype="object",
    )

    temp_co = pd.DataFrame(
        {
            "_g": co_group_key,
            "_app": app_series,
            "_comp": company_series,
        },
        index=work.index,
    )

    def _unique_join(vals: pd.Series, max_items: int = 8) -> str:
        seen: list[str] = []
        for v in vals:
            if v and v not in seen:
                seen.append(v)
            if len(seen) >= max_items:
                break
        return " | ".join(seen)

    grouped_co = temp_co.groupby("_g", sort=False).agg(
        same_apps=("_app", _unique_join),
        same_comps=("_comp", _unique_join),
    )
    same_time_apps = co_group_key.map(grouped_co["same_apps"]).fillna("")
    same_time_comps = co_group_key.map(grouped_co["same_comps"]).fillna("")

    coactivity_df = pd.DataFrame(
        {
            "Subscriber No.": sub_series,
            "Operator": op_series,
            "IP Version": ip_ver,
            "Destination IP": dst_ip,
            "Destination Port": dport_str,
            "IP Company": company_series,
            "Application": app_series,
            "Session From": session_from,
            "Session To": session_to,
            "Part": part_series,
            "Same Time Apps": same_time_apps,
            "Same Time Companies": same_time_comps,
        },
        index=work.index,
    )

    # Deduplicate identical consecutive session rows to keep the sheet compact and fast
    coactivity_df = (
        coactivity_df.drop_duplicates(
            subset=[
                "Subscriber No.",
                "Operator",
                "IP Version",
                "Destination IP",
                "Destination Port",
                "Application",
                "Session From",
                "Session To",
                "Part",
            ]
        )
        .sort_values(
            ["Session From", "Subscriber No."],
            ascending=[True, True],
            na_position="last",
            ignore_index=True,
        )
    )

    ipv4_df = coactivity_df[coactivity_df["IP Version"].eq("IPv4")].reset_index(drop=True)
    ipv6_df = coactivity_df[coactivity_df["IP Version"].eq("IPv6")].reset_index(drop=True)

    comp_lower = coactivity_df["IP Company"].astype(str).str.lower()
    is_airtel = comp_lower.str.contains("airtel|bharti", regex=True, na=False)
    is_jio = comp_lower.str.contains("jio|reliance", regex=True, na=False)
    is_vi = comp_lower.str.contains(r"vodafone|idea|vi|vil", regex=True, na=False)
    is_bsnl = comp_lower.str.contains("bsnl|bharat sanchar|mtnl", regex=True, na=False)
    is_others = ~(is_airtel | is_jio | is_vi | is_bsnl) & coactivity_df["Destination IP"].ne("")

    return {
        "session_coactivity": coactivity_df,
        "ipv4_sessions": ipv4_df,
        "ipv6_sessions": ipv6_df,
        "airtel_ips": coactivity_df[is_airtel].reset_index(drop=True),
        "jio_ips": coactivity_df[is_jio].reset_index(drop=True),
        "vi_ips": coactivity_df[is_vi].reset_index(drop=True),
        "bsnl_ips": coactivity_df[is_bsnl].reset_index(drop=True),
        "other_company_ips": coactivity_df[is_others].reset_index(drop=True),
    }
