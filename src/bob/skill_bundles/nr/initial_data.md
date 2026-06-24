# Initial Data for Numerical Relativity

## Constraints and Conformal Decomposition

Initial data must satisfy Hamiltonian and momentum constraints.
York-Lichnerowicz conformal decomposition:

```
γ_ij = ψ^4 γ̃_ij      (ψ: conformal factor)

Hamiltonian: Δ̃ψ - (R̃/8)ψ + (Ã^{ij}Ã_{ij}/8)ψ^{-7} - (K²/12)ψ^5 = -2πρψ^5
Momentum:    D̃_j Ã^{ij} - (2/3)γ̃^{ij} D̃_j K = 8π J^i
```

## Bowen-York Puncture Data

Analytic extrinsic curvature for spinning, boosted black holes:

```python
def bowen_york_K(r_vec, P, S):
    """Bowen-York extrinsic curvature for single BH.
    
    P: linear momentum (3-vector)
    S: spin angular momentum (3-vector)
    r: position vector from puncture
    """
    r = norm(r_vec)
    n = r_vec / r
    # Linear momentum contribution
    K_P  = (3/(2*r**2)) * (P[:, None]*n[None, :] + n[:, None]*P[None, :]
                            - (1 - n[:,None]*n[None,:])*dot(P, n))
    # Spin contribution
    eps = levi_civita()
    K_S = (3/r**3) * einsum('ijk,j,k->il', eps, S, n)[:, :, None] * n[None, None, :]
    return K_P + K_S
```

## TWOPUNCTURES (Ansorg et al. 2004)

Spectral solver for binary black hole initial data:

```
# Typically configured via parameter file
TwoPunctures::par_b  = 3.0        # half-separation [M]
TwoPunctures::par_m_plus  = 0.5  # bare mass BH+
TwoPunctures::par_m_minus = 0.5  # bare mass BH-
TwoPunctures::par_P_plus  = [0, 0.133, 0]   # momentum [M]
TwoPunctures::par_S_plus  = [0, 0, 0.2]     # spin [M²]
```

## ADM Mass and Angular Momentum (Surface Integrals)

```python
def adm_mass(psi, dx):
    """ADM mass from surface integral at infinity via conformal factor."""
    # M_ADM = -(1/2π) ∮ ∂_i psi dS^i
    # For isolated system, evaluate on large sphere
    return -1/(2*np.pi) * surface_flux(np.gradient(psi, dx))

def adm_angular_momentum(K_ij, gamma_ij, epsilon, dx):
    """ADM angular momentum J_k = (1/8π) ∮ ε_{kij} K^{il} n_l dS_j"""
    pass
```

## Eccentricity Reduction

Quasi-circular orbit initial data still has residual eccentricity:

```
# Iterative method: measure e from waveform or coordinate separation
# Adjust radial momentum P_r until e < 0.001

e_approx = (r_max - r_min) / (r_max + r_min)  # from r(t) oscillation

P_r_correction = -e * P_phi / r   # first-order estimate
```

## Common Pitfalls

- **Junk radiation**: initial data in conformal-thin-sandwich (CTS) is not time-symmetric; first ~50M dominated by gauge transient.
- **Mass vs bare mass**: ADM mass ≠ bare puncture mass; calibrate numerically.
- **Sign conventions**: verify K_ij sign convention matches evolution code.
