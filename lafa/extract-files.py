#!/usr/bin/env -S PYTHONPATH=../../../../tools/extract-utils python3
# SPDX-License-Identifier: Apache-2.0
"""Extract RMX5200 / lafa camera files; never modify the input dump."""
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
from zipfile import ZipFile, ZipInfo

from extract_utils.fixups_blob import blob_fixup
from extract_utils.fixups_lib import lib_fixups as default_lib_fixups
from extract_utils.main import ExtractUtils, ExtractUtilsModule
from extract_utils.tools import apktool_path, common_binaries_dir, java_path
from patch_camera import STOCK_SHA256, patch_decoded
from patch_capture_adapter import patch as patch_adapter

HERE = Path(__file__).resolve().parent
ADAPTER_STOCK_SHA256 = 'c33f3a63a868ef632b4a403a669b2b00f2bf7c711c00293edd1f33f6e430ddd3'
SUFFIX = '_oplus_camera'
LIBRARIES = tuple(sorted({
    line.split(';')[0].split(':')[-1].rsplit('/', 1)[-1][:-3]
    for line in (HERE / 'proprietary-files.txt').read_text().splitlines()
    if line.strip() and not line.startswith('#') and '.so;MODULE_SUFFIX=' in line
}))

def camera_suffix(lib, partition, *args, **kwargs):
    return lib + SUFFIX

def patch_camera_apk(ctx, file, file_path, *args, **kwargs):
    path = Path(file_path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != STOCK_SHA256:
        raise ValueError('Unexpected APK: this port requires stock RMX5200 7.006.309')
    with tempfile.TemporaryDirectory(prefix='lafa-camera-') as work:
        decoded = Path(work) / 'decoded'
        subprocess.run([java_path, '-Xmx6g', '-jar', apktool_path, 'd', str(path),
                        '-f', '--no-debug-info', '-o', str(decoded)], check=True)
        patch_decoded(decoded)
        subprocess.run([java_path, '-Xmx6g', '-jar', apktool_path, 'b', str(decoded),
                        '-o', str(path)], check=True)

def patch_adapter_jar(ctx, file, file_path, *args, **kwargs):
    path = Path(file_path)
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if digest != ADAPTER_STOCK_SHA256:
        raise ValueError('Unexpected camera adapter JAR for RMX5200 7.006.309')
    smali_tools = Path(common_binaries_dir) / 'smali'
    with tempfile.TemporaryDirectory(prefix='lafa-adapter-') as work:
        work = Path(work)
        dex = work / 'classes.dex'
        smali = work / 'decoded'
        with ZipFile(path) as archive:
            dex.write_bytes(archive.read('classes.dex'))
        subprocess.run([java_path, '-jar', smali_tools / 'baksmali.jar',
                        'd', '-o', smali, dex], check=True)
        patch_adapter(smali)
        subprocess.run([java_path, '-jar', smali_tools / 'smali.jar',
                        'a', '-o', dex, smali], check=True)
        # Pad the local ZIP header so ART can map the stored DEX.
        entry = ZipInfo('classes.dex')
        entry.extra = b'\xff\xff\x03\x00\x00\x00\x00'
        with ZipFile(path, 'w') as archive:
            archive.writestr(entry, dex.read_bytes())

module = ExtractUtilsModule(
    'blobs', 'oplus/camera/lafa',
    device_rel_path='vendor/oplus/camera/lafa',
    namespace_imports=[
        'vendor/realme/lafa',
        'vendor/oneplus/sm8850-common',
        'hardware/oplus',
    ],
    lib_fixups={**default_lib_fixups, LIBRARIES: camera_suffix},
    blob_fixups={
        'system_ext/priv-app/OplusCamera/OplusCamera.apk': blob_fixup().call(patch_camera_apk),
        'system_ext/framework/com.oplus.camera.unit.sdk.adapter.jar': blob_fixup().call(patch_adapter_jar),
        'system_ext/lib64/libcsextimpl.so': blob_fixup()
            .replace_needed('android.hardware.camera.device-V3-ndk.so', 'android.hardware.camera.device-V4-ndk.so')
            .replace_needed('android.hardware.camera.provider-V3-ndk.so', 'android.hardware.camera.provider-V4-ndk.so'),
    },
)

if __name__ == '__main__':
    ExtractUtils.device(module).run()
    # Both OEM SDKs contain DEX only, so dex_import cannot provide JavaInfo for
    # Soong's optional_uses_libs compiler dependency. Keep the original manifest
    # uses-library and the installed XML/JARs for runtime resolution. This APK
    # already has dex_preopt disabled; suppress only its build-time CLC check.
    bp = HERE / 'blobs/Android.bp'
    value = bp.read_text()
    pattern = re.compile(r'(android_app_import\s*\{\s*name:\s*"OplusCamera",)')
    value, count = pattern.subn(r'\1\n    // OEM runtime shared SDKs are dex_import modules, not Java classpath libraries.\n    enforce_uses_libs: false,', value)
    if count != 1:
        raise ValueError('Expected one generated OplusCamera import')
    bp.write_text(value)
