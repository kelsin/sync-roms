"""The package name and version code of an APK, read from its binary AndroidManifest.xml."""
import struct

VERSION_CODE_ID = 0x0101021B  # android:versionCode
STRING_POOL, RESOURCE_MAP, START_ELEMENT = 0x0001, 0x0180, 0x0102
UTF8 = 1 << 8
TYPE_STRING, TYPE_INT = 0x03, 0x10


def _length(data, at, wide):
    """(length, size of the length field) at the offset: one or two units, the high bit of the first marking two."""
    unit = 2 if wide else 1
    first = int.from_bytes(data[at:at + unit], "little")
    high = 0x8000 if wide else 0x80
    if first & high:
        second = int.from_bytes(data[at + unit:at + 2 * unit], "little")
        return ((first & (high - 1)) << (8 * unit)) | second, 2 * unit
    return first, unit


def _pool(data, start):
    """The strings of the string pool chunk starting at start."""
    count, _, flags, strings_at = struct.unpack_from("<IIII", data, start + 8)
    offsets = struct.unpack_from(f"<{count}I", data, start + 28)
    base = start + strings_at
    result = []
    for off in offsets:
        at = base + off
        if flags & UTF8:
            _, n = _length(data, at, False)
            size, m = _length(data, at + n, False)
            result.append(data[at + n + m:at + n + m + size].decode("utf-8"))
        else:
            size, n = _length(data, at, True)
            result.append(data[at + n:at + n + 2 * size].decode("utf-16-le"))
    return result


def manifest(data):
    """(package, versionCode) of the root <manifest> element of a binary AndroidManifest.xml; ValueError when it isn't one."""
    try:
        return _manifest(data)
    except (struct.error, IndexError, UnicodeDecodeError) as e:
        raise ValueError(f"not a binary manifest ({e})") from None


def _manifest(data):
    if len(data) < 8 or struct.unpack_from("<H", data, 0)[0] != 0x0003:
        raise ValueError("not a binary manifest")
    strings, resource_ids = None, []
    at = struct.unpack_from("<H", data, 2)[0]
    while at + 8 <= len(data):
        kind, header, size = struct.unpack_from("<HHI", data, at)
        if size < 8:
            raise ValueError("bad chunk size")
        if kind == STRING_POOL:
            strings = _pool(data, at)
        elif kind == RESOURCE_MAP:
            resource_ids = struct.unpack_from(f"<{(size - header) // 4}I", data, at + header)
        elif kind == START_ELEMENT:
            if strings is None:
                raise ValueError("no string pool")
            return _root(data, at, strings, resource_ids)
        at += size
    raise ValueError("no element")


def _root(data, at, strings, resource_ids):
    name = struct.unpack_from("<i", data, at + 20)[0]
    start, width, count = struct.unpack_from("<HHH", data, at + 24)
    if strings[name] != "manifest":
        raise ValueError("the root element isn't <manifest>")
    package = version = None
    for i in range(count):
        _, attr, raw, _, _, kind, value = struct.unpack_from("<iiiHBBI", data, at + 16 + start + i * width)
        label = strings[attr]
        if label == "package" and kind == TYPE_STRING:
            package = strings[raw]
        elif kind == TYPE_INT and (label == "versionCode" or (attr < len(resource_ids) and resource_ids[attr] == VERSION_CODE_ID)):
            version = value
    if package is None or version is None:
        raise ValueError("the manifest has no package or versionCode")
    return package, version
