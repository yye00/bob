# SIMD Intrinsics and Autovectorization Hints

## What Is SIMD?

SIMD (Single Instruction, Multiple Data) processes multiple data elements in a single CPU instruction using wide registers:

| ISA | Register Width | Floats (f32) | Doubles (f64) |
|-----|---------------|-------------|--------------|
| SSE2 | 128-bit | 4 | 2 |
| AVX / AVX2 | 256-bit | 8 | 4 |
| AVX-512 | 512-bit | 16 | 8 |
| ARM NEON | 128-bit | 4 | 2 |
| ARM SVE | scalable | varies | varies |

## Autovectorization (Prefer This)

Let the compiler vectorize loops automatically — this is more portable and maintainable.

```c
// Compile with: gcc -O2 -march=native  OR  clang -O2 -march=native

// Simple loop — compiler will vectorize if aliasing can be ruled out
void add_arrays(float* restrict c, const float* restrict a, const float* restrict b, int n) {
    for (int i = 0; i < n; i++) c[i] = a[i] + b[i];
}
```

### Hints to Help the Compiler

```c
// __restrict__ / restrict: pointers do not alias
void saxpy(float* __restrict__ y, const float* __restrict__ x, float a, int n) {
    for (int i = 0; i < n; i++) y[i] += a * x[i];
}

// Alignment: aligned loads/stores are faster
float* buf = (float*)aligned_alloc(64, n * sizeof(float));  // 64-byte for AVX-512

// OpenMP SIMD pragma forces vectorization
#pragma omp simd
for (int i = 0; i < n; i++) c[i] = a[i] * b[i];

// GCC/Clang hint: assume aligned
__builtin_assume_aligned(ptr, 32);
```

### Compiler Flags

```bash
gcc  -O2 -march=native -ftree-vectorize -fopt-info-vec-optimized
clang -O2 -march=native -Rpass=loop-vectorize
icc  -O2 -xHost -vec-report=3
```

## x86 AVX2 Intrinsics

Include header: `#include <immintrin.h>`

```c
// Load 8 floats from memory (32-byte aligned)
__m256 va = _mm256_load_ps(a + i);     // aligned
__m256 va = _mm256_loadu_ps(a + i);    // unaligned (slightly slower)

// Arithmetic
__m256 vc = _mm256_add_ps(va, vb);     // c = a + b
__m256 vc = _mm256_mul_ps(va, vb);     // c = a * b
__m256 vc = _mm256_fmadd_ps(va, vb, vc); // c = a*b + c  (FMA, requires AVX2)

// Store
_mm256_store_ps(c + i, vc);            // aligned store
_mm256_storeu_ps(c + i, vc);           // unaligned store

// Full AVX2 vector_add loop
void avx2_add(float* c, const float* a, const float* b, int n) {
    int i = 0;
    for (; i <= n - 8; i += 8) {
        __m256 va = _mm256_loadu_ps(a + i);
        __m256 vb = _mm256_loadu_ps(b + i);
        _mm256_storeu_ps(c + i, _mm256_add_ps(va, vb));
    }
    for (; i < n; i++) c[i] = a[i] + b[i];  // scalar tail
}
```

## ARM NEON Intrinsics

Include header: `#include <arm_neon.h>`

```c
// Load 4 floats
float32x4_t va = vld1q_f32(a + i);
float32x4_t vb = vld1q_f32(b + i);

// Arithmetic
float32x4_t vc = vaddq_f32(va, vb);   // a + b
float32x4_t vc = vmulq_f32(va, vb);   // a * b
float32x4_t vc = vfmaq_f32(vc, va, vb); // c = c + a*b  (FMA)

// Store
vst1q_f32(c + i, vc);
```

## Horizontal Reduction

Summing all elements of a SIMD register:

```c
// AVX2 horizontal sum of __m256 (8 floats → 1 float)
float hsum_avx(__m256 v) {
    __m128 lo = _mm256_castps256_ps128(v);
    __m128 hi = _mm256_extractf128_ps(v, 1);
    lo = _mm_add_ps(lo, hi);
    lo = _mm_hadd_ps(lo, lo);
    lo = _mm_hadd_ps(lo, lo);
    return _mm_cvtss_f32(lo);
}
```

## Data Layout Considerations

- **AoS (Array of Structs)**: `{x,y,z,w, x,y,z,w, ...}` — difficult to vectorize a single field.
- **SoA (Struct of Arrays)**: `{x[N], y[N], z[N], w[N]}` — each array vectorizes perfectly.
- **AoSoA**: blocks of AoS sized to SIMD width — cache-friendly + vectorizable.

## Detecting CPU Features at Runtime

```c
#include <cpuid.h>
unsigned eax, ebx, ecx, edx;
__get_cpuid(1, &eax, &ebx, &ecx, &edx);
int has_sse4 = (ecx >> 19) & 1;

// Or use __builtin_cpu_supports (GCC/Clang)
if (__builtin_cpu_supports("avx2")) { /* use AVX2 path */ }
```

## Common Pitfalls

- **Alignment faults**: `_mm256_load_ps` requires 32-byte alignment; use `loadu` when unsure or unaligned.
- **Scalar tail**: SIMD loops must handle `n % vector_width` remainder elements separately.
- **Aliasing**: without `restrict`, compiler may insert runtime alias checks that defeat vectorization.
- **Uninitialized lanes**: partial loads into a SIMD register leave undefined values in unused lanes — initialize explicitly or use masked loads.
- **FMA availability**: `_mm256_fmadd_ps` requires AVX2 + FMA; guard with `#ifdef __FMA__` or runtime check.
