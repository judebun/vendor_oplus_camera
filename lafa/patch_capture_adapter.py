#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Route lafa still captures to the appropriate APS implementation."""
import argparse
from pathlib import Path

ADAPTER = "Lcom/oplus/ocs/camera/consumer/apsAdapter/"
ALGORITHM = ADAPTER + "algorithm/"
PREVIEW = ALGORITHM + "PreviewApsImpl;"
FULL = ALGORITHM + "FullApsImpl;"


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"Expected one adapter anchor: {old}")
    return source.replace(old, new, 1)


def patch_method(source, name, instructions):
    start = source.index(".method public " + name + "(")
    end = source.index(".end method", start)
    lines = source[start:end].splitlines()
    signature = lines[0].removeprefix(".method public ")
    condition = instructions.replace("@METHOD@", f"{FULL}->{signature}")
    return source[:start] + "\n".join([lines[0], lines[1], condition, *lines[2:]]) + "\n" + source[end:]


def patch_ordinary_capture(source):
    frame = ALGORITHM + "NoneApsImpl$CaptureFrame;"
    utils = ADAPTER + "adapter/ApsUtils;"
    source = replace_once(
        source,
        f"    invoke-static {{p3}}, {utils}->getNumPlanesForFormat(I)I",
        f"""    const/16 p4, 0x23
    if-ne p3, p4, :original_buffer

    invoke-direct {{p0, p2}}, {PREVIEW}->queueYuvJpeg(Landroid/media/Image;)I
    move-result p0
    return p0

    :original_buffer
    invoke-static {{p3}}, {utils}->getNumPlanesForFormat(I)I""",
    )
    return source + f"""
.method private queueYuvJpeg(Landroid/media/Image;)I
    .locals 5

    invoke-virtual {{p1}}, Landroid/media/Image;->getWidth()I
    move-result v0
    invoke-virtual {{p1}}, Landroid/media/Image;->getHeight()I
    move-result v1

    const/16 v2, 0x11
    const/4 v3, 0x0
    invoke-static {{p1, v2, v3}}, {utils}->getYuvDataWithoutPadding(Landroid/media/Image;I[B)[B
    move-result-object v2
    if-eqz v2, :failed
    invoke-static {{v2, v0, v1}}, {utils}->convertNV21DataToJpeg([BII)[B
    move-result-object v2
    if-eqz v2, :failed
    array-length v3, v2
    if-eqz v3, :failed

    new-instance v3, {frame}
    invoke-direct {{v3}}, {frame}-><init>()V
    iput v0, v3, {frame}->mWidth:I
    iput v1, v3, {frame}->mHeight:I
    iput-object v2, v3, {frame}->mData:[B
    iget-object v4, p0, {PREVIEW}->mApsListener:{ALGORITHM}ApsInterface$ApsListener;
    iput-object v4, v3, {frame}->mApsListener:{ALGORITHM}ApsInterface$ApsListener;
    iget-object v0, p0, {PREVIEW}->mCaptureQueueLock:Ljava/lang/Object;
    monitor-enter v0
    :try_start
    iget-object v1, p0, {PREVIEW}->mCaptureFrameQueue:Ljava/util/Queue;
    invoke-interface {{v1, v3}}, Ljava/util/Queue;->add(Ljava/lang/Object;)Z
    monitor-exit v0
    :try_end
    .catchall {{:try_start .. :try_end}} :release_lock
    const/4 v0, 0x0
    return v0

    :release_lock
    move-exception v1
    monitor-exit v0
    throw v1

    :failed
    const/4 v0, -0x1
    return v0
.end method

"""


def patch(root):
    adapter = root / ADAPTER[1:]
    handler = adapter / "adapter/ApsAdapterImpl$ImageProcessHandler.smali"
    source = handler.read_text()
    source = replace_once(source, f"new-instance v2, {FULL}", f"new-instance v2, {PREVIEW}")
    source = replace_once(source, f"invoke-direct {{v2, v5, v0}}, {FULL}-><init>",
                          f"invoke-direct {{v2, v5, v0}}, {PREVIEW}-><init>")
    handler.write_text(source)

    config = adapter / "config/AlgoSwitchConfig.smali"
    switch = ADAPTER + "config/AlgoSwitchConfig;"
    mode = f"    sput v2, {switch}->sApsMode:I\n\n    const-string v2, \"com.heytap.speechassist\""
    config.write_text(replace_once(config.read_text(), mode, "    const/4 v2, 0x1\n" + mode))

    preview = adapter / "algorithm/PreviewApsImpl.smali"
    source = patch_ordinary_capture(preview.read_text())
    for name, params, args in (
        ("addFrameBuff", "p2", "{p0, p1, p2, p3, p4}"),
        ("processImages", "p1", "{p0 .. p7}"),
    ):
        invoke = "invoke-super/range" if name == "processImages" else "invoke-super"
        source = patch_method(source, name, f"""
    invoke-static {{{params}}}, {PREVIEW}->isHighPixel([Ljava/lang/String;)Z
    move-result v0
    if-eqz v0, :use_preview_capture
    {invoke} {args}, @METHOD@
    move-result v0
    return v0
    :use_preview_capture
""")
        if name == "processImages":
            # v0 is p0 in the original method, which declares zero locals.
            source = replace_once(source, ".registers 8\n\n    invoke-static {p1}",
                                  ".registers 9\n\n    invoke-static {p1}")

    source = patch_method(source, "previewDecision", f"""
    invoke-virtual {{p1}}, {ADAPTER}adapter/ApsPreviewDecisionParam;->getCaptureMode()Ljava/lang/String;
    move-result-object v0
    const-string v1, "aiHighPixel"
    invoke-virtual {{v1, v0}}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v0
    if-eqz v0, :use_preview_decision
    invoke-super {{p0, p1}}, @METHOD@
    move-result-object v0
    return-object v0
    :use_preview_decision
""")
    source = replace_once(source, ".registers 3\n\n    invoke-virtual {p1}",
                          ".registers 4\n\n    invoke-virtual {p1}")
    for name in ("beforeCapture", "startCapture"):
        start = source.index(".method public " + name + "(")
        end = source.index(".end method", start)
        signature = source[start:source.index("\n", start)].removeprefix(".method public ")
        source = source[:start] + f""".method public {signature}
    .locals 1
    invoke-super {{p0, p1}}, @METHOD@
    move-result v0
    return v0
""".replace("@METHOD@", f"{FULL}->{signature}") + source[end:]

    source += f"""
.method private static isHighPixel([Ljava/lang/String;)Z
    .locals 4
    if-eqz p0, :missing
    const/4 v0, 0x1
    array-length v1, p0
    :next
    if-ge v0, v1, :missing
    add-int/lit8 v2, v0, -0x1
    aget-object v2, p0, v2
    const-string v3, "capture_mode"
    invoke-virtual {{v3, v2}}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v2
    if-nez v2, :found
    add-int/lit8 v0, v0, 0x2
    goto :next
    :found
    aget-object v0, p0, v0
    const-string v1, "aiHighPixel"
    invoke-virtual {{v1, v0}}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v0
    return v0
    :missing
    const/4 v0, 0x0
    return v0
.end method
"""
    preview.write_text(source)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("smali_directory", type=Path)
    patch(parser.parse_args().smali_directory)
