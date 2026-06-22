# Magnetohydrodynamics (MHD)

## Ideal MHD Equations

Conservation form (single fluid, perfectly conducting):

```
∂ρ/∂t   + ∇·(ρv) = 0
∂(ρv)/∂t + ∇·(ρvv - BB + (p + B²/2)I) = 0    (momentum)
∂e/∂t   + ∇·((e + p + B²/2)v - (v·B)B) = 0    (energy)
∂B/∂t   - ∇×(v×B) = 0                           (induction)
∇·B = 0                                           (div-free constraint)

e = p/(γ-1) + ρv²/2 + B²/2   (total energy density)
```

## Constraint Transport (∇·B = 0)

Maintain divergence-free B using constrained transport on Yee-staggered grid:

```python
def constrained_transport_update(B, E_edge, dx, dy, dt):
    """CT update preserves ∇·B = 0 to machine precision."""
    # B is face-centered; E is edge-centered
    Bx, By, Bz = B
    # Faraday's law in integral form on each face
    dBx = dt/dy * (E_edge['z'][i, j+1] - E_edge['z'][i, j]) \
        - dt/dz * (E_edge['y'][i, j, k+1] - E_edge['y'][i, j, k])
    return Bx + dBx, ...
```

## Riemann Solver (Roe-type for MHD)

MHD Roe linearization at interface:

```python
def mhd_roe_flux(UL, UR, B_face, gamma):
    """Roe flux for ideal MHD. Returns numerical flux F at interface."""
    # Average state
    sqrtRhoL = np.sqrt(UL[0])
    sqrtRhoR = np.sqrt(UR[0])
    Roe_avg  = roe_average(UL, UR, sqrtRhoL, sqrtRhoR)
    # Eigenvalue decomposition (7 waves in 1D MHD)
    eigenvals, R, R_inv = mhd_eigensystem(Roe_avg, B_face, gamma)
    # Upwind flux
    alpha = R_inv @ (UR - UL)
    F = 0.5*(flux(UL) + flux(UR)) - 0.5*R @ (abs(eigenvals)*alpha)
    return F
```

## Resistive MHD (∇·(ηJ) term)

```
∂B/∂t = ∇×(v×B) + η/μ₀ ∇²B

Magnetic Reynolds number: Rm = μ₀ σ v L
Rm >> 1: ideal; Rm ~ 1: resistive effects important
```

## Alfvén Speed and CFL

```python
def alfven_speed(B, rho, mu_0=1.0):
    return np.linalg.norm(B) / np.sqrt(mu_0 * rho)

def mhd_cfl(v, B, cs, rho, dx, mu_0=1.0):
    vA  = alfven_speed(B, rho, mu_0)
    vf  = np.sqrt(cs**2 + vA**2)   # fast magnetosonic speed (approx)
    return dx / (np.linalg.norm(v) + vf)
```

## Common Pitfalls

- **∇·B errors**: divergence cleaning (GLM/Dedner) or constrained transport required.
- **Negative pressure**: floor pressure/density; use entropy fix or positivity-preserving limiter.
- **Ambipolar diffusion**: add Hall term for partially ionized plasmas.
