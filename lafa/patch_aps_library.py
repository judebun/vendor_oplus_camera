#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the P010 compatibility library for the tested lafa APS binary."""
import argparse
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
EXPECTED = "a99d9bb489ea90a9b3a9c774393f8544b26ab4a92ad8f4613be94512239fb84e"
PATCH_START = 0x6DCCC8
TEXT_PROGRAM_HEADER = 0x40 + 2 * 0x38


def patch(source, llvm_bin):
    image = bytearray(source)
    def tool(name):
        return str(llvm_bin / name) if llvm_bin else name
    if hashlib.sha256(image).hexdigest() != EXPECTED:
        raise SystemExit("Unexpected libAlgoProcess.so version")

    with tempfile.TemporaryDirectory() as tmp:
        obj, elf, code = (Path(tmp) / name for name in ("patch.o", "patch.elf", "patch.bin"))
        subprocess.run(
            [tool("llvm-mc"), "-triple=aarch64", "-filetype=obj", HERE / "p010-compat.S", "-o", obj],
            check=True,
        )
        subprocess.run(
            [tool("ld.lld"), "-Ttext=0x6dccc8", "--entry=p010_plane_layout",
             "--defsym=resume_plane_layout=0x21d31c", "--defsym=unpack_frame=0x304414",
             "--defsym=skip_unpack_frame=0x304440", obj, "-o", elf],
            check=True,
        )
        subprocess.run([tool("llvm-objcopy"), "--dump-section", f".text={code}", elf], check=True)
        patch = code.read_bytes()
        symbols = {}
        for line in subprocess.check_output([tool("llvm-nm"), elf], text=True).splitlines():
            address, _, name = line.split()
            symbols[name] = int(address, 16)

    segment = struct.unpack_from("<II6Q", image, TEXT_PROGRAM_HEADER)
    kind, flags, offset, addr, _, file_size, memory_size, _ = segment
    end = PATCH_START + len(patch)
    if (kind, flags, offset, addr, file_size, memory_size) != (
        1, 5, 0x144000, 0x144000, PATCH_START - 0x144000, PATCH_START - 0x144000
    ) or end > 0x6DD000 or any(image[PATCH_START:end]):
        raise SystemExit("Unexpected executable segment layout")
    image[PATCH_START:end] = patch
    struct.pack_into("<QQ", image, TEXT_PROGRAM_HEADER + 32, file_size + len(patch),
                     memory_size + len(patch))

    for pc, target in ((0x21D310, "p010_plane_layout"), (0x304410, "high_pixel_unpack")):
        branch = 0x14000000 | ((symbols[target] - pc) // 4 & 0x03FFFFFF)
        struct.pack_into("<I", image, pc, branch)

    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock_library", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--llvm-bin", type=Path)
    args = parser.parse_args()
    image = patch(args.stock_library.read_bytes(), args.llvm_bin)
    args.output.write_bytes(image)
    print(f"{hashlib.sha256(image).hexdigest()}  {args.output}")


if __name__ == "__main__":
    main()
