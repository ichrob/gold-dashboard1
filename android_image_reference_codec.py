"""Lossless *offline* device-scoped PNG reference codec.

No production reader, importer, HTTP handler or scheduled worker invokes this.
This pure helper is the first non-migrating stage of a possible future
content-addressed, reversible screenshot storage scheme. Caller must supply
explicit authenticated device scope and controlled object mapping.
"""
import base64
import copy
import hashlib
import re
import struct

_REF = '_bobPrivateImageRefV1'
_DOMAIN = b'bob-private-png-v1\x00'
_SCOPE_RE = re.compile(r'[a-f0-9]{64}\Z')
_HASH_RE = re.compile(r'[a-f0-9]{64}\Z')
_MAX_IMAGES = 4
_MAX_ENCODED = 2_000_000


def _scope(scope):
    if type(scope) is not str or not _SCOPE_RE.fullmatch(scope):
        raise ValueError('Invalid authenticated image scope')
    return bytes.fromhex(scope)


def _decode(encoded):
    """Recheck existing Android PNG size/dimension rules without side effects."""
    if type(encoded) is not str or not 1 <= len(encoded) <= _MAX_ENCODED:
        raise ValueError('Invalid PNG encoding length')
    try:
        raw=base64.b64decode(encoded,validate=True)
    except Exception:
        raise ValueError('Invalid PNG base64') from None
    if (len(raw)<33 or raw[:8]!=b'\x89PNG\r\n\x1a\n'
            or raw[12:16]!=b'IHDR'):
        raise ValueError('Invalid PNG header')
    width,height=struct.unpack('>II',raw[16:24])
    if not 200 <= width <= 5000 or not 200 <= height <= 5000 or width*height>16_000_000:
        raise ValueError('Invalid PNG dimensions')
    return raw


def _content_key(owner_bytes,raw):
    return hashlib.sha256(_DOMAIN+owner_bytes+raw).hexdigest()


def pack_batch(original,scope):
    """Produce pointers and an in-memory object map, never persist either.

    Returns (pointer_batch, {device_scoped_content_key: original_base64}).
    The full original must remain available until a future explicitly gated
    migration tests exact read-through and verified independent backup.
    """
    owner=_scope(scope)
    if type(original) is not dict or type(original.get('images')) is not list:
        raise ValueError('Invalid original batch')
    imgs=original['images']
    if not 1 <= len(imgs) <= _MAX_IMAGES:
        raise ValueError('Invalid image count')
    packed=copy.deepcopy(original)
    objects={}
    seen=set()
    for i,image in enumerate(imgs):
        if (type(image) is not dict or set(image) not in
                ({'at','png'},{'at','png','appText'})
                or type(image.get('at')) is not str):
            raise ValueError('Invalid image shape')
        encoded=image['png']
        raw=_decode(encoded)
        key=_content_key(owner,raw)
        if key in seen:
            # Current batch validation forbids duplicate screenshots.
            raise ValueError('Repeated screenshot in one batch')
        seen.add(key)
        if key in objects and objects[key]!=encoded:
            raise ValueError('Image hash collision')
        objects[key]=encoded
        packed['images'][i].pop('png')
        packed['images'][i][_REF]=key
    return packed,objects


def restore_batch(pointer_batch,objects,scope):
    """Reject missing/corrupt/cross-device objects; round-trip exact JSON.

    Does not fetch Drive or PostgreSQL, create objects, log content, or
    substitute upload time for original image/market source timestamps.
    """
    owner=_scope(scope)
    if (type(pointer_batch) is not dict
            or type(pointer_batch.get('images')) is not list
            or not 1 <= len(pointer_batch['images']) <= _MAX_IMAGES
            or type(objects) is not dict):
        raise ValueError('Invalid pointer batch')
    restored=copy.deepcopy(pointer_batch)
    for i,image in enumerate(pointer_batch['images']):
        if (type(image) is not dict
                or set(image) not in ({'at',_REF},{'at','appText',_REF})
                or type(image.get('at')) is not str):
            raise ValueError('Ambiguous image pointer')
        key=image[_REF]
        if type(key) is not str or not _HASH_RE.fullmatch(key):
            raise ValueError('Invalid image reference')
        encoded=objects.get(key)
        if type(encoded) is not str:
            raise ValueError('Image object missing')
        raw=_decode(encoded)
        if _content_key(owner,raw)!=key:
            raise ValueError('Image object identity mismatch')
        restored['images'][i].pop(_REF)
        restored['images'][i]['png']=encoded
    return restored
