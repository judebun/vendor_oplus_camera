// SPDX-License-Identifier: Apache-2.0
// Register assignments follow camApsBufferLockPlanes in this blob version.
// The vendor P010 format is exposed as one contiguous plane by libnativewindow.
.text
.global p010_plane_layout
p010_plane_layout:
    cbnz x9, .Lreported_chroma
    ldr w9, [sp, #0x130]
    movz w14, #0x0c0a
    movk w14, #0x7fa3, lsl #16
    cmp w9, w14
    b.ne .Lreported_chroma
    ldr w9, [sp, #0x134]
    cmp w10, w9, lsl #1
    b.ne .Lmissing_chroma
    ldr w9, [sp, #0x138]
    mov w12, w10
    mov w13, w10
    b .Lstore_luma
.Lmissing_chroma:
    mov w9, wzr
    b .Lstore_luma
.Lreported_chroma:
    sub x9, x9, x8
    sdiv x9, x9, x10
.Lstore_luma:
    str x8, [x20, #0x18]
    b resume_plane_layout

// app_cmd_addFrameBuff stores the begin and end of its parameter vector here.
// Honor the existing switch for every mode. Also unpack RAW10 in aiHighPixel.
.global high_pixel_unpack
high_pixel_unpack:
    tbnz w19, #0, .Lunpack
    ldr x8, [sp, #0x258]
    ldr x9, [sp, #0x260]
    adr x10, .Lcapture_mode
    ldp x11, x12, [x10]
.Lnext_parameter:
    cmp x8, x9
    b.hs .Lskip_unpack
    ldrb w10, [x8]
    cmp w10, #24  // Short string of length 12.
    b.ne .Ladvance_parameter
    ldur x13, [x8, #1]
    cmp x13, x11
    b.ne .Ladvance_parameter
    ldur w13, [x8, #9]
    cmp w13, w12
    b.ne .Ladvance_parameter
    ldrb w10, [x8, #24]
    cmp w10, #22  // Short string of length 11.
    b.ne .Lskip_unpack
    adr x10, .Lhigh_pixel_mode
    ldp x11, x12, [x10]
    ldur x13, [x8, #25]
    cmp x13, x11
    b.ne .Lskip_unpack
    ldur w13, [x8, #33]
    cmp w13, w12
    b.eq .Lunpack
.Lskip_unpack:
    b skip_unpack_frame
.Lunpack:
    b unpack_frame
.Ladvance_parameter:
    add x8, x8, #48
    b .Lnext_parameter

.balign 8
.Lcapture_mode:
    .ascii "capture_mode"
    .zero 4
.Lhigh_pixel_mode:
    .asciz "aiHighPixel"
    .zero 4
