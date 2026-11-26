#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Adapt the lafa camera unit session modes for the uwuAOSP camera stack."""
import argparse
import hashlib
import json
from pathlib import Path

STOCK_SHA256 = 'b2eaa0319017842b29ff51e64917e5204d1b857f30cb763a9108a1e13ea45960'
STANDARD_MODES = (
    'fastvideo_mode', 'fine_food_mode', 'high_pixel_mode', 'long_exposure_mode',
    'master_video_mode', 'multi_camera_mode', 'night_mode', 'panorama_mode',
    'photo_mode', 'professional_mode', 'star_capture_mode', 'super_text_mode',
    'tilt_shift_mode', 'video_mode',
)


def patch_camera_unit(source):
    if hashlib.sha256(source).hexdigest() != STOCK_SHA256:
        raise ValueError('Unexpected RMX5200 camera_unit_config')
    config = json.loads(source)
    operation_modes = config['mode_operation_mode']
    for mode in STANDARD_MODES:
        operation_modes[mode] = '0000'
    features = config['feature_operation_mode']
    features['high_pixel_mode']['aiHighPixel']['on'] = '0000'
    video = features['video_mode']
    del video['fovc']
    # The 0x8021 path requests more encoder buffers than the AOSP queue supports.
    video['fps']['video_60fps'] = '830B'
    # The generic 0x0000 session stalls at 4K during resolution switches.
    video['resolution']['4k'] = '830B'
    return json.dumps(config, indent=2) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stock_config', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    output = patch_camera_unit(args.stock_config.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output)
