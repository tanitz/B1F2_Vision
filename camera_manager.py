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

import platform as _platform
if _platform.system() == "Windows":
    MVS_IMPORT = r"C:\Program Files (x86)\MVS\Development\Samples\Python\MvImport"
else:
    MVS_IMPORT = "/opt/MVS/Samples/64/Python/MvImport"

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

def _to_bgr(data: np.ndarray, frame_info):
    """numpy uint8 buffer → numpy BGR array."""
    w, h = frame_info.nWidth, frame_info.nHeight
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
        self.last_error   = ""
        self._frame_lock  = threading.Lock()  # serialize GetImageBuffer across threads

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
        Connect to a GigE camera by IP.
        Strategy: scan with EnumDevices first (correct GVSP stream setup),
        fall back to manual struct if not found in scan.
        """
        if not _sdk_ok:
            return False, f"MVS SDK unavailable: {_sdk_err}"
        self.disconnect()

        # ── Try enum-based connect first (proper GVSP stream channel setup) ──
        try:
            dl  = MV_CC_DEVICE_INFO_LIST()
            ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, dl)
            if ret == MV_OK and dl.nDeviceNum > 0:
                for i in range(dl.nDeviceNum):
                    di = cast(dl.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)).contents
                    if di.nTLayerType == MV_GIGE_DEVICE:
                        ip_i = di.SpecialInfo.stGigEInfo.nCurrentIp
                        found_ip = "%d.%d.%d.%d" % (
                            (ip_i>>24)&0xff, (ip_i>>16)&0xff,
                            (ip_i>>8) &0xff,  ip_i     &0xff)
                        if found_ip == camera_ip.strip():
                            print(f"[HikCamera] connect_by_ip: found {camera_ip} via EnumDevices → connecting by index {i}")
                            ok, msg = self._open_device_info(di)
                            if ok:
                                return True, f"Connected [{camera_ip}]"
                            # fall through to manual approach
        except Exception as ex:
            print(f"[HikCamera] connect_by_ip: EnumDevices error: {ex}")

        # ── Fallback: manual struct (requires correct net_ip for GVSP to work) ──
        print(f"[HikCamera] connect_by_ip: not found in scan, trying manual struct")
        try:
            stDevInfo         = MV_CC_DEVICE_INFO()
            stGigEDev         = MV_GIGE_DEVICE_INFO()
            stGigEDev.nCurrentIp = _ip_to_int(camera_ip)
            if net_ip.strip() and net_ip.strip() != "0.0.0.0":
                stGigEDev.nNetExport = _ip_to_int(net_ip.strip())
            stDevInfo.nTLayerType            = MV_GIGE_DEVICE
            stDevInfo.SpecialInfo.stGigEInfo = stGigEDev
            di = stDevInfo
            ok, msg = self._open_device_info(di)
            return ok, msg
        except Exception as ex:
            return False, str(ex)

    def _open_device_info(self, di) -> tuple[bool, str]:
        """Internal: open device from MV_CC_DEVICE_INFO, set packet size + TriggerMode=OFF."""
        try:
            cam = MvCamera()
            ret = cam.MV_CC_CreateHandle(di)
            if ret != MV_OK:
                return False, f"CreateHandle failed (0x{ret:x})"
            ret = cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
            if ret != MV_OK:
                cam.MV_CC_DestroyHandle()
                return False, f"OpenDevice failed (0x{ret:x})"
            pkt = cam.MV_CC_GetOptimalPacketSize()
            if pkt > 0:
                cam.MV_CC_SetIntValue("GevSCPSPacketSize", pkt)
            cam.MV_CC_SetEnumValue("PixelFormat", 0x02180014)  # RGB8_Packed — consistent color output
            cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_ON)
            self._cam       = cam
            self._connected = True
            return True, "Connected"
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
        di = cast(self._device_list.pDeviceInfo[index], POINTER(MV_CC_DEVICE_INFO)).contents
        ok, msg = self._open_device_info(di)
        if ok:
            name = self._cameras[index]["name"] if index < len(self._cameras) else str(index)
            return True, f"Connected [{name}]"
        return False, msg

    # ── Disconnect ────────────────────────────────────────────────────────────

    def disconnect(self):
        self._streaming = False
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

    # Trigger selector / source / activation enum maps (HikRobot GenICam names → int)
    _TRIG_SELECTOR_MAP = {
        "FrameStart":      0,
        "FrameBurstStart": 1,
    }
    _TRIG_SOURCE_MAP = {
        "Line0":    0,
        "Line1":    1,
        "Line2":    2,
        "Line3":    3,
        "Counter0": 4,
        "Software": 7,
    }
    _TRIG_ACTIVATION_MAP = {
        "RisingEdge":  0,
        "FallingEdge": 1,
        "AnyEdge":     2,
        "LevelHigh":   3,
        "LevelLow":    4,
    }
    _TRIG_SELECTOR_INV    = {v: k for k, v in _TRIG_SELECTOR_MAP.items()}
    _TRIG_SOURCE_INV      = {v: k for k, v in _TRIG_SOURCE_MAP.items()}
    _TRIG_ACTIVATION_INV  = {v: k for k, v in _TRIG_ACTIVATION_MAP.items()}

    def get_trigger_params(self) -> dict | None:
        """Read IO trigger settings. Returns dict or None on error.
        Nodes that are not supported by the camera model are silently skipped."""
        if not self._connected:
            return None

        MV_E_NOTSUPPORT = 0x80000106

        class _EnumVal(Structure):
            _fields_ = [("nCurValue",    c_uint32),
                        ("nSupportedNum",c_uint32),
                        ("nSupportValue",c_uint32 * 64)]

        def ge(name, default=0):
            ev = _EnumVal()
            memset(byref(ev), 0, sizeof(ev))
            ret = self._cam.MV_CC_GetEnumValue(name, ev)
            if ret != MV_OK:
                print(f"[HikCamera] get_trigger_params: {name} skipped (0x{ret:x})")
                return default
            return ev.nCurValue

        def gf(name, default=0.0):
            v = MVCC_FLOATVALUE()
            memset(byref(v), 0, sizeof(MVCC_FLOATVALUE))
            ret = self._cam.MV_CC_GetFloatValue(name, v)
            if ret != MV_OK:
                print(f"[HikCamera] get_trigger_params: {name} skipped (0x{ret:x})")
                return default
            return v.fCurValue

        try:
            sel  = ge("TriggerSelector", 0)
            mode = ge("TriggerMode",     1)
            src  = ge("TriggerSource",   0)
            act  = ge("TriggerActivation", 0)
            dly  = gf("TriggerDelay",    0.0)
            return {
                "trigger_selector":   self._TRIG_SELECTOR_INV.get(sel,   "FrameStart"),
                "trigger_mode":       "On" if mode == 1 else "Off",
                "trigger_source":     self._TRIG_SOURCE_INV.get(src,     "Line0"),
                "trigger_activation": self._TRIG_ACTIVATION_INV.get(act, "RisingEdge"),
                "trigger_delay":      round(dly, 4),
            }
        except Exception as ex:
            print(f"[HikCamera] get_trigger_params: {ex}")
            return None

    def set_trigger_params(self, trigger_selector: str = "FrameStart",
                           trigger_mode: str = "Off",
                           trigger_source: str = "Line0",
                           trigger_activation: str = "RisingEdge",
                           trigger_delay: float = 0.0) -> tuple[bool, str]:
        """Apply IO trigger settings. Returns (ok, message).
        Nodes not supported by the camera (MV_E_NOTSUPPORT) are silently skipped."""
        if not self._connected:
            return False, "Not connected"

        MV_E_NOTSUPPORT = 0x80000106

        def _set_enum(name, val):
            ret = self._cam.MV_CC_SetEnumValue(name, val)
            if ret not in (MV_OK, MV_E_NOTSUPPORT):
                raise RuntimeError(f"{name} error (0x{ret:x})")
            if ret == MV_E_NOTSUPPORT:
                print(f"[HikCamera] set_trigger_params: {name} not supported, skipped")

        def _set_float(name, val):
            ret = self._cam.MV_CC_SetFloatValue(name, float(val))
            if ret not in (MV_OK, MV_E_NOTSUPPORT):
                raise RuntimeError(f"{name} error (0x{ret:x})")
            if ret == MV_E_NOTSUPPORT:
                print(f"[HikCamera] set_trigger_params: {name} not supported, skipped")

        try:
            sel_val = self._TRIG_SELECTOR_MAP.get(trigger_selector, 0)
            src_val = self._TRIG_SOURCE_MAP.get(trigger_source, 0)
            act_val = self._TRIG_ACTIVATION_MAP.get(trigger_activation, 0)
            mode_on = trigger_mode == "On"

            _set_enum("TriggerSelector", sel_val)
            _set_enum("TriggerMode", 1 if mode_on else 0)
            if mode_on:
                _set_enum("TriggerSource",     src_val)
                _set_enum("TriggerActivation", act_val)
            _set_float("TriggerDelay", trigger_delay)
            return True, "Trigger settings applied"
        except RuntimeError as ex:
            return False, str(ex)
        except Exception as ex:
            return False, str(ex)

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

    def start_streaming(self, trigger_on=True, preserve_trigger=False) -> tuple[bool, str]:
        """Start continuous grabbing.
        trigger_on=True  : set TriggerMode=On + TriggerSource=Line0 (default hardware).
        preserve_trigger : if True, skip touching TriggerMode/Source (use already-applied settings).
        """
        if not self._connected:
            return False, "Not connected"
        try:
            # Always stop first so we start from a clean state
            try: self._cam.MV_CC_StopGrabbing()
            except Exception: pass
            self._streaming = False
            if not preserve_trigger:
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
        """Get one frame from streaming buffer. Returns numpy BGR or None.
        Thread-safe via _frame_lock (prevents concurrent MV_E_RESOURCE from two threads)."""
        if not self._connected or not self._cam or not self._streaming:
            return None
        if not self._frame_lock.acquire(timeout=timeout_ms / 1000.0 + 0.5):
            return None  # another thread is already waiting
        try:
            stOutFrame = MV_FRAME_OUT()
            memset(byref(stOutFrame), 0, sizeof(stOutFrame))
            ret = self._cam.MV_CC_GetImageBuffer(stOutFrame, timeout_ms)
            if ret != MV_OK:
                _silent = {
                    0x80000007,  # MV_E_WAIT  — trigger timeout (normal)
                    0x80000003,  # MV_E_CALLORDER / MV_E_NODATA — no frame yet (Linux SDK)
                }
                if ret not in _silent:
                    print(f"[HikCamera] get_frame: GetImageBuffer ret=0x{ret:x}")
                return None
            if not stOutFrame.pBufAddr:
                print("[HikCamera] get_frame: pBufAddr is NULL")
                return None
            fi  = stOutFrame.stFrameInfo
            n   = fi.nFrameLen
            buf = np.empty(n, dtype=np.uint8)
            memmove(buf.ctypes.data, stOutFrame.pBufAddr, n)
            self._cam.MV_CC_FreeImageBuffer(stOutFrame)
            return _to_bgr(buf, fi)
        except Exception as ex:
            print(f"[HikCamera] get_frame: {ex}")
            return None
        finally:
            self._frame_lock.release()

    # ── Grab one frame ────────────────────────────────────────────────────────

    def grab_one(self):
        """Grab single frame via software trigger → numpy BGR or None.
        Pattern: TriggerMode=1, TriggerSource=7(Software), fire TriggerSoftware command.
        Check .last_error on None return.
        """
        self.last_error = ""
        if not self._connected or not self._cam:
            self.last_error = "Not connected"
            print(f"[HikCamera] grab_one: {self.last_error}")
            return None
        try:
            # Stop any ongoing stream so we own the grabbing state
            if self._streaming:
                print("[HikCamera] grab_one: stopping existing stream first")
                self._cam.MV_CC_StopGrabbing()
                self._streaming = False

            # Software trigger mode (TriggerSource=7 = Software)
            ret = self._cam.MV_CC_SetEnumValue("TriggerMode", 1)
            print(f"[HikCamera] grab_one: TriggerMode→1  ret=0x{ret:x}")
            ret = self._cam.MV_CC_SetEnumValue("TriggerSource", 7)
            print(f"[HikCamera] grab_one: TriggerSource→7(Software)  ret=0x{ret:x}")

            ret = self._cam.MV_CC_StartGrabbing()
            if ret != MV_OK:
                self.last_error = f"StartGrabbing failed (0x{ret:x})"
                print(f"[HikCamera] grab_one: {self.last_error}")
                return None
            print("[HikCamera] grab_one: grabbing started")

            # Fire software trigger
            ret = self._cam.MV_CC_SetCommandValue("TriggerSoftware")
            print(f"[HikCamera] grab_one: TriggerSoftware fired  ret=0x{ret:x}")

            stOutFrame = MV_FRAME_OUT()
            memset(byref(stOutFrame), 0, sizeof(stOutFrame))
            ret = self._cam.MV_CC_GetImageBuffer(stOutFrame, 3000)

            if ret != MV_OK or not stOutFrame.pBufAddr:
                self.last_error = f"GetImageBuffer failed (0x{ret:x})"
                print(f"[HikCamera] grab_one: {self.last_error}")
                self._cam.MV_CC_StopGrabbing()
                return None

            fi = stOutFrame.stFrameInfo
            n  = fi.nFrameLen
            print(f"[HikCamera] grab_one: frame {fi.nWidth}x{fi.nHeight} "
                  f"pixelType=0x{fi.enPixelType:x} len={n}")

            # Copy out before freeing SDK buffer
            buf = (c_ubyte * n)()
            memmove(buf, stOutFrame.pBufAddr, n)
            self._cam.MV_CC_FreeImageBuffer(stOutFrame)
            self._cam.MV_CC_StopGrabbing()

            frame = _to_bgr(buf, fi)
            if frame is None:
                self.last_error = f"Pixel conversion failed (pixelType=0x{fi.enPixelType:x})"
                print(f"[HikCamera] grab_one: {self.last_error}")
            return frame
        except Exception as ex:
            self.last_error = str(ex)
            print(f"[HikCamera] grab_one exception: {ex}")
            import traceback; traceback.print_exc()
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
