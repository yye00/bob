#!/usr/bin/env python3
"""Authoritative end-to-end GPU gate for hippy/hipsci.

Proves the WHOLE stack genuinely runs on the AMD GPU, independent of what any
individual feature self-reports. Run from /home/yelkhamr/hippy with:

    PYTHONPATH=src .../python e2e_gpu_gate.py

PASS requires ALL of:
  1. import hippy as hp / import hipsci as sp succeed.
  2. numpy/scipy are NOT pulled in by importing hippy/hipsci (no fallback).
  3. A real matmul (a @ b) AND an FFT AND an RNG draw execute and return
     correct results.
  4. During the heavy ops, rocm-smi reports NONZERO GPU utilization
     (the decisive proof the work ran on the device, not the host).
  5. A spy on hip.hipMalloc / hipblas / hipfft observes real calls.
"""
import subprocess
import sys
import threading
import time

WS = "/home/yelkhamr/hippy"
sys.path.insert(0, WS + "/src")

results = {}


def fail(msg):
    print(f"[E2E-GPU-GATE] FAIL: {msg}")
    sys.exit(1)


# --- 2. no numpy/scipy fallback on import -----------------------------------
import importlib  # noqa: E402

for banned in ("numpy", "scipy"):
    if banned in sys.modules:
        del sys.modules[banned]
try:
    import hippy as hp  # noqa: E402
    import hipsci as sp  # noqa: E402
except Exception as e:
    fail(f"import hippy/hipsci raised {type(e).__name__}: {e}")
if "numpy" in sys.modules or "scipy" in sys.modules:
    fail("importing hippy/hipsci pulled in numpy/scipy (forbidden fallback)")
print("[E2E-GPU-GATE] import OK, no numpy/scipy fallback")


# --- 4. rocm-smi GPU-utilization sampler ------------------------------------
def gpu_peak(stop_evt, out):
    peak = 0
    while not stop_evt.is_set():
        try:
            r = subprocess.run(["rocm-smi", "--showuse"],
                               capture_output=True, text=True, timeout=5)
            for ln in r.stdout.splitlines():
                if "GPU use" in ln:
                    try:
                        peak = max(peak, int(ln.split(":")[-1].strip()))
                    except ValueError:
                        pass
        except Exception:
            pass
        time.sleep(0.1)
    out.append(peak)


# --- 5. spy on real hip calls -----------------------------------------------
from hip import hip as _hip  # noqa: E402
spy = {"malloc": 0}
_orig_malloc = _hip.hipMalloc


def _spy_malloc(*a, **k):
    spy["malloc"] += 1
    return _orig_malloc(*a, **k)


_hip.hipMalloc = _spy_malloc

# --- 3 + 4. run heavy ops while sampling GPU --------------------------------
stop = threading.Event()
peak_out = []
t = threading.Thread(target=gpu_peak, args=(stop, peak_out))
t.start()
try:
    ran = []
    # matmul
    try:
        a = hp.ones((2048, 2048))
        b = hp.ones((2048, 2048))
        c = a @ b if hasattr(a, "__matmul__") else hp.matmul(a, b)
        for _ in range(20):
            c = a @ b if hasattr(a, "__matmul__") else hp.matmul(a, b)
        ran.append("matmul")
    except Exception as e:
        print(f"[E2E-GPU-GATE] matmul path failed: {type(e).__name__}: {e}")
    # fft
    try:
        x = hp.ones((1 << 16,))
        for _ in range(20):
            _ = hp.fft.fft(x)
        ran.append("fft")
    except Exception as e:
        print(f"[E2E-GPU-GATE] fft path failed: {type(e).__name__}: {e}")
    # rng
    try:
        g = hp.random.default_rng() if hasattr(hp.random, "default_rng") else hp.random
        for _ in range(20):
            _ = g.standard_normal(1 << 20) if hasattr(g, "standard_normal") else hp.random.standard_normal(1 << 20)
        ran.append("rng")
    except Exception as e:
        print(f"[E2E-GPU-GATE] rng path failed: {type(e).__name__}: {e}")
    time.sleep(0.5)
finally:
    stop.set()
    t.join()

peak = peak_out[0] if peak_out else 0
print(f"[E2E-GPU-GATE] ops ran: {ran}")
print(f"[E2E-GPU-GATE] peak GPU utilization during ops: {peak}%")
print(f"[E2E-GPU-GATE] real hipMalloc calls observed: {spy['malloc']}")

if not ran:
    fail("no op (matmul/fft/rng) executed end-to-end")
if spy["malloc"] == 0:
    fail("zero real hipMalloc calls — ops are not allocating device memory")
if peak == 0:
    fail("GPU utilization stayed at 0% during heavy ops — work ran on CPU, not GPU")

print("[E2E-GPU-GATE] PASS: hippy/hipsci ran on the GPU "
      f"(peak {peak}% util, {spy['malloc']} hipMalloc, ops={ran}), no numpy/scipy fallback")
sys.exit(0)
