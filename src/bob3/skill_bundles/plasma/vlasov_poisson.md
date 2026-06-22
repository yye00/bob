# Vlasov-Poisson System

## Governing Equations

The Vlasov equation describes collisionless kinetic plasma:

```
∂f/∂t + v·∇_x f + (q/m)(E + v×B)·∇_v f = 0

f(x, v, t): distribution function (particles per phase-space volume)
E, B: electromagnetic fields

Coupled with Poisson:
∇²φ = -ρ/ε₀ = -(q/ε₀) ∫ f dv
E = -∇φ
```

## Semi-Lagrangian Method (Backward Advection)

Trace characteristics backward in time; no CFL restriction:

```python
def semi_lagrangian_step(f, x_grid, v_grid, E, dt, q_over_m):
    """Advect distribution function f using backward tracing."""
    f_new = np.zeros_like(f)
    for i, xi in enumerate(x_grid):
        for j, vj in enumerate(v_grid):
            # Trace backward along characteristic
            x_dep = xi - vj * dt
            v_dep = vj - q_over_m * E[i] * dt
            # Interpolate f at departure point
            f_new[i, j] = bilinear_interp(f, x_dep, v_dep, x_grid, v_grid)
    return f_new
```

## Fourier Spectral Method (Periodic)

Efficient for periodic domains:

```python
def vlasov_spectral_rhs(f_hat, k_x, k_v, E_hat, q_over_m):
    """RHS of Vlasov in Fourier space."""
    # ∂f/∂t = -v ∂f/∂x - (q/m) E ∂f/∂v
    df_dx_hat = 1j * k_x * f_hat
    df_dv_hat = 1j * k_v * f_hat
    # Convolution theorem for E * ∂f/∂v
    rhs_hat = -v_grid * df_dx_hat - q_over_m * ifft(fft(E) * df_dv_hat)
    return rhs_hat
```

## Landau Damping (Linear Theory Verification)

Landau damping rate for electron plasma wave:

```python
def landau_damping_rate(k, v_th, omega_pe):
    """Approximate Landau damping rate γ for wavenumber k.
    
    Valid for k λ_D << 1 (long-wavelength limit).
    """
    lambda_D = v_th / omega_pe
    x = 1.0 / (k * lambda_D * np.sqrt(2))
    # Asymptotic: γ = -sqrt(π/8) * omega_pe/(k*lambda_D)^3 * exp(-1/(2k²λ_D²))
    gamma = -np.sqrt(np.pi/8) * omega_pe / (k*lambda_D)**3 * np.exp(-x**2)
    omega_r = omega_pe * (1 + 1.5*(k*lambda_D)**2)   # real frequency
    return omega_r, gamma
```

## Conservation Laws

```python
def kinetic_energy(f, v_grid, dv):
    """Total kinetic energy: Ek = ∫ 0.5 m v² f dv dx"""
    return 0.5 * np.sum(v_grid**2 * f) * dv

def entropy(f, dv):
    """Boltzmann entropy: S = -∫ f ln(f) dv dx (avoid log(0))"""
    mask = f > 0
    return -np.sum(f[mask] * np.log(f[mask])) * dv
```

## Common Pitfalls

- **Filamentation**: f develops fine structures in v → requires phase-space filtering or higher resolution.
- **Recurrence**: spectral methods show recurrence at t = 2π/(k Δv); use dealiasing or hyperviscosity.
- **Charge conservation**: ensure ∫f dv = ρ/q at each timestep.
- **Negative f**: positivity-preserving limiters needed for finite-difference schemes.
