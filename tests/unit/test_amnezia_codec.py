import pytest
from src.app.utils.amnezia_codec import encode_vpn_url, decode_vpn_url, q_compress, q_uncompress


def test_amnezia_codec_roundtrip():
    original_conf = (
        "[Interface]\n"
        "Address = 10.8.1.2/32\n"
        "PrivateKey = aW5pdGlhbF9wcml2YXRlX2tleV9mb3JfdGVzdGluZzEy\n"
        "DNS = 1.1.1.1, 8.8.8.8\n"
        "Jc = 6\n"
        "Jmin = 10\n"
        "Jmax = 50\n"
        "S1 = 142\n"
        "S2 = 17\n"
        "S3 = 34\n"
        "S4 = 13\n"
        "H1 = 1196015809-1347332553\n"
        "H2 = 2001085790-2132310278\n"
        "H3 = 2138797701-2138904917\n"
        "H4 = 2139548831-2142765526\n"
        "I1 = <r 2><b 0x858000010001000000000669636c6f756403636f6d0000010001c00c000100010000105a00044d583737>\n\n"
        "[Peer]\n"
        "PublicKey = c2VydmVyX3B1YmxpY19rZXlfZm9yX3Rlc3RpbmcxMjM=\n"
        "PresharedKey = cHJlc2hhcmVkX2tleV9mb3JfdGVzdGluZ19wdXJwb3Nlcw==\n"
        "Endpoint = 103.83.86.253:36466\n"
        "AllowedIPs = 0.0.0.0/0, ::/0\n"
        "PersistentKeepalive = 25\n"
    )

    vpn_url = encode_vpn_url(original_conf)
    assert vpn_url.startswith("vpn://")
    assert len(vpn_url) > 10

    decoded_conf = decode_vpn_url(vpn_url)
    assert decoded_conf == original_conf


def test_invalid_vpn_url():
    assert decode_vpn_url("invalid_url") is None
    assert decode_vpn_url("vpn://invalid!!base64") is None
