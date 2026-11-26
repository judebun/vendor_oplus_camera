# SPDX-License-Identifier: Apache-2.0
# Opt-in lafa stock-camera port.
OPLUS_CAMERA_LAFA_PATH := vendor/oplus/camera/lafa

$(call soong_config_set,camera,target_ships_oplus_cam,true)
# This value is a HAL vendor metadata tag, not an Android package name.
$(call soong_config_set,camera,package_name,com.oplus.packageName)

PRODUCT_PACKAGES += \
    android.frameworks.cameraservice.common@2.0 \
    android.frameworks.cameraservice.device@2.0 \
    android.frameworks.cameraservice.service@2.2 \
    android.hardware.camera.provider@2.7 \
    android.hardware.camera.device-V4-ndk \
    android.hardware.camera.provider-V4-ndk \
    vendor.oplus.hardware.cameraextension-V1-ndk \
    vendor.oplus.hardware.urcc-V1-ndk \
    libcameraservice \
    libdynamic_depth

PRODUCT_COPY_FILES += \
    $(OPLUS_CAMERA_LAFA_PATH)/configs/permissions/oplus-camera-lafa.xml:$(TARGET_COPY_OUT_SYSTEM_EXT)/etc/permissions/oplus-camera-lafa.xml \
    $(OPLUS_CAMERA_LAFA_PATH)/configs/default-permissions/oplus-camera-lafa.xml:$(TARGET_COPY_OUT_SYSTEM_EXT)/etc/default-permissions/oplus-camera-lafa.xml \
    $(OPLUS_CAMERA_LAFA_PATH)/configs/init/init.oplus.camera-lafa.rc:$(TARGET_COPY_OUT_SYSTEM_EXT)/etc/init/init.oplus.camera-lafa.rc

PRODUCT_SYSTEM_EXT_PROPERTIES += \
    ro.oplus.system.camera.name=com.oplus.camera

PRODUCT_VENDOR_PROPERTIES += \
    persist.vendor.camera.privapp.list=com.oplus.camera \
    vendor.camera.skip_unconfigure.packagelist=com.oplus.camera \
    persist.vendor.oplus.quickjpeg.bypass=1

# sm8850-common already inherits oplus-fwk.mk on this device.
$(call inherit-product, $(OPLUS_CAMERA_LAFA_PATH)/blobs/blobs-vendor.mk)
