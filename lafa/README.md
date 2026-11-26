# realme GT8 Pro (lafa) stock Camera port

This port adapts Camera 7.006.309 for lafa on Android 17 uwuAOSP.
On the test device, ordinary JPEG capture and 50MP and 200MP stills saved
successfully. Recorded files confirmed 60 fps at 1080p and 4K. The camera app
falls back to 30 fps for 720p and offers 30 fps at 8K.

## Source material

- Device: RMX5200 / RE6030L1, SM8850.
- Stock fingerprint:
  `realme/RMX5200/RE6030L1:17/CP2A.260605.016/B.25a1b69_12ba59_12adc4:user/release-keys`.
- APK: `com.oplus.camera`, version `7.006.309` / `60000`.
- Unmodified source APK SHA-256:
  `1d850c7d93e2ac1826ea6f97940c47cbcbd5fdb1c559df5a56e3e558036cd732`.
- File hashes and original source locations: `stock-manifest.json`.
- Port template: realahnet/vendor_oplus_camera, commit
  `f7f484c75d34364154dcc1748d8f0d09b7b34fc0`.
- Java compatibility source reference: realahnet/hardware_oplus, commit
  `b1327f0c1e0c4269445507f4c2a33b162c2e3c49`.

Keep proprietary material local unless you have permission to redistribute it.
`blobs/` is intentionally ignored by Git. No private signing keys belong here.

## Changes from the giulia template

- Extract actual lafa files, using canonical `my_product` sources and no duplicate
  `product` aliases.
- Use distinct `_oplus_camera` Soong module names while retaining library file
  names and SONAMEs.
- Use source-built Android HIDL/AIDL dependency libraries. Never replace
  `libcameraservice`, `libcamera_client`, `libbase` or `libhwui` with stock binaries.
- Adapt exactly the lafa APK's font and vibration calls. Use a generic media
  viewer only when unlocked; preserve manifest component permission guards.
- Add certificate-protected definitions for the OEM gate permissions needed by
  the app and its framework calls. Keep platform signing local to the ROM.
- Dispatch high-resolution frames to the native APS engine and use the YUV to
  JPEG path for ordinary photos. Keep the native capture sequence callbacks for APS.
- Use HAL mode `0x830b` for ordinary 4K30 and 60 fps video. The original 60 fps
  mode requested more encoder surface slots than the AOSP queue supports.
- Correct P010 plane layout in the matching OEM APS library and enable RAW10
  unpacking for the high-pixel capture mode.
- The SDKs are DEX-only `dex_import` modules. Keep their original manifest and
  XML runtime registration; disable app dexpreopt and its build-time
  `uses_libs` matching, which requires Java classpath libraries. Verify the
  actual JARs and XML mapping separately before runtime testing.
- Do not apply giulia's old BufferQueue register patch: lafa's Android 17 library
  already supplies the fence in the correct register.
- Do not apply hardcoded APS/HEIF byte offsets from another firmware.
- Omit the optional `liboplushwui_jni.so`: it imports 85 OEM rendering symbols not
  exported by the current AOSP `libhwui`. Its absence or optional UI paths still
  need runtime verification.
- Do not import the template's blanket SEPolicy or global hidden-API bypass.
  Any necessary device-specific policy must be supported by actual denial logs.

## ROM integration

Clone this tree at `vendor/oplus/camera`. The lafa device tree inherits
`lafa/opluscamera.mk` when `WITH_OPLUS_CAMERA=true`. For that product, add
`lafa/sepolicy` to `SYSTEM_EXT_PRIVATE_SEPOLICY_DIRS` and select the patched
camera unit configuration before inheriting the stock ODM copy.
`sm8850-common` supplies the `oplus-fwk` boot library.

The accompanying source changes in `hardware/oplus/oplus-fwk` and `frameworks/av`
are required. They add the Java wrappers, two verified OEM state constants, and
the CameraService extension loader. The server uses the same shared
`libcameraservice.so` as the extension to avoid duplicate service state.
The existing platform already supplies `com.oplus.util.OplusTypeCastingHelper`;
exclude the imported duplicate source from the `oplus-fwk` module. Preserve
normal hidden-API checking across the complete boot class path.
Only OEM Binder codes 10001–10022 enter the extension, after a camera signature
permission check. Standard CameraService transactions retain the existing path.

Extract from a local stock tree:

```bash
PYTHONPATH=tools/extract-utils python3 \
  vendor/oplus/camera/lafa/extract-files.py /path/to/stock-tree
```

The APK patch rejects unknown source hashes. Re-extracting never modifies the
input APK or input dump. To regenerate build files from already extracted blobs:

```bash
PYTHONPATH=tools/extract-utils python3 \
  vendor/oplus/camera/lafa/extract-files.py -m
```

Generate the camera unit configuration from the lafa vendor tree:

```bash
python3 vendor/oplus/camera/lafa/patch_camera_unit.py \
  vendor/realme/lafa/proprietary/odm/etc/camera/config/camera_unit_config \
  vendor/oplus/camera/lafa/blobs/proprietary/odm/etc/camera/config/camera_unit_config
```

Apply `patch_aps_library.py STOCK_LIBALGO_PROCESS OUTPUT_LIBALGO_PROCESS` with
LLVM tools in `PATH`. The script validates the OEM input hash. High-pixel
capture also depends on the matching vendor offline camera service, ODM APS
algorithms, and DSP libraries used on the test device.

Component validation (not an OTA build):

```bash
export WITH_OPLUS_CAMERA=true
source build/envsetup.sh
lunch uwu_lafa-cp2a-user
m -j4 OplusCamera oplus-fwk cameraserver libcameraservice libcamera_client \
  com.oplus.camera.unit.sdk com.oplus.camera.unit.sdk.adapter \
  libAPSClient-cmd-jni_oplus_camera libAPSClient-jni_oplus_camera \
  libNativeWinBuffExchange_oplus_camera libcsextimpl_oplus_camera
```

## Runtime validation boundary

An APK-only installation cannot supply the boot framework and native service
changes. Do not install this platform-signed APK over the manufacturer's camera
on official firmware. Use a separately bootable custom/DSU test system with
rollback available. Do not replace stock boot or vendor images for this test.

Verify app startup, preview, ordinary JPEG saving, lens switching, video and
gallery entry, then inspect crashes and SELinux denials. Specifically confirm
Aperture continues to work and that launching a gallery from the locked camera
cannot reveal older photos. A successful component build is not a claim that
these checks have passed.
