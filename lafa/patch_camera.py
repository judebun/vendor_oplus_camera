#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Guarded AOSP UI adaptations for RMX5200 Camera 7.006.309 only.

No capture sizes, sensor modes, exposure, zoom ranges or SDK sequencing change.
The source APK is never modified. Run against an apktool-decoded working copy.
"""
import argparse
import re
from pathlib import Path
import xml.etree.ElementTree as ET

STOCK_SHA256 = '1d850c7d93e2ac1826ea6f97940c47cbcbd5fdb1c559df5a56e3e558036cd732'
ANDROID = '{http://schemas.android.com/apk/res/android}'

def replace_method(text, signature, body, required):
    pattern = re.compile(r'^' + re.escape(signature) + r'\n.*?^\.end method$', re.M | re.S)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one {signature}, got {len(matches)}')
    match = matches[0]
    if not all(token in match.group() for token in required):
        raise ValueError(f'Unexpected OEM method body: {signature}')
    return text[:match.start()] + signature + '\n' + body.strip() + '\n.end method' + text[match.end():]

GALLERY = '''
    .locals 3

    # A generic gallery must not expose older media from the locked camera.
    if-eqz p3, :done
    iget-object v0, p0, Lcom/oplus/camera/helper/GalleryHelper;->a:Landroid/app/Activity;
    const-string v1, "keyguard"
    invoke-virtual {v0, v1}, Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;
    move-result-object v1
    check-cast v1, Landroid/app/KeyguardManager;
    if-eqz v1, :done
    invoke-virtual {v1}, Landroid/app/KeyguardManager;->isKeyguardLocked()Z
    move-result v2
    if-nez v2, :done

    new-instance v1, Landroid/content/Intent;
    const-string v2, "android.intent.action.VIEW"
    invoke-direct {v1, v2}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V
    if-eqz p2, :image
    const-string v2, "video/*"
    goto :set_data
    :image
    const-string v2, "image/*"
    :set_data
    invoke-virtual {v1, p3, v2}, Landroid/content/Intent;->setDataAndType(Landroid/net/Uri;Ljava/lang/String;)Landroid/content/Intent;
    const/4 v2, 0x1
    invoke-virtual {v1, v2}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;
    invoke-virtual {v0}, Landroid/content/Context;->getPackageManager()Landroid/content/pm/PackageManager;
    move-result-object v2
    invoke-virtual {v1, v2}, Landroid/content/Intent;->resolveActivity(Landroid/content/pm/PackageManager;)Landroid/content/ComponentName;
    move-result-object v2
    if-eqz v2, :done
    :try_start
    invoke-virtual {v0, v1}, Landroid/app/Activity;->startActivity(Landroid/content/Intent;)V
    :try_end
    .catch Landroid/content/ActivityNotFoundException; {:try_start .. :try_end} :gallery_error
    .catch Ljava/lang/SecurityException; {:try_start .. :try_end} :gallery_error
    goto :done
    :gallery_error
    move-exception v2
    const-string v0, "GalleryHelper"
    const-string v1, "Unable to open the selected media"
    invoke-static {v0, v1, v2}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I
    :done
    return-void
'''

def patch_optional_scene_observer(root):
    """Skip the unavailable OEM-only scene subscription on the AOSP port.

    Keep the existing visible-task query and local state. There is no complex
    scene service in this ROM, so do not instantiate its observer subclass or
    report that an observer was registered. Sensor/capture code is untouched.
    """
    path = Path(root) / 'smali_classes32/com/oplus/camera/util/i1.smali'
    value = path.read_text()
    field = '.field public final f:Lcom/oplus/camera/util/i1$a;'
    if value.count(field) != 1:
        raise ValueError('Unexpected FloatingWindowDetectHelper observer field')
    value = value.replace(field, '.field public final f:Ljava/lang/Object;')
    value = replace_method(value, '.method public constructor <init>()V', '''
    .locals 0
    # Fields retain Java defaults; the OEM scene service is absent on AOSP.
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    return-void
''', ['new-instance v0, Lcom/oplus/camera/util/i1$a;', 'complexSceneTypeArray'])
    value = replace_method(value, '.method public final e(Ldn/c;)V', '''
    .locals 2
    iput-object p1, p0, Lcom/oplus/camera/util/i1;->d:Lcom/oplus/camera/util/i1$c;
    const-string v0, "FloatingWindowDetectHelper"
    const-string v1, "OEM complex-scene subscription unavailable on AOSP"
    invoke-static {v0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    return-void
''', ['registerComplexSceneObserver'])
    value = replace_method(value, '.method public final g()V', '''
    .locals 1
    const/4 v0, 0x0
    iput-object v0, p0, Lcom/oplus/camera/util/i1;->d:Lcom/oplus/camera/util/i1$c;
    return-void
''', ['unregisterComplexSceneObserver'])
    path.write_text(value)
    return str(path.relative_to(root))

def patch_preview_callback(root):
    path = Path(root) / 'smali_classes23/co/i.smali'
    value = path.read_text()
    signature = '.method public final onFrameAvailable(Landroid/graphics/SurfaceTexture;)V'
    methods = re.findall(re.escape(signature) + r'\n(.*?)^\.end method$', value, re.M | re.S)
    if len(methods) != 1:
        raise ValueError('Unexpected CameraScreenNail frame callback')
    body = methods[0]
    replacements = (
        ('    if-ne v4, v0, :cond_6\n',
         '    if-ne v4, v0, :cond_6\n\n'
         '    # Both ImageReader preview paths signal a queued image with null.\n'
         '    if-eqz p1, :cond_6\n'),
        ('    if-eqz p1, :cond_4\n\n', ''),
        ('    :cond_4\n    :goto_1\n', '    :goto_1\n'),
    )
    for old, new in replacements:
        if body.count(old) != 1:
            raise ValueError('Unexpected CameraScreenNail texture validation')
        body = body.replace(old, new)
    value = replace_method(value, signature, body, [
        'CameraUnitAlgoSwitchConfig;->getApsVersion()',
        'Lco/f1;->G0:Landroid/graphics/SurfaceTexture;',
        'Lco/i;->P1:Z',
    ])
    path.write_text(value)
    return str(path.relative_to(root))

def patch_preview_render(root):
    path = Path(root) / 'smali_classes23/co/f1.smali'
    value = path.read_text()
    signature = '.method public final s(Lcom/oplus/camera/common/gl/k;IIII)V'
    methods = re.findall(re.escape(signature) + r'\n(.*?)^\.end method$', value, re.M | re.S)
    if len(methods) != 1:
        raise ValueError('Unexpected SurfaceTextureScreenNail renderer')
    body = methods[0]
    aps_gate = '''    invoke-static {}, Lcom/oplus/ocs/camera/appinterface/adapter/CameraUnitAlgoSwitchConfig;->getApsVersion()I

    move-result v2

    const/4 v4, 0x3

    const/4 v10, 0x0

    if-gt v4, v2, :cond_2
'''
    skipped_queue = '''    :cond_2
    move-object v4, v10

'''
    if body.count(aps_gate) != 1 or body.count(':cond_2\n') != 2 or body.count(skipped_queue) != 1:
        raise ValueError('Unexpected SurfaceTextureScreenNail queue selection')
    # Use a queued image when one exists and retain the texture fallback.
    body = body.replace(aps_gate, '    const/4 v10, 0x0\n').replace(skipped_queue, '')
    importer_gate = '''    iget-wide v3, v1, Lco/f1;->P0:J

    cmp-long v3, v20, v3

    if-eqz v3, :cond_13
'''
    if body.count(importer_gate) != 1:
        raise ValueError('Unexpected SurfaceTextureScreenNail buffer importer')
    body = body.replace(importer_gate, '''    iget-wide v3, v1, Lco/f1;->P0:J

    cmp-long v3, v20, v3

    if-nez v3, :buffer_importer_ready

    # The image queue can be used even when texture setup skipped PreviewShow.
    invoke-static {}, Lcom/oplus/camera/jni/PreviewShow;->init()J

    move-result-wide v3

    iput-wide v3, v1, Lco/f1;->P0:J

    cmp-long v3, v20, v3

    if-eqz v3, :cond_13

    :buffer_importer_ready
''')
    value = replace_method(value, signature, body, [
        'Lco/f1;->O0:Ljava/lang/Object;',
        'Lco/f1;->L0:Ljava/util/ArrayList;',
        'PreviewShow;->process(Landroid/hardware/HardwareBuffer;IIJ)V',
    ])
    path.write_text(value)
    return str(path.relative_to(root))

def patch_preview_buffer_transform(root):
    """Use the OEM image-queue transform for photo and video buffer previews."""
    path = Path(root) / 'smali_classes23/co/f1.smali'
    text = path.read_text()
    field = '.field public G0:Landroid/graphics/SurfaceTexture;'
    if text.count(field) != 1 or 'usePreviewBufferTransform' in text:
        raise ValueError('Unexpected preview texture state')
    text = text.replace(field, field + '\n\n.field private volatile usePreviewBufferTransform:Z')
    signature = '.method public final s(Lcom/oplus/camera/common/gl/k;IIII)V'
    matches = re.findall(re.escape(signature) + r'\n(.*?)^\.end method$', text, re.M | re.S)
    if len(matches) != 1:
        raise ValueError('Unexpected preview buffer renderer')
    body = matches[0]
    start = '    :cond_0\n    const/4 v10, 0x0'
    imported = '    invoke-static {v3, v10, v4, v5, v6}, Lcom/oplus/camera/jni/PreviewShow;->process(Landroid/hardware/HardwareBuffer;IIJ)V'
    current_mode = '    iget-object v3, v3, Lum/m5;->a:Lcom/oplus/camera/module/BaseMode;'
    if body.count(start) != 1 or body.count(imported) != 1:
        raise ValueError('Unexpected preview buffer import')
    before, after = body.split(imported)
    if after.count(current_mode) != 1:
        raise ValueError('Unexpected active preview mode')
    before = before.replace(start, start + '\n\n    iput-boolean v11, v1, Lco/f1;->usePreviewBufferTransform:Z')
    preview_modes = ('common', 'portrait', 'commonVideo', 'masterVideo')
    mode_tests = ''.join(f'''
    const-string v5, "{mode}"
    invoke-virtual {{v5, v4}}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v5
    if-nez v5, :set_buffer_transform
''' for mode in preview_modes)
    after = after.replace(current_mode, current_mode + '''

    iget-boolean v4, v1, Lco/f1;->usePreviewBufferTransform:Z
    if-eqz v4, :buffer_transform_done
    if-eqz v3, :other_preview_source
    iget-object v4, v3, Lcom/oplus/camera/module/BaseMode;->U0:Ljava/lang/String;
''' + mode_tests + '''
    :other_preview_source
    const/4 v4, 0x0
    iput-boolean v4, v1, Lco/f1;->usePreviewBufferTransform:Z
    goto :buffer_transform_done
    :set_buffer_transform
    iget-object v4, v1, Lco/f1;->Y:[F
    invoke-virtual {v1, v4}, Lco/f1;->getTransformMatrix([F)V
    iget-object v5, v1, Lco/f1;->v:Lcom/oplus/camera/filter/IEffectProcessor;
    invoke-interface {v5, v4}, Lcom/oplus/camera/filter/IEffectProcessor;->setTransform([F)V
    :buffer_transform_done''')
    # G0 can exist solely for fallback even though PreviewShow sampled an ImageReader.
    mark = '''
    iget-object v3, v1, Lco/f1;->G0:Landroid/graphics/SurfaceTexture;
    if-eqz v3, :buffer_source_recorded
    const/4 v3, 0x1
    iput-boolean v3, v1, Lco/f1;->usePreviewBufferTransform:Z
    :buffer_source_recorded
'''
    text = replace_method(text, signature, before + imported + '\n' + mark + after, [imported])
    getter = '.method public final getTransformMatrix([F)V'
    prefix = getter + '\n    .locals 3\n'
    if text.count(prefix) != 1:
        raise ValueError('Unexpected preview transform getter')
    text = text.replace(prefix, prefix + '''
    iget-boolean v0, p0, Lco/f1;->usePreviewBufferTransform:Z
    if-nez v0, :cond_0
''')
    path.write_text(text)
    return str(path.relative_to(root))

def patch_optional_face_preview(root):
    path = Path(root) / 'smali_classes12/ue/e.smali'
    text = path.read_text()
    original = '''    new-instance v1, Lcom/oplus/ocs/camera/OplusFaceBeautyPreviewHelper;

    invoke-direct {v1}, Lcom/oplus/ocs/camera/OplusFaceBeautyPreviewHelper;-><init>()V

    iput-object v1, v0, Lue/e;->g:Lcom/oplus/ocs/camera/OplusFaceBeautyPreviewHelper;'''
    if text.count(original) != 1 or 'createOptionalFacePreview' in text:
        raise ValueError('Unexpected face preview construction')
    text = text.replace(original, '''    invoke-static {}, Lue/e;->createOptionalFacePreview()Lcom/oplus/ocs/camera/OplusFaceBeautyPreviewHelper;

    move-result-object v1

    iput-object v1, v0, Lue/e;->g:Lcom/oplus/ocs/camera/OplusFaceBeautyPreviewHelper;

    if-eqz v1, :goto_4''')
    process_entry = '''    :goto_2
    iget-object v5, p1, Lcom/oplus/camera/filter/texturepreview/FrameInfo;->mImage:Lfb/d;'''
    if text.count(process_entry) != 1:
        raise ValueError('Unexpected face preview frame processor')
    text = text.replace(process_entry, '''    :goto_2
    iget-object v5, p0, Lue/e;->g:Lcom/oplus/ocs/camera/OplusFaceBeautyPreviewHelper;
    if-nez v5, :face_helper_ready
    invoke-static {v4}, Lsn/a;->e(Ljava/lang/String;)V
    return v3

    :face_helper_ready
    iget-object v5, p1, Lcom/oplus/camera/filter/texturepreview/FrameInfo;->mImage:Lfb/d;''')
    text += '''
.method private static createOptionalFacePreview()Lcom/oplus/ocs/camera/OplusFaceBeautyPreviewHelper;
    .locals 3

    :try_start
    new-instance v0, Lcom/oplus/ocs/camera/OplusFaceBeautyPreviewHelper;
    invoke-direct {v0}, Lcom/oplus/ocs/camera/OplusFaceBeautyPreviewHelper;-><init>()V
    :try_end
    .catch Ljava/lang/LinkageError; {:try_start .. :try_end} :preview_unavailable
    return-object v0

    :preview_unavailable
    move-exception v0
    const-string v1, "FaceSlenderTexturePreview"
    const-string v2, "Optional face preview native library unavailable"
    invoke-static {v1, v2, v0}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I
    const/4 v0, 0x0
    return-object v0
.end method
'''
    path.write_text(text)
    return str(path.relative_to(root))

def patch_capture_defer_probe(root):
    path = Path(root) / 'smali_classes2/com/oplus/camera/feature/defer/a.smali'
    value = path.read_text()
    signature = '.method public static n(Z[Ljava/lang/String;)Z'
    methods = re.findall(re.escape(signature) + r'\n(.*?)^\.end method$', value, re.M | re.S)
    if len(methods) != 1:
        raise ValueError('Unexpected capture-defer storage probe')
    body = methods[0]
    original_read = '''    invoke-static {v0, v1}, Lkotlin/io/FilesKt__FileReadWriteKt;->readText(Ljava/io/File;Ljava/nio/charset/Charset;)Ljava/lang/String;

    move-result-object v0
'''
    if body.count(original_read) != 1:
        raise ValueError('Unexpected capture-defer storage read')
    guarded_read = '''    invoke-static {v0, v1}, Lcom/oplus/camera/feature/defer/a;->readUfsInfo(Ljava/io/File;Ljava/nio/charset/Charset;)Ljava/lang/String;

    move-result-object v0

    if-eqz v0, :ufs_unavailable
'''
    if body.count('    :cond_9\n') != 1 or body.count('    :try_end_6\n') != 1:
        raise ValueError('Unexpected capture-defer storage result')
    body = body.replace(original_read, guarded_read)
    body = body.replace('    :cond_9\n', '''    goto :cond_9

    :ufs_unavailable
    # Leave the storage model uncached and decline deferred capture.
    const/4 v0, 0x0
    sput-object v0, Lcom/oplus/camera/feature/defer/a;->d:Ljava/lang/Boolean;
    move v0, v3
    goto :ufs_probe_done

    :cond_9
''')
    body = body.replace('    :try_end_6\n', '    :ufs_probe_done\n    :try_end_6\n')
    reader = '''

.method private static readUfsInfo(Ljava/io/File;Ljava/nio/charset/Charset;)Ljava/lang/String;
    .locals 1

    :try_start
    invoke-static {p0, p1}, Lkotlin/io/FilesKt__FileReadWriteKt;->readText(Ljava/io/File;Ljava/nio/charset/Charset;)Ljava/lang/String;
    move-result-object v0
    :try_end
    .catch Ljava/io/IOException; {:try_start .. :try_end} :read_failed
    return-object v0

    :read_failed
    move-exception v0
    const/4 v0, 0x0
    return-object v0
.end method
'''
    value = replace_method(value, signature, body, ['/proc/devinfo/ufs', 'monitor-exit p0'])
    path.write_text(value.rstrip() + reader)
    return str(path.relative_to(root))

def patch_decoded(root):
    root = Path(root)
    manifest = root / 'AndroidManifest.xml'
    text = manifest.read_text()
    parsed = ET.fromstring(text)
    if parsed.get('package') != 'com.oplus.camera':
        raise ValueError('Unexpected APK package')
    yml = (root / 'apktool.yml').read_text()
    if not re.search(r'versionName:\s*[\'"]?7\.006\.309[\'"]?\s*$', yml, re.M):
        raise ValueError('This adaptation supports only Camera 7.006.309')
    if 'lafa AOSP compatibility permissions' in text:
        raise ValueError('Working copy is already patched; use a clean decode')

    changes = {}
    path = root / 'smali/ma/u3.smali'
    changes[path] = replace_method(
        path.read_text(), '.method public static a(Landroid/content/Context;)Landroid/graphics/Typeface;',
        '''    .locals 1
    sget-object v0, Landroid/graphics/Typeface;->DEFAULT:Landroid/graphics/Typeface;
    return-object v0''', ['OplusBaseConfiguration', 'OplusExtraConfiguration'])

    for relative in ('smali/com/oplus/camera/lh$k.smali', 'smali_classes33/l4/a.smali'):
        path = root / relative
        value = path.read_text()
        pattern = re.compile(r'    const-string v1, "linearmotor"\s+invoke-virtual \{p0, v1\}, Landroid/content/Context;->getSystemService\(Ljava/lang/String;\)Ljava/lang/Object;')
        value, count = pattern.subn('    invoke-static {p0}, Lcom/oplus/os/LinearmotorVibrator;->create(Landroid/content/Context;)Lcom/oplus/os/LinearmotorVibrator;', value)
        if count != 1:
            raise ValueError(f'Expected one motor lookup in {relative}, got {count}')
        changes[path] = value

    path = root / 'smali_classes12/com/oplus/camera/helper/GalleryHelper.smali'
    changes[path] = replace_method(
        path.read_text(), '.method public final p(Landroid/content/Intent;ZLandroid/net/Uri;)V',
        GALLERY, ['thumbnail_click', 'resolveActivity', 'startActivity'])

    # Keep component protections. Define absent OEM gate permissions with the
    # platform-signed camera's certificate rather than stripping their guards.
    declared = {x.get(ANDROID + 'name') for x in parsed.findall('permission')}
    gates = {'com.oplus.permission.safe.CAMERA'}
    for node in parsed.iter():
        for key in ('permission', 'readPermission', 'writePermission'):
            value = node.get(ANDROID + key, '')
            if value.startswith(('com.oplus.permission.safe.', 'oplus.permission.OPLUS_COMPONENT_SAFE')):
                gates.add(value)
    declarations = ['    <!-- lafa AOSP compatibility permissions; component guards retained. -->']
    for name in sorted(gates - declared):
        declarations.append(f'    <permission android:name="{name}" android:protectionLevel="signature"/>')
    text = text.replace('    <compatible-screens/>', '\n'.join(declarations) + '\n    <compatible-screens/>', 1)
    queries = '''        <intent>
            <action android:name="android.intent.action.VIEW"/>
            <data android:mimeType="image/*"/>
        </intent>
        <intent>
            <action android:name="android.intent.action.VIEW"/>
            <data android:mimeType="video/*"/>
        </intent>
'''
    if text.count('    </queries>') != 1:
        raise ValueError('Unexpected queries structure')
    text = text.replace('    </queries>', queries + '    </queries>')
    updated = ET.fromstring(text)
    old_components = [dict(x.attrib) for x in parsed.find('application')]
    assert old_components == [dict(x.attrib) for x in updated.find('application')]
    changes[manifest] = text
    # Validate all targets before writing any one of them.
    for path, value in changes.items():
        path.write_text(value)
    scene = patch_optional_scene_observer(root)
    preview = patch_preview_callback(root)
    renderer = patch_preview_render(root)
    patch_preview_buffer_transform(root)
    face_preview = patch_optional_face_preview(root)
    defer = patch_capture_defer_probe(root)
    return [str(path.relative_to(root)) for path in changes] + [scene, preview, renderer, face_preview, defer]

def blob_fixup(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    if tmp_dir is None:
        raise ValueError('apktool work directory is required')
    patch_decoded(tmp_dir)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('decoded')
    args = parser.parse_args()
    for changed in patch_decoded(args.decoded):
        print('Patched:', changed)
