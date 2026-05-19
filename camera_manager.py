"""
HikRobot GigE / USB3 camera manager via MVS SDK.
Supports connecting by IP address directly (no RTSP).
"""
import json
import os
import sys
import time
import threading
import numpy as np
import cv2
from ctypes import *

MVS_IMPORT   = r"C:\Program Files (x86)\MVS\Development\Samples\Python\MvImport"
_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_BASE_DIR, "config", "camera.json")

DEFAULT_CONFIG = {
    "camera_ip": "192.168.1.64",
    "net_ip":    "",            # host NIC IP — blank = auto
}

_sdk_ok  = False
_sdk_err = ""

try:
    if MVS_IMPORT not in sys.path:
        sys.path.insert(0, MVS_IMPORT)
    from MvCameraControl_class import *   # MvCamera, MV_CC_DEVICE_INFO, ...
    from CameraParams_header import *     # MVCC_FLOATVALUE, MV_FRAME_OUT_INFO_EX, ...
    _sdk_ok = True
except Exception as _e:
    _sdk_err = str(_e)


# ── Config helpers ────────────────────────────────────────────────────────────

def load_config() -> dict:
    if os.path.isfile(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict):
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ── Pixel conversion ──────────────────────────────────────────────────────────

def _to_bgr(buf, frame_info):
    """Raw frame buffer → numpy BGR array."""
    w, h, n = frame_info.nWidth, frame_info.nHeight, frame_info.nFrameLen
    data = np.frombuffer(buf, dtype=np.uint8, count=n)
    pt   = frame_info.enPixelType
    try:
        if   pt == 0x01080001: return cv2.cvtColor(data.reshape(h, w), cv2.COLOR_GRAY2BGR)
        elif pt == 0x01080009: return cv2.cvtColor(data.reshape(h, w), cv2.COLOR_BayerRG2BGR)
        elif pt == 0x01080008: return cv2.cvtColor(data.reshape(h, w), cv2.COLOR_BayerGR2BGR)
        elif pt == 0x0108000A: return cv2.cvtColor(data.reshape(h, w), cv2.COLOR_BayerGB2BGR)
        elif pt == 0x0108000B: return cv2.cvtColor(data.reshape(h, w), cv2.COLOR_BayerBG2BGR)
        elif pt == 0x02180014: return cv2.cvtColor(data[:h*w*3].reshape(h, w, 3), cv2.COLOR_RGB2BGR)
        elif pt == 0x02180015: return data[:h*w*3].reshape(h, w, 3).copy()
        else:                  return cv2.cvtColor(data[:h*w].reshape(h, w), cv2.COLOR_GRAY2BGR)
    except Exception as ex:
        print(f"[HikCamera] _to_bgr error (pt=0x{pt:x}): {ex}")
        return None


def _ip_to_int(ip: str) -> int:
    parts = ip.strip().split(".")
    return (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])


# ── Camera class ──────────────────────────────────────────────────────────────

