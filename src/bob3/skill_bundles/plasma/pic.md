# Particle-in-Cell (PIC) Method

## PIC Algorithm Overview

```
Each timestep:
1. Scatter charges from particles to grid   (charge deposition)
2. Solve field equations on grid             (Poisson / Maxwell)
3. Gather fields from grid to particles      (field interpolation)
4. Push particle positions and momenta       (equations of motion)
```

## Particle Data Layout

```python
# Structure of Arrays (SoA) — cache-friendly for SIMD
class ParticleArray:
    x:  np.ndarray   # positions  [n_particles, 3]
    p:  np.ndarray   # momenta    [n_particles, 3]  (relativistic: γm v)
    q:  float        # charge per macro-particle
    m:  float        # mass per macro-particle
```

## Charge Deposition (Cloud-in-Cell, 1st-order)

```python
def deposit_charge(x, q, grid, dx):
    """1st-order linear interpolation (Cloud-in-Cell)."""
    rho = np.zeros(grid.shape)
    for xi, qi in zip(x, q):
        i = int(xi / dx)
        wx = xi/dx - i           # weight to right cell
        rho[i]   += qi * (1 - wx)
        rho[i+1] += qi * wx
    return rho / dx
```

## Higher-Order Shapes (B-splines)

| Shape  | Order | Width | Peak-to-noise |
|--------|-------|-------|---------------|
| NGP    | 0     | 1Δx   | Highest noise |
| CIC    | 1     | 2Δx   | Moderate      |
| TSC    | 2     | 3Δx   | Lower noise   |
| PCS    | 3     | 4Δx   | Smoothest     |

## Poisson Solver (Electrostatic PIC)

```python
def solve_poisson_fft(rho, dx, epsilon_0=1.0):
    """Spectral Poisson solve: ∇²φ = -ρ/ε₀."""
    n = len(rho)
    rho_k = np.fft.rfft(rho)
    k = 2*np.pi*np.fft.rfftfreq(n, dx)
    k[0] = 1.0            # avoid division by zero for DC component
    phi_k = rho_k / (epsilon_0 * k**2)
    phi_k[0] = 0.0        # zero mean potential
    return np.fft.irfft(phi_k)
```

## Particle Pushing (Leapfrog)

```python
def push_leapfrog(x, v, E, q, m, dt):
    """Non-relativistic leapfrog (Störmer-Verlet)."""
    # v at half-integer timestep
    v_half = v + 0.5 * (q/m) * E * dt
    x_new  = x + v_half * dt
    v_new  = v_half + 0.5 * (q/m) * gather_field(E, x_new) * dt
    return x_new, v_new
```

## Macro-Particle Weighting

Physical particles per macro-particle = N_phys / N_sim. Choose:

```
N_sim per cell = 10–100 for good statistics (sqrt(N) noise ~ 3–10%)
```

## Common Pitfalls

- **Grid heating**: artificial heating from aliasing; use higher-order shapes or current smoothing.
- **Nyquist modes**: ensure λ_Debye ≥ Δx for stable electrostatic PIC.
- **Energy conservation**: leapfrog conserves (discrete) energy; check drift over many timesteps.
- **Particle loss**: apply periodic or reflecting boundaries explicitly.
