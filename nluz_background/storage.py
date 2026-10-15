"""Local immutable image pairs; no credentials or QGIS objects."""
import hashlib
import math
import os
import struct
import uuid
from pathlib import Path


def png_size(data):
    if len(data) < 33 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise ValueError('Invalid PNG header')
    return struct.unpack('>II', data[16:24])


def validate_world(data):
    values = [float(value) for value in data.decode('ascii').split()]
    if (len(values) != 6 or not all(math.isfinite(v) for v in values)
            or values[0] <= 0 or values[3] >= 0 or values[1] or values[2]):
        raise ValueError('Invalid world file')


def snapshot(source, root, project_name, crs):
    """Publish a complete, immutable PNG/PGW pair by directory rename.

    Same content can be reused. Different content never overwrites a snapshot
    already referenced by another saved project or its backup.
    """
    source, root = Path(source), Path(root)
    data = source.read_bytes()
    if min(png_size(data)) <= 0:
        raise ValueError('Empty PNG')
    world = source.with_suffix('.pgw').read_bytes()
    validate_world(world)
    project_id = hashlib.sha256(os.path.normcase(os.path.abspath(project_name)).encode('utf-8')).hexdigest()[:24]
    digest = hashlib.sha256(data + b'\0PGW\0' + world + b'\0CRS\0' + crs.encode('utf-8')).hexdigest()
    parent = root / project_id
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / digest
    target = destination / 'image.png'

    def matches():
        return (target.is_file() and target.read_bytes() == data
                and target.with_suffix('.pgw').read_bytes() == world)

    if destination.exists():
        if not matches():
            raise OSError('Existing snapshot differs')
        return target
    staging = parent / ('.stage-' + uuid.uuid4().hex)
    staging.mkdir()
    try:
        for name, content in (('image.png', data), ('image.pgw', world)):
            with (staging / name).open('xb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        # This directory is unique and contains only files created above.
        try:
            staging.rename(destination)
        except OSError:
            if not destination.is_dir() or not matches():
                raise
        return target
    finally:
        if staging.exists():
            for name in ('image.png', 'image.pgw'):
                (staging / name).unlink(missing_ok=True)
            staging.rmdir()