class HikCamera:
    """HikRobot GigE / USB3 camera via MVS SDK."""

    def __init__(self):
        self._cam         = None
        self._connected   = False
        self._streaming   = False
        self._device_list = None
        self._cameras     = []

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def cameras(self) -> list:
        return self._cameras

    @staticmethod
    def sdk_ok() -> bool:
        return _sdk_ok

    @staticmethod
    def sdk_err() -> str:
        return _sdk_err

    # ── Enumerate ─────────────────────────────────────────────────────────────

    def enum_devices(self) -> list:
        """Scan network for GigE + USB3 cameras."""
        if not _sdk_ok:
            return []
        dl  = MV_CC_DEVICE_INFO_LIST()
        ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, dl)
        self._device_list = dl if ret == MV_OK else None
        self._cameras = []
        if ret != MV_OK or not self._device_list:
            return []
        for i in range(dl.nDeviceNum):
            di = cast(dl.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)).contents
            if di.nTLayerType == MV_GIGE_DEVICE:
                name  = bytes(di.SpecialInfo.stGigEInfo.chModelName).split(b"\x00")[0].decode("utf-8", errors="ignore")
                ip_i  = di.SpecialInfo.stGigEInfo.nCurrentIp
                ip    = "%d.%d.%d.%d" % ((ip_i>>24)&0xff,(ip_i>>16)&0xff,(ip_i>>8)&0xff,ip_i&0xff)
                self._cameras.append({"index": i, "type": "GigE", "name": name, "ip": ip})
            elif di.nTLayerType == MV_USB_DEVICE:
                name = bytes(di.SpecialInfo.stUsb3VInfo.chModelName).split(b"\x00")[0].decode("utf-8", errors="ignore")
                sn   = bytes(di.SpecialInfo.stUsb3VInfo.chSerialNumber).split(b"\x00")[0].decode("utf-8", errors="ignore")
                self._cameras.append({"index": i, "type": "USB3", "name": name, "ip": sn})
        return self._cameras

    # ── Connect by IP ─────────────────────────────────────────────────────────

    def connect_by_ip(self, camera_ip: str, net_ip: str = "") -> tuple[bool, str]:
        """
        Connect to a GigE camera directly by its IP address.
        net_ip: IP of host NIC connected to camera (blank = auto).
        """
        if not _sdk_ok:
            return False, f"MVS SDK unavailable: {_sdk_err}"
        self.disconnect()
        try:
            stDevInfo         = MV_CC_DEVICE_INFO()
            stGigEDev         = MV_GIGE_DEVICE_INFO()
            stGigEDev.nCurrentIp = _ip_to_int(camera_ip)
            if net_ip.strip() and net_ip.strip() != "0.0.0.0":
                stGigEDev.nNetExport = _ip_to_int(net_ip.strip())
            stDevInfo.nTLayerType           = MV_GIGE_DEVICE
            stDevInfo.SpecialInfo.stGigEInfo = stGigEDev

            cam = MvCamera()
            ret = cam.MV_CC_CreateHandle(stDevInfo)
            if ret != MV_OK:
                return False, f"CreateHandle failed (0x{ret:x})"
            ret = cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
            if ret != MV_OK:
                cam.MV_CC_DestroyHandle()
                return False, f"OpenDevice failed (0x{ret:x})"

            pkt = cam.MV_CC_GetOptimalPacketSize()
            if pkt > 0:
                cam.MV_CC_SetIntValue("GevSCPSPacketSize", pkt)

            cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
            self._cam       = cam
            self._connected = True
            return True, f"Connected  [{camera_ip}]"
        except Exception as ex:
            return False, str(ex)

    # ── Connect by index (from enum) ──────────────────────────────────────────

    def connect_by_index(self, index: int) -> tuple[bool, str]:
        """Connect to enumerated device at index."""
        if not _sdk_ok:
            return False, f"MVS SDK unavailable: {_sdk_err}"
        if not self._device_list or index >= self._device_list.nDeviceNum:
            return False, "Please scan first."
        self.disconnect()
        try:
            di  = cast(self._device_list.pDeviceInfo[index], POINTER(MV_CC_DEVICE_INFO)).contents
            cam = MvCamera()
            ret = cam.MV_CC_CreateHandle(di)
            if ret != MV_OK:
                return False, f"CreateHandle failed (0x{ret:x})"
            ret = cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
            if ret != MV_OK:
                cam.MV_CC_DestroyHandle()
                return False, f"OpenDevice failed (0x{ret:x})"
            if di.nTLayerType == MV_GIGE_DEVICE:
                pkt = cam.MV_CC_GetOptimalPacketSize()
                if pkt > 0:
                    cam.MV_CC_SetIntValue("GevSCPSPacketSize", pkt)
            cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
            self._cam       = cam
            self._connected = True
            name = self._cameras[index]["name"] if index < len(self._cameras) else str(index)
            return True, f"Connected  [{name}]"
        except Exception as ex:
            return False, str(ex)

    # ── Disconnect ────────────────────────────────────────────────────────────

    def disconnect(self):
        if self._cam:
            try: self._cam.MV_CC_StopGrabbing()
            except Exception: pass
            try: self._cam.MV_CC_CloseDevice()
            except Exception: pass
            try: self._cam.MV_CC_DestroyHandle()
            except Exception: pass
            self._cam = None
        self._connected = False

    # ── Parameters ────────────────────────────────────────────────────────────

    def get_params(self) -> dict | None:
        """Returns {exposure, gain, frame_rate} or None."""
        if not self._connected:
            return None
        try:
            def gf(name):
                v = MVCC_FLOATVALUE()
                memset(byref(v), 0, sizeof(MVCC_FLOATVALUE))
                self._cam.MV_CC_GetFloatValue(name, v)
                return v.fCurValue
            return {
                "exposure":   gf("ExposureTime"),
                "gain":       gf("Gain"),
                "frame_rate": gf("AcquisitionFrameRate"),
            }
        except Exception as ex:
            print(f"[HikCamera] get_params: {ex}")
            return None

    def set_params(self, exposure=None, gain=None, frame_rate=None, trigger_on=False) -> tuple[bool, str]:
        """Returns (ok, message)."""
        if not self._connected:
            return False, "Not connected"
        try:
            if exposure is not None:
                self._cam.MV_CC_SetEnumValue("ExposureAuto", 0)
                time.sleep(0.05)
                ret = self._cam.MV_CC_SetFloatValue("ExposureTime", float(exposure))
                if ret != MV_OK:
                    return False, f"Exposure error (0x{ret:x})"
            if gain is not None:
                ret = self._cam.MV_CC_SetFloatValue("Gain", float(gain))
                if ret != MV_OK:
                    return False, f"Gain error (0x{ret:x})"
            if frame_rate is not None:
                ret = self._cam.MV_CC_SetFloatValue("AcquisitionFrameRate", float(frame_rate))
                if ret != MV_OK:
                    return False, f"FrameRate error (0x{ret:x})"
            self._cam.MV_CC_SetEnumValue("TriggerMode", 1 if trigger_on else 0)
            return True, "Parameters applied"
        except Exception as ex:
            return False, str(ex)

    # ── Streaming (hardware trigger) ──────────────────────────────────────────

    def start_streaming(self, trigger_on=True) -> tuple[bool, str]:
        """Start continuous grabbing. trigger_on=True enables hardware Line0 trigger."""
        if not self._connected:
            return False, "Not connected"
        try:
            self._cam.MV_CC_SetEnumValue("TriggerMode", 1 if trigger_on else 0)
            if trigger_on:
                self._cam.MV_CC_SetEnumValue("TriggerSource", 0)  # Line0
            ret = self._cam.MV_CC_StartGrabbing()
            if ret != MV_OK:
                return False, f"StartGrabbing failed (0x{ret:x})"
            self._streaming = True
            return True, "Streaming started"
        except Exception as ex:
            return False, str(ex)

    def stop_streaming(self):
        """Stop grabbing."""
        self._streaming = False
        if self._cam:
            try:
                self._cam.MV_CC_StopGrabbing()
            except Exception:
                pass

    def get_frame(self, timeout_ms: int = 2000):
        """Get one frame from the streaming buffer. Returns numpy BGR or None on timeout/error."""
        if not self._connected or not self._cam or not self._streaming:
            return None
        try:
            pv = MVCC_INTVALUE_EX()
            memset(byref(pv), 0, sizeof(MVCC_INTVALUE_EX))
            if self._cam.MV_CC_GetIntValueEx("PayloadSize", pv) != MV_OK:
                return None
            size = int(pv.nCurValue)
            buf  = (c_ubyte * size)()
            fi   = MV_FRAME_OUT_INFO_EX()
            memset(byref(fi), 0, sizeof(MV_FRAME_OUT_INFO_EX))
            ret = self._cam.MV_CC_GetOneFrameTimeout(buf, size, fi, timeout_ms)
            if ret != MV_OK:
                return None
            return _to_bgr(buf, fi)
        except Exception as ex:
            print(f"[HikCamera] get_frame: {ex}")
            return None

    # ── Grab one frame ────────────────────────────────────────────────────────

    def grab_one(self):
        """Grab single frame → numpy BGR or None."""
        if not self._connected or not self._cam:
            return None
        try:
            pv = MVCC_INTVALUE_EX()
            memset(byref(pv), 0, sizeof(MVCC_INTVALUE_EX))
            if self._cam.MV_CC_GetIntValueEx("PayloadSize", pv) != MV_OK:
                return None
            size = int(pv.nCurValue)
            buf  = (c_ubyte * size)()

            if self._cam.MV_CC_StartGrabbing() != MV_OK:
                return None
            fi  = MV_FRAME_OUT_INFO_EX()
            memset(byref(fi), 0, sizeof(MV_FRAME_OUT_INFO_EX))
            ret = self._cam.MV_CC_GetOneFrameTimeout(buf, size, fi, 3000)
            self._cam.MV_CC_StopGrabbing()

            if ret != MV_OK:
                return None
            return _to_bgr(buf, fi)
        except Exception as ex:
            print(f"[HikCamera] grab_one: {ex}")
            try: self._cam.MV_CC_StopGrabbing()
            except Exception: pass
            return None


# ── Singleton ─────────────────────────────────────────────────────────────────
_instance: HikCamera | None = None


def get_camera() -> HikCamera:
    global _instance
    if _instance is None:
        _instance = HikCamera()
    return _instance
