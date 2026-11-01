import hashlib
import hmac

P = 2**256 - 2**32 - 977
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
     0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BECH = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

VERSIONS = {
    bytes.fromhex("0488b21e"): "p2pkh",
    bytes.fromhex("019da462"): "p2pkh",
    bytes.fromhex("049d7cb2"): "p2sh-p2wpkh",
    bytes.fromhex("01b26ef6"): "p2sh-p2wpkh",
    bytes.fromhex("04b24746"): "p2wpkh",
}
COINS = {
    "btc": {"p2pkh": 0x00, "p2sh": 0x05, "hrp": "bc"},
    "ltc": {"p2pkh": 0x30, "p2sh": 0x32, "hrp": "ltc"},
}


class WalletError(ValueError):
    pass


def _ripemd160(data: bytes) -> bytes:
    try:
        return hashlib.new("ripemd160", data).digest()
    except (ValueError, TypeError):
        return _ripemd160_py(data)


def _ripemd160_py(message: bytes) -> bytes:
    def rol(x, n):
        return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF

    r1 = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 7, 4, 13, 1, 10, 6, 15, 3, 12, 0, 9, 5, 2, 14, 11, 8,
          3, 10, 14, 4, 9, 15, 8, 1, 2, 7, 0, 6, 13, 11, 5, 12, 1, 9, 11, 10, 0, 8, 12, 4, 13, 3, 7, 15, 14, 5, 6, 2,
          4, 0, 5, 9, 7, 12, 2, 10, 14, 1, 3, 8, 11, 6, 15, 13]
    r2 = [5, 14, 7, 0, 9, 2, 11, 4, 13, 6, 15, 8, 1, 10, 3, 12, 6, 11, 3, 7, 0, 13, 5, 10, 14, 15, 8, 12, 4, 9, 1, 2,
          15, 5, 1, 3, 7, 14, 6, 9, 11, 8, 12, 2, 10, 0, 4, 13, 8, 6, 4, 1, 3, 11, 15, 0, 5, 12, 2, 13, 9, 7, 10, 14,
          12, 15, 10, 4, 1, 5, 8, 7, 6, 2, 13, 14, 0, 3, 9, 11]
    s1 = [11, 14, 15, 12, 5, 8, 7, 9, 11, 13, 14, 15, 6, 7, 9, 8, 7, 6, 8, 13, 11, 9, 7, 15, 7, 12, 15, 9, 11, 7, 13, 12,
          11, 13, 6, 7, 14, 9, 13, 15, 14, 8, 13, 6, 5, 12, 7, 5, 11, 12, 14, 15, 14, 15, 9, 8, 9, 14, 5, 6, 8, 6, 5, 12,
          9, 15, 5, 11, 6, 8, 13, 12, 5, 12, 13, 14, 11, 8, 5, 6]
    s2 = [8, 9, 9, 11, 13, 15, 15, 5, 7, 7, 8, 11, 14, 14, 12, 6, 9, 13, 15, 7, 12, 8, 9, 11, 7, 7, 12, 7, 6, 15, 13, 11,
          9, 7, 15, 11, 8, 6, 6, 14, 12, 13, 5, 14, 13, 13, 7, 5, 15, 5, 8, 11, 14, 14, 6, 14, 6, 9, 12, 9, 12, 5, 15, 8,
          8, 5, 12, 9, 12, 5, 14, 6, 8, 13, 6, 5, 15, 13, 11, 11]
    k1 = [0x00000000, 0x5A827999, 0x6ED9EBA1, 0x8F1BBCDC, 0xA953FD4E]
    k2 = [0x50A28BE6, 0x5C4DD124, 0x6D703EF3, 0x7A6D76E9, 0x00000000]

    def f(j, x, y, z):
        if j < 16:
            return x ^ y ^ z
        if j < 32:
            return (x & y) | (~x & 0xFFFFFFFF & z)
        if j < 48:
            return (x | (~y & 0xFFFFFFFF)) ^ z
        if j < 64:
            return (x & z) | (y & (~z & 0xFFFFFFFF))
        return x ^ (y | (~z & 0xFFFFFFFF))

    h = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0]
    length = len(message)
    message += b"\x80"
    message += b"\x00" * ((56 - len(message) % 64) % 64)
    message += (length * 8).to_bytes(8, "little")
    for offset in range(0, len(message), 64):
        x = [int.from_bytes(message[offset + 4 * i: offset + 4 * i + 4], "little") for i in range(16)]
        a1, b1, c1, d1, e1 = h
        a2, b2, c2, d2, e2 = h
        for j in range(80):
            t = (rol((a1 + f(j, b1, c1, d1) + x[r1[j]] + k1[j // 16]) & 0xFFFFFFFF, s1[j]) + e1) & 0xFFFFFFFF
            a1, e1, d1, c1, b1 = e1, d1, rol(c1, 10), b1, t
            t = (rol((a2 + f(79 - j, b2, c2, d2) + x[r2[j]] + k2[j // 16]) & 0xFFFFFFFF, s2[j]) + e2) & 0xFFFFFFFF
            a2, e2, d2, c2, b2 = e2, d2, rol(c2, 10), b2, t
        t = (h[1] + c1 + d2) & 0xFFFFFFFF
        h[1] = (h[2] + d1 + e2) & 0xFFFFFFFF
        h[2] = (h[3] + e1 + a2) & 0xFFFFFFFF
        h[3] = (h[4] + a1 + b2) & 0xFFFFFFFF
        h[4] = (h[0] + b1 + c2) & 0xFFFFFFFF
        h[0] = t
    return b"".join(v.to_bytes(4, "little") for v in h)


def hash160(data: bytes) -> bytes:
    return _ripemd160(hashlib.sha256(data).digest())


def b58decode(text: str) -> bytes:
    number = 0
    for char in text:
        if char not in B58:
            raise WalletError("That is not a valid extended public key.")
        number = number * 58 + B58.index(char)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    pad = len(text) - len(text.lstrip("1"))
    return b"\x00" * pad + raw


def b58encode(data: bytes) -> str:
    number = int.from_bytes(data, "big")
    out = ""
    while number:
        number, rest = divmod(number, 58)
        out = B58[rest] + out
    return "1" * (len(data) - len(data.lstrip(b"\x00"))) + out


def b58check_decode(text: str) -> bytes:
    raw = b58decode(text)
    if len(raw) < 5 or hashlib.sha256(hashlib.sha256(raw[:-4]).digest()).digest()[:4] != raw[-4:]:
        raise WalletError("That key has a typo: the checksum does not match.")
    return raw[:-4]


def b58check_encode(data: bytes) -> str:
    return b58encode(data + hashlib.sha256(hashlib.sha256(data).digest()).digest()[:4])


def _polymod(values):
    generator = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for value in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ value
        for i in range(5):
            chk ^= generator[i] if (top >> i) & 1 else 0
    return chk


def bech32_encode(hrp: str, version: int, program: bytes) -> str:
    acc, bits, data = 0, 0, []
    for byte in program:
        acc = (acc << 8) | byte
        bits += 8
        while bits >= 5:
            bits -= 5
            data.append((acc >> bits) & 31)
    if bits:
        data.append((acc << (5 - bits)) & 31)
    values = [version] + data
    expanded = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]
    mod = _polymod(expanded + values + [0] * 6) ^ 1
    checksum = [(mod >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(BECH[d] for d in values + checksum)


def _add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0] and (a[1] + b[1]) % P == 0:
        return None
    if a == b:
        slope = 3 * a[0] * a[0] * pow(2 * a[1], -1, P) % P
    else:
        slope = (b[1] - a[1]) * pow(b[0] - a[0], -1, P) % P
    x = (slope * slope - a[0] - b[0]) % P
    return x, (slope * (a[0] - x) - a[1]) % P


def _mul(k: int, point):
    result = None
    while k:
        if k & 1:
            result = _add(result, point)
        point = _add(point, point)
        k >>= 1
    return result


def _decompress(data: bytes):
    if len(data) != 33 or data[0] not in (2, 3):
        raise WalletError("That key is not a compressed public key.")
    x = int.from_bytes(data[1:], "big")
    y = pow((pow(x, 3, P) + 7) % P, (P + 1) // 4, P)
    if pow(y, 2, P) != (pow(x, 3, P) + 7) % P:
        raise WalletError("That key is not on the curve.")
    if (y & 1) != (data[0] & 1):
        y = P - y
    return x, y


def _compress(point) -> bytes:
    return bytes([2 + (point[1] & 1)]) + point[0].to_bytes(32, "big")


def parse_xpub(text: str) -> dict:
    raw = b58check_decode(text.strip())
    if len(raw) != 78:
        raise WalletError("That is not an extended public key.")
    version = raw[:4]
    if version not in VERSIONS:
        raise WalletError("Unsupported key. Use an xpub, ypub, zpub, Ltub or Mtub exported from your wallet. A key starting with xprv or zprv is private: do not share it.")
    key = raw[45:]
    _decompress(key)
    return {"kind": VERSIONS[version], "chain": raw[13:45], "key": key}


def _child(key: bytes, chain: bytes, index: int):
    if index >= 0x80000000:
        raise WalletError("Hardened derivation is not possible from a public key.")
    digest = hmac.new(chain, key + index.to_bytes(4, "big"), hashlib.sha512).digest()
    shift = int.from_bytes(digest[:32], "big")
    if shift >= N:
        raise WalletError("Invalid child key.")
    point = _add(_mul(shift, G), _decompress(key))
    if point is None:
        raise WalletError("Invalid child key.")
    return _compress(point), digest[32:]


def derive_pubkey(info: dict, index: int, branch: int = 0) -> bytes:
    key, chain = _child(info["key"], info["chain"], branch)
    key, _ = _child(key, chain, index)
    return key


def address_for(pubkey: bytes, kind: str, coin: str) -> str:
    params = COINS[coin]
    digest = hash160(pubkey)
    if kind == "p2wpkh":
        return bech32_encode(params["hrp"], 0, digest)
    if kind == "p2sh-p2wpkh":
        redeem = b"\x00\x14" + digest
        return b58check_encode(bytes([params["p2sh"]]) + hash160(redeem))
    return b58check_encode(bytes([params["p2pkh"]]) + digest)


def derive_address(xpub: str, coin: str, index: int, branch: int = 0) -> str:
    if coin not in COINS:
        raise WalletError("Unknown coin.")
    info = parse_xpub(xpub)
    return address_for(derive_pubkey(info, index, branch), info["kind"], coin)
