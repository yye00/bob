# ROCm / HIP Programming Patterns

## Overview

ROCm (Radeon Open Compute) is AMD's open-source HPC GPU platform. HIP (Heterogeneous-compute Interface for Portability) is its primary kernel language, designed to be syntactically close to CUDA so code can be ported with minimal changes.

## HIP Kernel Anatomy

```cpp
#include <hip/hip_runtime.h>

// hipcc compiles this
__global__ void vector_add(const float* a, const float* b, float* c, int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < n) c[idx] = a[idx] + b[idx];
}
```

## Launch Configuration

```cpp
int n = 1 << 20;
int block_size = 256;
int grid_size  = (n + block_size - 1) / block_size;

hipLaunchKernelGGL(vector_add, dim3(grid_size), dim3(block_size), 0, 0,
                   d_a, d_b, d_c, n);
hipDeviceSynchronize();

// Or using CUDA-like triple-chevron syntax (supported in HIP)
vector_add<<<dim3(grid_size), dim3(block_size)>>>(d_a, d_b, d_c, n);
```

## Memory Management

```cpp
float *d_a;
hipMalloc(&d_a, n * sizeof(float));
hipMemcpy(d_a, h_a, n * sizeof(float), hipMemcpyHostToDevice);
// ... kernel ...
hipMemcpy(h_a, d_a, n * sizeof(float), hipMemcpyDeviceToHost);
hipFree(d_a);
```

### Unified Memory

```cpp
float *data;
hipMallocManaged(&data, n * sizeof(float));
// accessible from host and device
hipFree(data);
```

## Shared Memory Tiling

Shared memory syntax is identical to CUDA:

```cpp
#define TILE 32
__global__ void matmul(const float* A, const float* B, float* C, int N) {
    __shared__ float tA[TILE][TILE];
    __shared__ float tB[TILE][TILE];
    // ... same tiling pattern as CUDA ...
    __syncthreads();  // same barrier primitive
}
```

## CUDA → HIP Migration Map

| CUDA | HIP |
|------|-----|
| `cudaMalloc` | `hipMalloc` |
| `cudaMemcpy` | `hipMemcpy` |
| `cudaFree` | `hipFree` |
| `cudaDeviceSynchronize` | `hipDeviceSynchronize` |
| `cudaMemcpyHostToDevice` | `hipMemcpyHostToDevice` |
| `__syncthreads` | `__syncthreads` (same) |
| `cudaStream_t` | `hipStream_t` |
| `cudaEvent_t` | `hipEvent_t` |
| `nvcc` | `hipcc` |

The tool `hipify-perl` or `hipify-clang` automates most of this translation.

## Warp-Level Operations

HIP uses "wavefronts" of 64 threads (AMD GCN/CDNA) vs CUDA's 32-thread warps.

```cpp
// HIP warp shuffle (wavefront-aware)
float val = __shfl_down(val, offset);       // within a wavefront

// For portability, check warpSize at runtime:
int ws = __AMDGCN_WAVEFRONT_SIZE;  // 32 or 64 depending on arch
```

## Error Checking Pattern

```cpp
#define HIP_CHECK(call) \
    do { \
        hipError_t err = (call); \
        if (err != hipSuccess) { \
            fprintf(stderr, "HIP error %s:%d: %s\n", __FILE__, __LINE__, \
                    hipGetErrorString(err)); \
            exit(1); \
        } \
    } while (0)
```

## ROCm Libraries

| Library | Purpose | CUDA equivalent |
|---------|---------|----------------|
| `rocBLAS` | Dense linear algebra | cuBLAS |
| `rocFFT` | Fast Fourier Transform | cuFFT |
| `rocSPARSE` | Sparse linear algebra | cuSPARSE |
| `MIOpen` | Deep learning primitives | cuDNN |
| `rocRAND` | Random number generation | cuRAND |
| `rocThrust` | Parallel algorithms | Thrust |

## Build System

```cmake
# CMakeLists.txt for HIP
find_package(hip REQUIRED)
add_executable(myapp main.cpp kernel.cpp)
set_source_files_properties(kernel.cpp PROPERTIES LANGUAGE HIP)
target_link_libraries(myapp hip::device)
```

```bash
# Manual compile
hipcc -O3 -o myapp main.cpp kernel.cpp
```

## Common Pitfalls

- **Wavefront size**: AMD hardware uses 64-thread wavefronts by default; CUDA shuffle code assuming 32-thread warps needs adaptation.
- **Register pressure**: AMD architectures have different occupancy tradeoffs; profile with `rocprof`.
- **Library API differences**: rocBLAS uses column-major by default (same as cuBLAS), but error codes differ.
- **Missing `hipDeviceSynchronize`**: async kernels complete silently; always synchronize before timing or reading results.
