# BSSN Formulation of Numerical Relativity

## 3+1 Decomposition

The 4D spacetime metric is split into spatial metric γ_ij and lapse/shift:

```
ds² = -α² dt² + γ_ij (dx^i + β^i dt)(dx^j + β^j dt)

α  : lapse function  (controls time slicing)
β^i: shift vector   (controls spatial gauge)
γ_ij: 3-metric on spatial slice
```

## BSSN Variables

BSSN (Baumgarte-Shapiro-Shibata-Nakamura) confactors the metric:

```
φ = (1/12) ln det(γ_ij)           (conformal factor)
γ̃_ij = e^{-4φ} γ_ij               (conformal 3-metric, det = 1)
K = γ^{ij} K_ij                   (trace of extrinsic curvature)
Ã_ij = e^{-4φ} (K_ij - γ_ij K/3) (traceless conformal extrinsic curvature)
Γ̃^i = -∂_j γ̃^{ij}                (conformal connection functions)
```

## BSSN Evolution Equations

```
∂_t φ     = -α K/6 + β^k ∂_k φ + ∂_k β^k / 6
∂_t γ̃_ij = -2α Ã_ij + β^k ∂_k γ̃_ij + γ̃_ik ∂_j β^k + γ̃_jk ∂_i β^k - (2/3) γ̃_ij ∂_k β^k
∂_t K     = -γ^{ij} D_i D_j α + α(Ã_{ij} Ã^{ij} + K²/3) + 4πα(ρ + S)
∂_t Ã_ij = e^{-4φ}[-D_i D_j α + α R_ij]^{TF} + α(K Ã_ij - 2 Ã_ik Ã^k_j)
∂_t Γ̃^i  = -2 Ã^{ij} ∂_j α + 2α(Γ̃^i_{jk} Ã^{jk} - 2/3 γ̃^{ij} ∂_j K)
```

Superscript TF: trace-free part.

## Constraint Equations

Must be satisfied initially and monitored during evolution:

```
H = R + K² - K_{ij} K^{ij} - 16π ρ = 0   (Hamiltonian constraint)
M^i = D_j(K^{ij} - γ^{ij} K) - 8π S^i = 0 (momentum constraints)
```

```python
def hamiltonian_violation(gamma, K_trace, K_tf, matter_rho):
    """Monitor ||H|| / ||H_norm|| as a code quality metric."""
    R = ricci_scalar(gamma)
    H = R + K_trace**2 - np.einsum('ij,ij', K_tf, K_tf) - 16*np.pi*matter_rho
    return H
```

## Numerical Derivatives

Use 4th-order centered finite differences for spatial terms:

```python
def d1(f, dx, axis):
    """4th-order centered first derivative."""
    return (-np.roll(f,-2,axis) + 8*np.roll(f,-1,axis)
            - 8*np.roll(f,1,axis) + np.roll(f,2,axis)) / (12*dx)

def d2(f, dx, axis):
    """4th-order centered second derivative."""
    return (-np.roll(f,-2,axis) + 16*np.roll(f,-1,axis) - 30*f
            + 16*np.roll(f,1,axis) - np.roll(f,2,axis)) / (12*dx**2)
```

## Kreiss-Oliger Dissipation

Add artificial dissipation to suppress high-frequency instabilities:

```python
# 4th-order KO dissipation, σ ~ 0.1–0.5
def ko_dissipation(f, dx, sigma):
    d4 = (-np.roll(f,2,0) + 4*np.roll(f,1,0) - 6*f
          + 4*np.roll(f,-1,0) - np.roll(f,-2,0)) / (16*dx)
    return -sigma * d4
```

## Common Pitfalls

- **Γ̃^i as evolved var**: must re-set Γ̃^i from γ̃_ij periodically to enforce algebraic constraint.
- **Singular puncture**: use moving puncture method with χ = e^{-4φ} as evolved variable.
- **Courant condition**: Δt ≤ CFL × Δx (CFL ~ 0.25–0.45 for 4th order with RK4).
