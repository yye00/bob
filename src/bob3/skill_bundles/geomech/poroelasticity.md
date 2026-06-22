# Poroelasticity (Biot Theory)

## Governing Equations

Biot (1941) couples solid deformation with pore fluid flow:

**Equilibrium** (solid):
```
∇·σ + f = 0
σ = C : ε - α p I
ε = ½(∇u + ∇uᵀ)
```

**Continuity** (fluid):
```
∂(α∇·u)/∂t + (1/M) ∂p/∂t = ∇·(k/μ ∇p) + q
```

Parameters:
- α: Biot-Willis coefficient (0 < α ≤ 1)
- M: Biot modulus [Pa]
- k: intrinsic permeability [m²]
- μ: fluid dynamic viscosity [Pa·s]

## Coupled System (FEM Discretization)

```
[K    -Q ] [u]   [f_u]
[-Qᵀ  S/Δt] [p] = [f_p]

K = ∫ Bᵀ C B dΩ        (stiffness)
Q = ∫ α m Np dΩ         (coupling)
S = ∫ (1/M) Np Np dΩ   (storage)
H = ∫ (k/μ) ∇Np·∇Np dΩ (permeability)
```

## Stability: Inf-Sup Condition

Co-located equal-order interpolation for (u, p) can violate inf-sup:

```python
# Safe element pairs:
# Taylor-Hood: P2/P1 (quadratic displacement, linear pressure)
# Mini element: P1+bubble/P1
# Stabilized P1/P1 with pressure Laplacian stabilization

# Stabilization parameter
tau_stab = h**2 / (4 * (k/mu) * dt)
```

## Mandel's Problem (Verification)

Analytical solution for undrained loading of a poroelastic slab:

```python
def mandel_pressure(x, t, a, nu_u, nu, B, G, c_v):
    """Analytical pressure at position x, time t."""
    p0 = 2*B*(1 + nu_u) / (3*(1 - nu_u))
    alpha_m = roots_mandel(nu_u, nu)  # transcendental equation roots
    p = p0 * sum(
        2*sin(am) / (am - sin(am)*cos(am)) * cos(am*x/a) * exp(-am**2*c_v*t/a**2)
        for am in alpha_m
    )
    return p
```

## Undrained vs Drained Moduli

```
Undrained bulk modulus:  K_u = K + α²M
Undrained Poisson ratio: ν_u = (3K_u - 2G) / (2*(3K_u + G))
Skempton's coefficient:  B = α M / K_u
```

## Common Pitfalls

- **Locking**: use Taylor-Hood or reduced integration to avoid volumetric locking.
- **Oscillatory pressure**: use implicit time integration; explicit is conditionally stable with very small Δt.
- **Convergence staggered scheme**: coupling is strong → apply fixed-stress split or full monolithic solve.
